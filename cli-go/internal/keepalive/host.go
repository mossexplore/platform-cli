package keepalive

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const HostProtocol = "dsh-keepalive-v1"
const hostLifetime = 10 * time.Minute
const maximumHostInput = 4096

type HostRequest struct {
	Protocol  string `json:"protocol"`
	Action    string `json:"action"`
	HostID    string `json:"host_id"`
	SessionID string `json:"session_id"`
}

type TickResult struct {
	Protocol    string `json:"protocol"`
	State       string `json:"state"`
	Environment string `json:"env,omitempty"`
	RequestID   string `json:"request_id,omitempty"`
	NextAttempt string `json:"next_attempt,omitempty"`
}

type hostRegistration struct {
	SessionID string    `json:"session_id"`
	Profile   string    `json:"profile,omitempty"`
	Seen      time.Time `json:"seen"`
}

func (host hostRegistration) active(now time.Time) bool {
	return !host.Seen.IsZero() && now.Before(host.Seen.Add(hostLifetime))
}

func (host hostRegistration) scope() localstate.SessionScope {
	return localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: host.SessionID}
}

func displayTime(value time.Time) string {
	if value.IsZero() {
		return ""
	}
	return value.In(time.FixedZone("Asia/Shanghai", 8*60*60)).Format("2006-01-02 15:04:05")
}

func DecodeHostRequest(reader io.Reader) (HostRequest, error) {
	var request HostRequest
	data, err := io.ReadAll(io.LimitReader(reader, maximumHostInput+1))
	if err != nil || len(data) > maximumHostInput {
		return request, errors.New("宿主请求不可读或超过长度限制")
	}
	decoder := json.NewDecoder(strings.NewReader(string(data)))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&request) != nil || decoder.Decode(new(any)) != io.EOF || !request.valid() {
		return HostRequest{}, errors.New("宿主请求格式或协议无效")
	}
	return request, nil
}

func (request HostRequest) valid() bool {
	return request.Protocol == HostProtocol && (request.Action == "tick" || request.Action == "release") &&
		validHostID(request.HostID) && detectHostScope(request.SessionID).Mode == localstate.SessionModeDSH
}

func validHostID(id string) bool {
	if len(id) == 0 || len(id) > 64 {
		return false
	}
	for _, ch := range id {
		if !(ch >= 'a' && ch <= 'z' || ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' || ch == '-') {
			return false
		}
	}
	return true
}

func detectHostScope(id string) localstate.SessionScope {
	return localstate.DetectSessionScope(func(key string) (string, bool) {
		switch key {
		case "DSH_SHELL":
			return "1", true
		case "DSH_SESSION_ID":
			if strings.TrimSpace(id) == id {
				return id, true
			}
		}
		return "", false
	})
}

func HostBudgetMS(paths localstate.Paths) int64 {
	cfg, err := localstate.LoadConfig(paths.WithoutSession())
	if err != nil {
		cfg.API.TimeoutMS = 30000
	}
	return (probeBudget(cfg) + 2*localstate.DefaultLockWait).Milliseconds()
}

func Tick(ctx context.Context, base localstate.Paths, request HostRequest, version string) (result TickResult, err error) {
	var environment string
	defer func() {
		result.Protocol = HostProtocol
		result.Environment = environment
	}()
	if !request.valid() || base.Session.EffectiveMode() != localstate.SessionModeGlobal {
		return TickResult{State: "invalid_request"}, nil
	}
	key := request.HostID + ":" + request.SessionID
	if request.Action == "release" {
		err := updateRegistry(base, localstate.DefaultLockWait, func(data entryFile) error {
			host := data.Hosts[key]
			delete(data.Hosts, key)
			cancelHostRequest(data, host.Profile, key)
			return nil
		})
		return TickResult{State: "released"}, err
	}

	paths := base.WithSession(detectHostScope(request.SessionID))
	state, exists, stateErr := paths.LoadSessionState()
	if stateErr != nil || !exists {
		return TickResult{State: "unknown_session"}, nil
	}
	if err := updateRegistry(base, localstate.DefaultLockWait, func(data entryFile) error {
		if err := ctx.Err(); err != nil {
			return err
		}
		previous := data.Hosts[key]
		if previous.Profile != state.Current {
			cancelHostRequest(data, previous.Profile, key)
		}
		data.Hosts[key] = hostRegistration{SessionID: request.SessionID, Profile: state.Current, Seen: time.Now()}
		return nil
	}); err != nil {
		return TickResult{}, err
	}
	defer MaintainSessions(paths)
	if state.Current == "" {
		return TickResult{State: "unbound"}, nil
	}
	cfg, err := localstate.LoadConfig(base)
	if err != nil {
		return TickResult{}, err
	}
	cfg.Current = state.Current
	profile, err := cfg.RequireProfile()
	if err != nil {
		return TickResult{State: "unbound"}, nil
	}
	environment = profile.Name
	if !hostAllowed(cfg, profile) {
		return TickResult{State: "disabled"}, nil
	}
	creds, err := paths.LoadCredentials(profile, time.Now())
	if err != nil {
		return TickResult{State: "login_unavailable"}, nil
	}
	target, err := paths.KeepaliveTarget(creds)
	if err != nil {
		return TickResult{State: "waiting_business"}, nil
	}
	return (probeJob{paths: paths, cfg: cfg, creds: creds, target: target, version: version, hostKey: key}).run(ctx)
}

func cancelHostRequest(data entryFile, profile, hostKey string) {
	if entry := data.Profiles[profile]; entry.InFlight.Host == hostKey {
		entry.InFlight.Cancelled = true
		data.Profiles[profile] = entry
	}
}

func hostAllowed(cfg localstate.Config, profile localstate.Profile) bool {
	return cfg.PingEnabled() && !localstate.Denied("auth ping start", profile.Policy.Deny) &&
		!localstate.Denied("auth ping tick", profile.Policy.Deny)
}

func hostSeen(data entryFile, scope localstate.SessionScope, profile string) time.Time {
	var seen time.Time
	for _, registration := range data.Hosts {
		if registration.SessionID == scope.ID && registration.Profile == profile {
			seen = maxTime(seen, registration.Seen)
		}
	}
	return seen
}

func ResumeHost(paths localstate.Paths, cfg localstate.Config) (string, error) {
	profile, err := cfg.RequireProfile()
	if err != nil {
		return "", err
	}
	if !hostAllowed(cfg, profile) {
		return "当前环境禁止自动保活", nil
	}
	message := "请安装并启用 DeepSeek Harness 保活插件，等待插件登记当前会话"
	err = updateRegistry(paths, localstate.DefaultLockWait, func(data entryFile) error {
		if time.Since(hostSeen(data, paths.Session, profile.Name)) >= hostLifetime {
			return nil
		}
		creds, err := paths.LoadCredentials(profile, time.Now())
		if err != nil {
			message = "当前环境未登录，请执行 ml login 登录该环境"
			return nil
		}
		if _, err := paths.KeepaliveTarget(creds); err != nil {
			message = "尚未选择业务，请选择业务后重试"
			return nil
		}
		entry := data.Profiles[profile.Name]
		entry.ManualStop = false
		data.Profiles[profile.Name] = entry
		message = "已允许当前环境自动保活，等待 DeepSeek Harness 插件调度"
		return nil
	})
	return message, err
}

type HostStatus struct {
	State string
	Seen  time.Time
	Next  time.Time
	Entry Entry
}

func ViewHost(paths localstate.Paths, cfg localstate.Config, now time.Time) (HostStatus, error) {
	data, err := load(paths)
	if err != nil {
		return HostStatus{}, err
	}
	profile := cfg.Profile()
	entry := data.Profiles[profile.Name]
	seen := hostSeen(data, paths.Session, profile.Name)
	status := HostStatus{Seen: seen, Entry: entry}
	creds, loginErr := paths.LoadCredentials(profile, now)
	_, targetErr := paths.KeepaliveTarget(creds)
	switch {
	case !hostAllowed(cfg, profile):
		status.State = "自动保活已关闭"
	case entry.ManualStop:
		status.State = "已手动停止"
	case seen.IsZero():
		status.State = "插件尚未登记"
	case !now.Before(seen.Add(hostLifetime)):
		status.State = "插件调度已过期"
	case profile.Name == "":
		status.State = "等待绑定环境"
	case loginErr != nil:
		status.State = "登录不可用"
	case targetErr != nil:
		status.State = "等待有效业务上下文"
	case entry.ExpiredState == creds.StateID:
		status.State = "平台会话已失效"
	case alive(entry) && entry.Protocol != workerProtocol:
		status.State = "等待旧版保活进程退出"
	default:
		status.State = "DSH 插件托管"
		if !entry.InFlight.active(now) {
			status.Next = maxTime(now, maxTime(entry.LastActivity.Add(time.Duration(cfg.Auth.PingMinutes)*time.Minute), entry.RetryAt))
		}
	}
	return status, nil
}
