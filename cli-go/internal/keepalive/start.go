package keepalive

import (
	"context"
	"errors"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const registrationLockWait = 150 * time.Millisecond

// Replace same-version workers without changing the protocol shared with the host bridge.
const workerTokenPrefix = "dsh-priority-"

func Start(ctx context.Context, paths localstate.Paths, cfg localstate.Config, version string, automatic bool) (string, error) {
	if paths.Session.Mode == localstate.SessionModeDSH {
		return ResumeHost(paths, cfg)
	}
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
	deadline := time.Now().Add(workerPoll + 3*time.Second)
	for {
		if err := ctx.Err(); err != nil {
			return "", err
		}
		result, err := register(paths, profile, version, automatic)
		if err != nil || result.message != "" {
			return result.message, err
		}
		if result.token != "" {
			return "", waitForWorker(ctx, paths, profile.Name, result.token)
		}
		if !result.stopping {
			return "", nil
		}
		if !time.Now().Before(deadline) {
			return "", ErrRegistrationPending
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

var ErrRegistrationPending = errors.New("上一个保活进程尚未退出")

// SyncEnvironment updates old and new registrations together after the environment is saved.
func SyncEnvironment(paths localstate.Paths, cfg localstate.Config, previous, version string, startNew bool) (string, error) {
	if paths.Session.Mode == localstate.SessionModeDSH {
		return "", nil
	}
	if previous == "" && !startNew {
		return "", nil
	}
	var result registration
	err := updateWithin(paths, registrationLockWait, func(entries map[string]Entry) error {
		if previous != "" {
			if err := detachOwner(entries, paths, previous); err != nil {
				return err
			}
		}
		if !startNew {
			return nil
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		if localstate.Denied("auth ping start", profile.Policy.Deny) {
			result.message = "当前环境禁止启动自动保活"
			return nil
		}
		result, err = registerEntry(entries, paths, profile, version, true)
		return err
	})
	if err == nil && result.stopping {
		err = ErrRegistrationPending
	}
	return result.message, err
}

func register(paths localstate.Paths, profile localstate.Profile, version string, automatic bool) (registration, error) {
	var result registration
	err := update(paths, func(entries map[string]Entry) error {
		var err error
		result, err = registerEntry(entries, paths, profile, version, automatic)
		return err
	})
	return result, err
}

func registerEntry(entries map[string]Entry, paths localstate.Paths, profile localstate.Profile, version string, automatic bool) (registration, error) {
	var result registration
	paths.BusinessOverride = "" // Use the registered environment selection.
	now := time.Now()
	creds, err := paths.LoadCredentials(profile, now)
	if err != nil {
		result.message = "当前环境未登录，请执行 ml login 登录该环境"
		return result, nil
	}
	if _, err := paths.KeepaliveTarget(creds); err != nil {
		result.message = "尚未选择业务，选择后将启动自动保活"
		return result, nil
	}
	item := currentOwner(paths.Session)
	if item.Identity == "" {
		result.message = "无法识别当前终端进程，未启动自动保活"
		return result, nil
	}
	entry := entries[profile.Name]
	sameLogin := entry.Endpoint == profile.Origin() && entry.Username == creds.Username
	if entry.ManualStop && automatic {
		result.message = "当前环境的自动保活已手动停止，运行 ml auth ping start 可恢复"
		return result, nil
	}
	running := alive(entry)
	if running && (!sameLogin || entry.Protocol != workerProtocol || entry.Version != version ||
		!strings.HasPrefix(entry.WorkerToken, workerTokenPrefix) || entry.Status == "stopping") {
		entry.Status = "stopping"
		entries[profile.Name] = entry
		result.stopping = true
		return result, nil
	}
	if !sameLogin {
		entry = resetLogin(entry, creds.Username, profile.Origin())
	}
	entry.ManualStop = false
	entry.Owner = validOwners(entry)
	registerOwner(&entry, item)
	if !running || entry.WorkerToken == "" || entry.Status == "stopped" {
		if err := launchWorker(&entry, profile.Name, version, now); err != nil {
			return result, err
		}
		result.token = entry.WorkerToken
	}
	entries[profile.Name] = entry
	return result, nil
}

func launchWorker(entry *Entry, profile, version string, now time.Time) error {
	path, err := os.Executable()
	if err != nil {
		return err
	}
	token := workerTokenPrefix + localstate.NewID()
	proc := exec.Command(path, WorkerArg, profile, token)
	proc.Env = workerEnvironment(os.Environ())
	detachProcess(proc)
	if err := proc.Start(); err != nil {
		return errors.New("无法启动后台保活进程")
	}
	entry.WorkerPID, entry.WorkerIdentity = proc.Process.Pid, identity(proc.Process.Pid)
	entry.Version, entry.WorkerToken, entry.Status = version, token, "starting"
	entry.Protocol = workerProtocol
	if entry.LastActivity.IsZero() {
		entry.LastActivity = now
	}
	_ = proc.Process.Release()
	return nil
}

func waitForWorker(ctx context.Context, paths localstate.Paths, profile string, token string) error {
	return confirmWorker(ctx, token, 3*time.Second, func() (Entry, bool, error) {
		return View(paths, profile)
	})
}

func confirmWorker(ctx context.Context, token string, timeout time.Duration, read func() (Entry, bool, error)) error {
	deadline := time.Now().Add(timeout)
	for {
		if err := ctx.Err(); err != nil {
			return err
		}
		entry, running, err := read()
		if err == nil && entry.WorkerToken != "" && entry.WorkerToken != token {
			return errReplaced
		}
		if err == nil && entry.WorkerToken == token && running {
			switch entry.Status {
			case "running", "waiting", "requesting", "retrying", WorkerStandby:
				return nil
			}
		}
		if !time.Now().Before(deadline) {
			if err != nil {
				return fmt.Errorf("自动保活未能确认启动：%w", err)
			}
			return errors.New("自动保活未能确认启动")
		}
		if err := waitForStateChange(ctx); err != nil {
			return err
		}
	}
}

func waitForStateChange(ctx context.Context) error {
	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-time.After(100 * time.Millisecond):
		return nil
	}
}
