package keepalive

import (
	"context"
	"errors"
	"os"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

const (
	WorkerArg      = "--internal-go-ping-worker"
	workerProtocol = 2
	workerPoll     = 5 * time.Second
)

var (
	errReplaced      = errors.New("保活进程已被替换")
	errTargetChanged = errors.New("保活期间会话或业务上下文已变化")
)

type worker struct {
	paths      localstate.Paths
	name       string
	token      string
	version    string
	retryDelay time.Duration
}

func RunWorker(ctx context.Context, paths localstate.Paths, name, token, version string) error {
	w := worker{paths: paths.WithoutSession(), name: name, token: token, version: version}
	// The parent holds the registry lock until the worker PID and token are saved.
	if err := w.update(func(entry *Entry) error {
		entry.WorkerIdentity = identity(os.Getpid())
		return nil
	}); err != nil {
		return err
	}
	defer func() { _ = w.update(func(entry *Entry) error { clearWorker(entry); return nil }) }()
	var nextCleanup time.Time
	for ctx.Err() == nil {
		stop, err := w.poll(ctx)
		if (stop || err != nil) && !errors.Is(err, localstate.ErrLockBusy) {
			return err
		}
		if now := time.Now(); now.After(nextCleanup) {
			if cfg, err := localstate.LoadConfig(w.paths); err == nil {
				MaintainSessions(w.paths, time.Duration(cfg.Auth.PingMinutes)*time.Minute)
			}
			nextCleanup = now.Add(localstate.SessionCleanupInterval)
		}
		select {
		case <-ctx.Done():
		case <-time.After(workerPoll):
		}
	}
	return nil
}

func clearWorker(entry *Entry) {
	entry.WorkerToken, entry.WorkerIdentity, entry.Status = "", "", "stopped"
	entry.WorkerPID = 0
}

func (w *worker) update(change func(*Entry) error) error {
	return w.updateWithin(localstate.DefaultLockWait, change)
}

func (w *worker) updateWithin(wait time.Duration, change func(*Entry) error) error {
	return updateWithin(w.paths, wait, func(entries map[string]Entry) error {
		entry := entries[w.name]
		if w.token == "" || entry.WorkerToken != w.token || entry.WorkerPID != os.Getpid() {
			return errReplaced
		}
		if err := change(&entry); err != nil {
			return err
		}
		entries[w.name] = entry
		return nil
	})
}

func (w *worker) poll(ctx context.Context) (bool, error) {
	cfg, err := localstate.LoadConfig(w.paths)
	if err != nil || !cfg.PingEnabled() {
		return true, err
	}
	cfg.Current = w.name
	profile := cfg.Profile()
	interval := time.Duration(cfg.Auth.PingMinutes) * time.Minute
	entry, _, err := View(w.paths, w.name, interval)
	if err != nil {
		return true, err
	}
	if entry.WorkerToken != w.token || entry.WorkerPID != os.Getpid() || entry.Status == "stopping" ||
		profile.Name == "" || profile.Origin() != entry.Endpoint {
		return true, nil
	}
	if len(entry.Owner) == 0 {
		// Check again under the registry lock in case another invocation just joined.
		stopped := false
		err := w.update(func(current *Entry) error {
			if len(validOwners(*current, time.Now(), interval)) == 0 {
				current.Owner = nil
				clearWorker(current)
				stopped = true
			}
			return nil
		})
		return stopped, err
	}
	creds, err := w.paths.CredentialsFor(profile)
	if err != nil || creds.Username != entry.Username {
		return true, nil
	}
	target, ok := selectProbeTarget(w.paths, entry, creds)
	if !ok {
		return false, w.setStatus(entry, "waiting")
	}
	if entry.Status == "starting" || entry.Status == "waiting" {
		if err := w.setStatus(entry, "running"); err != nil {
			return true, err
		}
	}
	now := time.Now()
	if now.Before(entry.LastActivity.Add(interval)) || now.Before(entry.LastAttempt.Add(w.retryDelay)) {
		return false, nil
	}
	return w.probe(ctx, cfg, creds, target, interval)
}

func (w *worker) setStatus(previous Entry, status string) error {
	if previous.Status == status {
		return nil
	}
	return w.update(func(entry *Entry) error {
		if entry.Status == "stopping" {
			return nil
		}
		entry.Status = status
		return nil
	})
}

type probeTarget struct {
	owner    ownerRef
	paths    localstate.Paths
	business localstate.KeepaliveTarget
}

func selectProbeTarget(paths localstate.Paths, entry Entry, creds localstate.Credentials) (probeTarget, bool) {
	var selected probeTarget
	rank := 0
	for _, item := range entry.Owner {
		scoped, ok := item.paths(paths)
		if !ok {
			continue
		}
		preference := 1
		if scoped.IsSessionIsolated() {
			preference += 2
		}
		if item.ownerRef == entry.LastOwner {
			preference++
		}
		if preference <= rank {
			continue
		}
		business, err := scoped.KeepaliveTarget(creds)
		if err == nil {
			selected = probeTarget{owner: item.ownerRef, paths: scoped, business: business}
			rank = preference
		}
	}
	return selected, rank != 0
}

func (target probeTarget) registered(entry Entry, interval time.Duration) bool {
	if entry.Status == "stopping" {
		return false
	}
	now := time.Now()
	for _, item := range entry.Owner {
		if item.ownerRef == target.owner && item.live(now, interval) {
			return true
		}
	}
	return false
}

func (target probeTarget) active(entry Entry, creds localstate.Credentials, interval time.Duration) bool {
	if !target.registered(entry, interval) {
		return false
	}
	business, err := target.paths.KeepaliveTarget(creds)
	return err == nil && business == target.business
}

func (w *worker) probe(ctx context.Context, cfg localstate.Config, creds localstate.Credentials, target probeTarget, interval time.Duration) (bool, error) {
	id := localstate.NewID()
	profile := cfg.Profile()
	err := w.update(func(entry *Entry) error {
		now := time.Now()
		if now.Before(entry.LastActivity.Add(interval)) || !target.active(*entry, creds, interval) {
			return errTargetChanged
		}
		if !w.sameCredentials(profile, creds) {
			return errTargetChanged
		}
		entry.LastAttempt, entry.RequestID, entry.Status = now, id, "requesting"
		return nil
	})
	if errors.Is(err, errTargetChanged) {
		return false, nil
	}
	if err != nil {
		return true, err
	}
	session := platform.Session{Paths: target.paths, Config: cfg, CLIVersion: w.version}
	err = session.Probe(ctx, creds, target.business.BusinessID, id, func(cookie, csrf string) error {
		ttl := time.Duration(cfg.Auth.TTLSeconds) * time.Second
		return w.confirmProbe(ctx, profile, creds, target, cookie, csrf, ttl, interval)
	})
	if err == nil {
		w.retryDelay = 0
		return false, nil
	}
	if errors.Is(err, errReplaced) {
		return true, err
	}
	expired := false
	reportErr := w.update(func(entry *Entry) error {
		if entry.Status == "stopping" {
			return nil
		}
		if !target.active(*entry, creds, interval) || !w.sameCredentials(profile, creds) {
			entry.Status = "waiting"
			return nil
		}
		expired = errors.Is(err, platform.ErrSessionExpired)
		if expired {
			entry.Status = "stopping"
			entry.Error = "平台会话已失效"
		} else {
			entry.Status = "retrying"
			entry.Error = "平台保活请求未确认成功"
			w.retryDelay = min(5*time.Minute, max(30*time.Second, 2*w.retryDelay))
		}
		entry.Failure++
		return nil
	})
	return expired, reportErr
}

func (w *worker) confirmProbe(ctx context.Context, profile localstate.Profile, creds localstate.Credentials, target probeTarget, cookie, csrf string, ttl, interval time.Duration) error {
	deadline := time.Now().Add(localstate.DefaultLockWait)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		err := target.paths.TryExtendKeepaliveCredentials(profile, creds, target.business, cookie, csrf, ttl, func(write func() error) error {
			return w.updateWithin(0, func(entry *Entry) error {
				if !target.registered(*entry, interval) {
					return errTargetChanged
				}
				if err := write(); err != nil {
					return err
				}
				entry.Status = "running"
				entry.LastConfirmed, entry.LastActivity = time.Now(), time.Now()
				entry.LastOwner, entry.Error = target.owner, ""
				entry.Success++
				return nil
			})
		})
		if !errors.Is(err, localstate.ErrLockBusy) || !time.Now().Before(deadline) {
			return err
		}
		// Retry the same response with no locks held between attempts.
		if err := waitForStateChange(ctx); err != nil {
			return err
		}
	}
}

func (w *worker) sameCredentials(profile localstate.Profile, creds localstate.Credentials) bool {
	latest, err := w.paths.CredentialsFor(profile)
	return err == nil && latest.StateID == creds.StateID && latest.Username == creds.Username &&
		latest.Cookie == creds.Cookie && latest.CSRFToken == creds.CSRFToken
}

func workerEnvironment(environ []string) []string {
	filtered := make([]string, 0, len(environ))
	for _, entry := range environ {
		key, _, _ := strings.Cut(entry, "=")
		if strings.EqualFold(key, "DSH_SHELL") ||
			strings.EqualFold(key, "DSH_SESSION_ID") ||
			strings.EqualFold(key, "ML_SESSION_ID") {
			continue
		}
		filtered = append(filtered, entry)
	}
	return filtered
}
