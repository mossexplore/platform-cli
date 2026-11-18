package keepalive

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

const WorkerArg = "--internal-go-ping-worker"

var errReplaced = errors.New("保活进程已被替换")

func Start(ctx context.Context, paths localstate.Paths, cfg localstate.Config, version string, automatic bool) (string, error) {
	if !cfg.PingEnabled() {
		return "自动保活已在配置中关闭", nil
	}
	profile := cfg.Profile()
	creds, err := paths.LoadCredentials(profile, time.Now())
	if err != nil {
		return "当前环境未登录，请执行 ml login 登录该环境", nil
	}
	if _, err := paths.SelectedBusiness(creds); err != nil {
		return "尚未选择业务，选择后将启动自动保活", nil
	}
	parent := os.Getppid()
	current := owner{PID: parent, Identity: identity(parent)}
	if current.Identity == "" {
		return "无法识别当前终端进程，未启动自动保活", nil
	}
	path, err := os.Executable()
	if err != nil {
		return "", err
	}
	var spawned string
	blocked := false
	err = update(paths, func(entries map[string]Entry) error {
		entry := entries[profile.Name]
		if entry.ManualStop && automatic && entry.Endpoint == profile.Origin() && entry.Username == creds.Username {
			blocked = true
			return nil
		}
		if entry.Endpoint != profile.Origin() || entry.Username != creds.Username {
			entry = Entry{Endpoint: profile.Origin(), Username: creds.Username}
		}
		entry.ManualStop = false
		// Preserve the stop decision even if an old worker is still winding down.
		if entry.Status == "stopping" || entry.Status == "stopped" {
			entry.WorkerToken = ""
		}
		entry.Owner = validOwners(entry)
		hasOwner := false
		for _, item := range entry.Owner {
			if item.Identity == current.Identity {
				hasOwner = true
				break
			}
		}
		if !hasOwner {
			entry.Owner = append(entry.Owner, current)
		}
		if entry.WorkerToken == "" || !alive(entry) || entry.Version != version {
			token := localstate.NewID()
			proc := exec.Command(path, WorkerArg, profile.Name, token)
			detachProcess(proc)
			if err := proc.Start(); err != nil {
				return errors.New("无法启动后台保活进程")
			}
			entry.WorkerPID, entry.WorkerIdentity = proc.Process.Pid, identity(proc.Process.Pid)
			entry.Version, entry.WorkerToken, entry.Status = version, token, "starting"
			entry.LastActivity = time.Now()
			spawned = token
			_ = proc.Process.Release()
		}
		entries[profile.Name] = entry
		return nil
	})
	if err != nil {
		return "", err
	}
	if blocked {
		return "当前环境的自动保活已手动停止，运行 ml auth ping start 可恢复", nil
	}
	if spawned == "" {
		return "", nil
	}
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		entry, running, err := View(paths, profile.Name)
		if err != nil {
			return "", err
		}
		if entry.WorkerToken != spawned {
			return "", errReplaced
		}
		if running && entry.Status == "running" {
			return "", nil
		}
		select {
		case <-ctx.Done():
			return "", ctx.Err()
		case <-time.After(100 * time.Millisecond):
		}
	}
	return "", errors.New("自动保活未能确认启动")
}

func RunWorker(ctx context.Context, paths localstate.Paths, name, token, version string) error {
	failureDelay := time.Duration(0)
	report := func(change func(*Entry)) error {
		return update(paths, func(entries map[string]Entry) error {
			entry, ok := entries[name]
			if !ok || entry.WorkerToken != token || entry.WorkerPID != os.Getpid() {
				return errReplaced
			}
			change(&entry)
			entries[name] = entry
			return nil
		})
	}
	defer func() {
		_ = report(func(entry *Entry) {
			entry.WorkerToken, entry.WorkerIdentity, entry.Status = "", "", "stopped"
			entry.WorkerPID = 0
		})
	}()
	for ctx.Err() == nil {
		entry, _, err := View(paths, name)
		if err != nil {
			return err
		}
		if entry.WorkerToken != token || entry.WorkerPID != os.Getpid() || token == "" || len(entry.Owner) == 0 || entry.Status == "stopping" {
			return nil
		}
		cfg, err := localstate.LoadConfig(paths)
		if err != nil {
			return err
		}
		if !cfg.PingEnabled() {
			return nil
		}
		cfg.Current = name
		profile := cfg.Profile()
		if profile.Name == "" || profile.Origin() != entry.Endpoint {
			return nil
		}
		creds, err := paths.CredentialsFor(profile)
		if err != nil || creds.Username != entry.Username {
			return nil
		}
		if entry.Status == "starting" {
			if err := report(func(entry *Entry) {
				entry.WorkerIdentity = identity(os.Getpid())
				if entry.Status == "starting" {
					entry.Status = "running"
				}
			}); err != nil {
				return err
			}
		}
		now := time.Now()
		if !now.Before(entry.LastActivity.Add(time.Duration(cfg.Auth.PingMinutes)*time.Minute)) &&
			!now.Before(entry.LastAttempt.Add(failureDelay)) {
			id := localstate.NewID()
			if err := report(func(entry *Entry) {
				if entry.Status == "stopping" {
					return
				}
				entry.LastAttempt, entry.RequestID, entry.Status = now, id, "requesting"
			}); err != nil {
				return err
			}
			current, _, err := View(paths, name)
			if err != nil || current.Status == "stopping" {
				return err
			}
			session := platform.Session{Paths: paths, Config: cfg, CLIVersion: version}
			err = session.Probe(ctx, creds, id)
			if err != nil {
				if errors.Is(err, platform.ErrSessionExpired) {
					_ = report(func(entry *Entry) { entry.Error = "平台会话已失效"; entry.Failure++ })
					return nil
				}
				failureDelay = min(5*time.Minute, max(30*time.Second, 2*failureDelay))
				if err := report(func(entry *Entry) {
					if entry.Status != "stopping" {
						entry.Status = "retrying"
					}
					entry.Error = "平台保活请求未确认成功"
					entry.Failure++
				}); err != nil {
					return err
				}
			} else {
				failureDelay = 0
				if err := report(func(entry *Entry) {
					if entry.Status != "stopping" {
						entry.Status = "running"
					}
					entry.LastConfirmed, entry.LastActivity = time.Now(), time.Now()
					entry.Error = ""
					entry.Success++
				}); err != nil {
					return err
				}
			}
		}
		select {
		case <-ctx.Done():
		case <-time.After(5 * time.Second):
		}
	}
	return nil
}

func TerminalCount(entry Entry) int { return len(entry.Owner) }
