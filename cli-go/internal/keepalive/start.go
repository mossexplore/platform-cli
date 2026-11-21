package keepalive

import (
	"context"
	"errors"
	"os"
	"os/exec"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func Start(ctx context.Context, paths localstate.Paths, cfg localstate.Config, version string, automatic bool) (string, error) {
	return start(ctx, paths, cfg, version, automatic, "")
}

func SessionActivity(ctx context.Context, paths localstate.Paths, cfg localstate.Config, version, username string) error {
	_, err := start(ctx, paths, cfg, version, true, username)
	return err
}

func start(ctx context.Context, paths localstate.Paths, cfg localstate.Config, version string, automatic bool, activeUser string) (string, error) {
	if !cfg.PingEnabled() {
		return "自动保活已在配置中关闭", nil
	}
	profile, err := cfg.RequireProfile()
	if err != nil {
		return "", err
	}
	if localstate.Denied("auth ping start", profile.Policy.Deny) {
		return "当前环境禁止启动自动保活", nil
	}
	interval := time.Duration(cfg.Auth.PingMinutes) * time.Minute
	paths.BusinessOverride = "" // Background probes always use the registered environment selection.
	deadline := time.Now().Add(workerPoll + 3*time.Second)
	for {
		if err := ctx.Err(); err != nil {
			return "", err
		}
		result, err := register(paths, profile, interval, version, automatic, activeUser)
		if err != nil || result.message != "" {
			return result.message, err
		}
		if result.token != "" {
			return "", waitForWorker(ctx, paths, profile.Name, interval, result.token)
		}
		if !result.stopping {
			return "", nil
		}
		if !time.Now().Before(deadline) {
			return "", errors.New("上一个保活进程尚未退出")
		}
		if err := waitForStateChange(ctx); err != nil {
			return "", err
		}
	}
}

type registration struct {
	token    string
	message  string
	stopping bool
}

func register(paths localstate.Paths, profile localstate.Profile, interval time.Duration, version string, automatic bool, activeUser string) (registration, error) {
	var result registration
	err := update(paths, func(entries map[string]Entry) error {
		now := time.Now()
		creds, err := paths.LoadCredentials(profile, now)
		if err != nil {
			result.message = "当前环境未登录，请执行 ml login 登录该环境"
			return nil
		}
		if activeUser != "" && activeUser != creds.Username {
			return nil
		}
		if _, err := paths.KeepaliveTarget(creds); err != nil {
			result.message = "尚未选择业务，选择后将启动自动保活"
			return nil
		}
		item := currentOwner(paths.Session, now)
		if item.Mode != localstate.SessionModeDSH && item.Identity == "" {
			result.message = "无法识别当前终端进程，未启动自动保活"
			return nil
		}
		entry := entries[profile.Name]
		sameLogin := entry.Endpoint == profile.Origin() && entry.Username == creds.Username
		if sameLogin && entry.ManualStop && automatic {
			result.message = "当前环境的自动保活已手动停止，运行 ml auth ping start 可恢复"
			return nil
		}
		running := alive(entry)
		if running && (!sameLogin || entry.Protocol != workerProtocol || entry.Version != version || entry.Status == "stopping") {
			entry.Status = "stopping"
			entries[profile.Name] = entry
			result.stopping = true
			return nil
		}
		if !sameLogin || entry.Protocol != workerProtocol {
			// Older PID-only registrations cannot identify their original session.
			entry = Entry{Endpoint: profile.Origin(), Username: creds.Username}
		}
		entry.ManualStop = false
		entry.Owner = validOwners(entry, now, interval)
		registerOwner(&entry, item)
		if activeUser != "" {
			entry.LastActivity = now
		}
		if !running || entry.WorkerToken == "" || entry.Status == "stopped" {
			if err := launchWorker(&entry, profile.Name, version, now); err != nil {
				return err
			}
			result.token = entry.WorkerToken
		}
		entries[profile.Name] = entry
		return nil
	})
	return result, err
}

func launchWorker(entry *Entry, profile, version string, now time.Time) error {
	path, err := os.Executable()
	if err != nil {
		return err
	}
	token := localstate.NewID()
	proc := exec.Command(path, WorkerArg, profile, token)
	proc.Env = workerEnvironment(os.Environ())
	detachProcess(proc)
	if err := proc.Start(); err != nil {
		return errors.New("无法启动后台保活进程")
	}
	entry.WorkerPID, entry.WorkerIdentity = proc.Process.Pid, identity(proc.Process.Pid)
	entry.Version, entry.WorkerToken, entry.Status = version, token, "starting"
	entry.Protocol = workerProtocol
	entry.LastActivity = now
	_ = proc.Process.Release()
	return nil
}

func waitForWorker(ctx context.Context, paths localstate.Paths, profile string, interval time.Duration, token string) error {
	deadline := time.Now().Add(3 * time.Second)
	for time.Now().Before(deadline) {
		entry, running, err := View(paths, profile, interval)
		if err != nil {
			return err
		}
		if entry.WorkerToken != token {
			return errReplaced
		}
		if running && (entry.Status == "running" || entry.Status == "waiting") {
			return nil
		}
		if err := waitForStateChange(ctx); err != nil {
			return err
		}
	}
	return errors.New("自动保活未能确认启动")
}

func waitForStateChange(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(100 * time.Millisecond):
		return nil
	}
}
