package localstate

import (
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

const (
	sessionStateVersion = 1
	maxSessionIDRunes   = 256
	defaultSessionTTL   = 7 * 24 * time.Hour
)

type SessionMode string

const (
	SessionModeGlobal  SessionMode = "global"
	SessionModeDSH     SessionMode = "dsh"
	SessionModeEnv     SessionMode = "env"
	SessionModeInvalid SessionMode = "invalid"
)

type SessionScope struct {
	Mode SessionMode
	ID   string
	Err  error
}

type SessionSelection struct {
	Username     string `json:"username"`
	DepartmentID string `json:"department_id"`
	TenantID     string `json:"tenant_id"`
	TeamID       string `json:"team_id"`
	BusinessID   string `json:"businessId"`
}

func (s SessionSelection) toSelection() Selection {
	return Selection{
		DepartmentID: s.DepartmentID,
		TenantID:     s.TenantID,
		TeamID:       s.TeamID,
		BusinessID:   s.BusinessID,
	}
}

func sessionSelectionFrom(username string, sel Selection) SessionSelection {
	return SessionSelection{
		Username:     username,
		DepartmentID: sel.DepartmentID,
		TenantID:     sel.TenantID,
		TeamID:       sel.TeamID,
		BusinessID:   sel.BusinessID,
	}
}

type SessionState struct {
	Version    int                         `json:"version"`
	Source     string                      `json:"source"`
	SessionID  string                      `json:"session_id"`
	Current    string                      `json:"current"`
	Selections map[string]SessionSelection `json:"selections,omitempty"`
	UpdatedAt  time.Time                   `json:"updated_at"`
}

type sessionError struct {
	kind error
	msg  string
}

func (e sessionError) Error() string { return e.msg }
func (e sessionError) Unwrap() error { return e.kind }

var (
	ErrSessionInvalid         = errors.New("环境变量 ML_SESSION_ID 无效（不能为空、包含控制字符或超过 256 字符）")
	ErrDSHSessionMissing      = errors.New("检测到 DeepSeek Harness 托管环境（DSH_SHELL=1），但缺少有效的 DSH_SESSION_ID，已拒绝回退到全局配置以防多会话串台")
	ErrSessionEnvUnbound      = errors.New("当前会话尚未绑定环境，请先执行 ml env use <环境名>（可用 ml env list 查看可选环境）")
	ErrSessionBusinessUnbound = errors.New("当前会话尚未选择业务，请先执行 ml business use --tenant <租户ID>（可用 ml business list 查看可选业务）")
	ErrSessionBusinessInvalid = errors.New("当前会话的业务绑定已失效，请重新执行 ml business use --tenant <租户ID>")
)

func sessionBusinessUnboundError(profile string) error {
	if profile == "" {
		return ErrSessionBusinessUnbound
	}
	return sessionError{
		kind: ErrSessionBusinessUnbound,
		msg:  fmt.Sprintf("当前会话在环境 %s 下尚未选择业务，请先执行 ml business use --tenant <租户ID>（可用 ml business list 查看可选业务）", profile),
	}
}

func sessionBusinessInvalidError(profile string) error {
	if profile == "" {
		return ErrSessionBusinessInvalid
	}
	return sessionError{
		kind: ErrSessionBusinessInvalid,
		msg:  fmt.Sprintf("当前会话在环境 %s 下的业务绑定已失效（账号变化或权限变更），请重新执行 ml business use --tenant <租户ID>", profile),
	}
}

func DetectSessionScope(lookup func(string) (string, bool)) SessionScope {
	if lookup == nil {
		lookup = os.LookupEnv
	}
	if raw, ok := lookup("ML_SESSION_ID"); ok {
		if !validSessionID(raw) {
			return SessionScope{Mode: SessionModeInvalid, Err: ErrSessionInvalid}
		}
		return SessionScope{Mode: SessionModeEnv, ID: raw}
	}
	if shell, ok := lookup("DSH_SHELL"); ok && strings.TrimSpace(shell) == "1" {
		raw, exists := lookup("DSH_SESSION_ID")
		if !exists || !validSessionID(raw) {
			return SessionScope{Mode: SessionModeInvalid, Err: ErrDSHSessionMissing}
		}
		return SessionScope{Mode: SessionModeDSH, ID: raw}
	}
	return SessionScope{Mode: SessionModeGlobal}
}

func validSessionID(value string) bool {
	if value == "" || strings.TrimSpace(value) != value || utf8.RuneCountInString(value) > maxSessionIDRunes {
		return false
	}
	return strings.IndexFunc(value, unicode.IsControl) == -1
}

func (s SessionScope) EffectiveMode() SessionMode {
	if s.Mode == "" {
		return SessionModeGlobal
	}
	return s.Mode
}

func (s SessionScope) Isolated() bool {
	return s.Mode == SessionModeDSH || s.Mode == SessionModeEnv
}

func (s SessionScope) Label() string {
	switch s.EffectiveMode() {
	case SessionModeDSH:
		return "会话隔离 (dsh)"
	case SessionModeEnv:
		return "会话隔离 (env)"
	case SessionModeInvalid:
		return "会话异常"
	default:
		return "全局默认"
	}
}

func (p Paths) WithSession(scope SessionScope) Paths {
	p.Session = scope
	return p
}

func (p Paths) WithoutSession() Paths {
	p.Session = SessionScope{Mode: SessionModeGlobal}
	return p
}

func (p Paths) IsSessionIsolated() bool {
	return p.Session.Isolated()
}

func (p Paths) ValidateSession() error {
	return p.Session.Err
}

func (p Paths) SessionsDir() string {
	return filepath.Join(p.Dir, "sessions")
}

func (p Paths) SessionFile() string {
	if !p.IsSessionIsolated() {
		return ""
	}
	sum := sha256.Sum256([]byte(string(p.Session.Mode) + "\x00" + p.Session.ID))
	return filepath.Join(p.SessionsDir(), fmt.Sprintf("%x.json", sum[:16]))
}

func sessionLockName(stateFile string) string {
	id := strings.TrimSuffix(filepath.Base(stateFile), ".json")
	return filepath.Join("sessions", "locks", id+".lock")
}

func (p Paths) LockSession() (func(), error) {
	return p.lockSessionWithin(DefaultLockWait)
}

func (p Paths) lockSessionWithin(wait time.Duration) (func(), error) {
	if err := p.ValidateSession(); err != nil {
		return nil, err
	}
	if !p.IsSessionIsolated() {
		return nil, errors.New("当前未启用会话隔离")
	}
	return p.lockWithin(sessionLockName(p.SessionFile()), wait)
}

func (p Paths) LoadSessionState() (SessionState, bool, error) {
	if p.Session.Err != nil {
		return SessionState{}, false, p.Session.Err
	}
	if !p.IsSessionIsolated() {
		return SessionState{}, false, nil
	}
	path := p.SessionFile()
	contents, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return SessionState{
			Version:   sessionStateVersion,
			Source:    string(p.Session.Mode),
			SessionID: p.Session.ID,
		}, false, nil
	}
	if err != nil {
		return SessionState{}, false, fmt.Errorf("无法读取当前会话状态文件 %s", filepath.Base(path))
	}
	var state SessionState
	if err := json.Unmarshal(contents, &state); err != nil {
		return SessionState{}, false, fmt.Errorf("当前会话状态文件已损坏（%s），请重新执行 ml env use 绑定环境", filepath.Base(path))
	}
	if state.Version != sessionStateVersion || state.Source != string(p.Session.Mode) || state.SessionID != p.Session.ID {
		return SessionState{}, false, fmt.Errorf("当前会话状态文件元数据不匹配（%s），已拒绝回退到全局配置", filepath.Base(path))
	}
	return state, true, nil
}

func (p Paths) writeSessionStateLocked(state SessionState, now time.Time) error {
	if p.Session.Err != nil {
		return p.Session.Err
	}
	if !p.IsSessionIsolated() {
		return nil
	}
	state.Version = sessionStateVersion
	state.Source = string(p.Session.Mode)
	state.SessionID = p.Session.ID
	state.UpdatedAt = now.UTC()
	return writeState(p.SessionFile(), state)
}

func (p Paths) UpdateSessionState(mutate func(*SessionState) error) error {
	if p.Session.Err != nil {
		return p.Session.Err
	}
	if !p.IsSessionIsolated() {
		return nil
	}
	unlock, err := p.LockSession()
	if err != nil {
		return err
	}
	defer unlock()
	state, _, err := p.LoadSessionState()
	if err != nil {
		return err
	}
	if err := mutate(&state); err != nil {
		return err
	}
	return p.writeSessionStateLocked(state, time.Now())
}

func (p Paths) setSessionEnvironment(name string) error {
	if p.Session.Err != nil {
		return p.Session.Err
	}
	if !p.IsSessionIsolated() {
		return nil
	}
	unlock, err := p.LockSession()
	if err != nil {
		return err
	}
	defer unlock()
	state, _, err := p.LoadSessionState()
	if err != nil {
		// Allow explicit `ml env use` to recover a damaged session file cleanly.
		state = SessionState{}
	}
	state.Current = name
	return p.writeSessionStateLocked(state, time.Now())
}
