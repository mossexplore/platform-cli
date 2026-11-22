package keepalive

import (
	"context"
	"errors"
	"os"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const (
	WorkerArg      = "--internal-go-ping-worker"
	WorkerStandby  = "standby"
	workerProtocol = 3
	workerPoll     = 5 * time.Second
)

var (
	errReplaced      = errors.New("保活进程已被替换")
	errTargetChanged = errors.New("保活期间会话或业务上下文已变化")
)

type worker struct {
	paths   localstate.Paths
	name    string
	token   string
	version string
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
			MaintainSessions(w.paths)
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
	entry, _, err := View(w.paths, w.name)
	if err != nil {
		return true, err
	}
	if entry.WorkerToken != w.token || entry.WorkerPID != os.Getpid() || entry.Protocol != workerProtocol || entry.Status == "stopping" ||
		profile.Name == "" || profile.Origin() != entry.Endpoint {
		return true, nil
	}
	if len(entry.Owner) == 0 {
		// Check again under the registry lock in case another invocation just joined.
		stopped := false
		err := w.update(func(current *Entry) error {
			if len(validOwners(*current)) == 0 {
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
	job := probeJob{
		paths: target.paths, cfg: cfg, creds: creds, target: target.business, version: w.version,
		owner: target.owner, workerToken: w.token,
	}
	result, err := job.run(ctx)
	return result.State == "expired", err
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
