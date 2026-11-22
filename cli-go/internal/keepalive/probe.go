package keepalive

import (
	"context"
	"errors"
	"math"
	"os"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

type probeLease struct {
	ID        string    `json:"id,omitempty"`
	Host      string    `json:"host,omitempty"`
	PID       int       `json:"pid,omitempty"`
	Identity  string    `json:"identity,omitempty"`
	Deadline  time.Time `json:"deadline,omitzero"`
	Cancelled bool      `json:"cancelled,omitempty"`
}

func (lease probeLease) active(now time.Time) bool {
	return lease.ID != "" && now.Before(lease.Deadline) &&
		(lease.Identity == "" || lease.Identity == identity(lease.PID))
}

type probeJob struct {
	paths       localstate.Paths
	cfg         localstate.Config
	creds       localstate.Credentials
	target      localstate.KeepaliveTarget
	version     string
	owner       ownerRef
	workerToken string
	hostKey     string
}

func probeBudget(cfg localstate.Config) time.Duration {
	const margin = 2 * localstate.DefaultLockWait
	const maximumMS = int64((time.Duration(math.MaxInt64) - 2*margin) / time.Millisecond)
	timeout := time.Duration(min(int64(cfg.API.TimeoutMS), maximumMS)) * time.Millisecond
	return timeout + margin
}

func (job probeJob) sameTarget(profile localstate.Profile) bool {
	latest, err := job.paths.CredentialsFor(profile)
	if err != nil || latest.StateID != job.creds.StateID || latest.Username != job.creds.Username ||
		latest.Cookie != job.creds.Cookie || latest.CSRFToken != job.creds.CSRFToken {
		return false
	}
	target, err := job.paths.KeepaliveTarget(latest)
	return err == nil && target == job.target
}

func (job probeJob) eligible(data entryFile, entry Entry, now time.Time) bool {
	if entry.ManualStop {
		return false
	}
	profile := job.cfg.Profile()
	cfg, err := localstate.LoadConfig(job.paths.WithoutSession())
	if err != nil || !cfg.PingEnabled() {
		return false
	}
	cfg.Current = profile.Name
	current := cfg.Profile()
	if current.Name != profile.Name || current.Origin() != profile.Origin() ||
		localstate.Denied("auth ping start", current.Policy.Deny) {
		return false
	}
	if job.hostKey != "" {
		host := data.Hosts[job.hostKey]
		return host.active(now) && host.Profile == profile.Name &&
			!localstate.Denied("auth ping tick", current.Policy.Deny)
	}
	if job.workerToken == "" || entry.WorkerToken != job.workerToken || entry.Protocol != workerProtocol || entry.Status == "stopping" {
		return false
	}
	for _, item := range entry.Owner {
		if item.ownerRef == job.owner && item.live() {
			return true
		}
	}
	return false
}

func (job probeJob) reserve(ctx context.Context) (TickResult, error) {
	result := TickResult{State: "superseded"}
	profile := job.cfg.Profile()
	pid := os.Getpid()
	err := updateRegistry(job.paths, localstate.DefaultLockWait, func(data entryFile) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		now := time.Now()
		entry := data.Profiles[profile.Name]
		switch {
		case entry.ManualStop:
			result.State = "stopped"
		case alive(entry) && entry.Protocol != workerProtocol:
			result.State = "legacy_worker"
		case !job.eligible(data, entry, now) || !job.sameTarget(profile):
			return nil
		case entry.InFlight.active(now):
			result.State = "in_flight"
		default:
			if entry.Endpoint != profile.Origin() || entry.Username != job.creds.Username {
				entry = resetLogin(entry, job.creds.Username, profile.Origin())
			}
			if entry.ExpiredState == job.creds.StateID {
				result.State = "expired"
				return nil
			}
			if job.workerToken != "" {
				if hasEligibleHost(data, job.paths, profile, job.creds, now) {
					result.State, entry.Status = WorkerStandby, WorkerStandby
					data.Profiles[profile.Name] = entry
					return nil
				}
				if entry.Status == WorkerStandby {
					entry.Status = "running"
					data.Profiles[profile.Name] = entry
				}
			}
			due := maxTime(entry.LastActivity.Add(time.Duration(job.cfg.Auth.PingMinutes)*time.Minute), entry.RetryAt)
			if now.Before(due) {
				result.State, result.NextAttempt = "not_due", displayTime(due)
				result.RetryPending = now.Before(entry.RetryAt)
				return nil
			}
			result.State, result.RequestID = "requesting", localstate.NewID()
			entry.LastAttempt, entry.RequestID = now, result.RequestID
			entry.InFlight = probeLease{
				ID: result.RequestID, Host: job.hostKey, PID: pid,
				Identity: identity(pid), Deadline: now.Add(probeBudget(job.cfg)),
			}
			if job.workerToken != "" {
				entry.Status = "requesting"
			}
			data.Profiles[profile.Name] = entry
		}
		return nil
	})
	return result, err
}

func (job probeJob) run(ctx context.Context) (TickResult, error) {
	result, err := job.reserve(ctx)
	if err != nil || result.State != "requesting" {
		return result, err
	}
	probeCtx, cancel := context.WithTimeout(ctx, probeBudget(job.cfg))
	defer cancel()
	session := platform.Session{Paths: job.paths, Config: job.cfg, CLIVersion: job.version}
	err = session.Probe(probeCtx, job.creds, job.target.BusinessID, result.RequestID, func(cookie, csrf string) error {
		return job.confirm(probeCtx, result.RequestID, cookie, csrf)
	})
	if err == nil {
		result.State = "confirmed"
		return result, nil
	}
	return job.finishFailure(ctx, result, err)
}

func (job probeJob) confirm(ctx context.Context, id, cookie, csrf string) error {
	deadline := time.Now().Add(localstate.DefaultLockWait)
	profile := job.cfg.Profile()
	ttl := time.Duration(job.cfg.Auth.TTLSeconds) * time.Second
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := job.paths.TryExtendKeepaliveCredentials(profile, job.creds, job.target, cookie, csrf, ttl, func(write func() error) error {
			return updateRegistry(job.paths, 0, func(data entryFile) error {
				entry := data.Profiles[profile.Name]
				now := time.Now()
				if ctx.Err() != nil || entry.InFlight.ID != id || entry.InFlight.Cancelled ||
					!entry.InFlight.active(now) || !job.eligible(data, entry, now) {
					return errTargetChanged
				}
				if err := write(); err != nil {
					return err
				}
				entry.LastConfirmed, entry.LastActivity = now, now
				entry.Error, entry.ExpiredState, entry.RetryDelay, entry.RetryAt = "", "", 0, time.Time{}
				entry.LastOwner, entry.InFlight = job.owner, probeLease{}
				entry.Success++
				if job.workerToken != "" && entry.WorkerToken == job.workerToken {
					entry.Status = "running"
				}
				data.Profiles[profile.Name] = entry
				return nil
			})
		})
		if !errors.Is(err, localstate.ErrLockBusy) || !time.Now().Before(deadline) {
			return err
		}
		if err := waitForStateChange(ctx); err != nil {
			return err
		}
	}
}

func (job probeJob) finishFailure(ctx context.Context, result TickResult, cause error) (TickResult, error) {
	result.State = "superseded"
	name := job.cfg.Current
	err := updateRegistry(job.paths, localstate.DefaultLockWait, func(data entryFile) error {
		entry := data.Profiles[name]
		if entry.InFlight.ID != result.RequestID {
			return nil
		}
		now := time.Now()
		valid := ctx.Err() == nil && !entry.InFlight.Cancelled && job.eligible(data, entry, now) &&
			job.sameTarget(job.cfg.Profile()) && !errors.Is(cause, errTargetChanged)
		entry.InFlight = probeLease{}
		if valid {
			entry.Failure++
			if errors.Is(cause, platform.ErrSessionExpired) {
				result.State, entry.Error = "expired", "平台会话已失效"
				entry.ExpiredState = job.creds.StateID
			} else {
				result.State, entry.Error = "retrying", "平台保活请求未确认成功"
				entry.RetryDelay = min(5*time.Minute, max(30*time.Second, 2*entry.RetryDelay))
				entry.RetryAt = now.Add(entry.RetryDelay)
				result.NextAttempt = displayTime(entry.RetryAt)
			}
		}
		if job.workerToken != "" && entry.WorkerToken == job.workerToken && entry.Status == "requesting" {
			switch result.State {
			case "retrying":
				entry.Status = "retrying"
			case "expired":
				entry.Status = "stopping"
			default:
				entry.Status = "waiting"
			}
		}
		data.Profiles[name] = entry
		return nil
	})
	return result, err
}

func maxTime(a, b time.Time) time.Time {
	if b.After(a) {
		return b
	}
	return a
}
