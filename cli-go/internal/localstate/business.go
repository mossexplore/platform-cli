package localstate

import (
	"encoding/json"
	"errors"
	"os"
	"strings"
	"time"
)

type Credentials struct {
	Origin      string          `json:"platform_origin"`
	StateID     string          `json:"state_id"`
	Profile     string          `json:"profile"`
	Username    string          `json:"username"`
	Cookie      string          `json:"cookie"`
	CSRFToken   string          `json:"csrftoken"`
	AcquiredAt  json.RawMessage `json:"acquired_at,omitempty"`
	ChineseName string          `json:"cn_name,omitempty"`
	Department  string          `json:"department,omitempty"`
	ExpiresAt   json.RawMessage `json:"expires_at"`
}

type credentialFile struct {
	Profiles map[string]Credentials `json:"profiles"`
}

func (p Paths) CredentialsFor(profile Profile) (Credentials, error) {
	var file credentialFile
	if err := readJSON(p.Credentials(), &file); err != nil {
		return Credentials{}, err
	}
	creds, exists := file.Profiles[profile.Name]
	if !exists {
		return Credentials{}, errors.New("当前环境缺少可用的预览登录缓存")
	}
	if creds.Profile != profile.Name || creds.Origin != profile.Origin() ||
		!identifier.MatchString(creds.StateID) || !validHeader(creds.Username) || !validHeader(creds.Cookie) ||
		!validHeader(creds.CSRFToken) {
		return Credentials{}, errors.New("当前环境的登录缓存无效")
	}
	return creds, nil
}

func (p Paths) LoadCredentials(profile Profile, now time.Time) (Credentials, error) {
	creds, err := p.CredentialsFor(profile)
	if err != nil {
		return Credentials{}, err
	}
	expiry, err := creds.Expiry()
	if err != nil {
		return Credentials{}, err
	}
	if !now.Before(expiry) {
		return Credentials{}, errors.New("当前环境的登录缓存已过期")
	}
	return creds, nil
}

func (c Credentials) Expiry() (time.Time, error)   { return parseCacheTime(c.ExpiresAt) }
func (c Credentials) Acquired() (time.Time, error) { return parseCacheTime(c.AcquiredAt) }

func parseCacheTime(value json.RawMessage) (time.Time, error) {
	var text string
	if json.Unmarshal(value, &text) == nil && text != "" {
		instant, err := time.Parse(time.RFC3339Nano, strings.Replace(text, " ", "T", 1))
		if err == nil {
			return instant, nil
		}
	}
	var seconds float64
	if json.Unmarshal(value, &seconds) == nil && seconds > 0 && seconds < 253402300800 {
		return time.Unix(int64(seconds), int64((seconds-float64(int64(seconds)))*1e9)), nil
	}
	return time.Time{}, errors.New("登录缓存有效期格式无效")
}

type Department struct {
	Name    string   `json:"name,omitempty"`
	ID      string   `json:"id"`
	Tenants []Tenant `json:"tenants"`
}

type Tenant struct {
	Name  string `json:"name,omitempty"`
	ID    string `json:"id"`
	Teams []Team `json:"teams"`
}

type Team struct {
	Name       string `json:"name,omitempty"`
	ID         string `json:"id"`
	Key        string `json:"key"`
	Status     string `json:"status"`
	BusinessID string `json:"businessId"`
}

type Selection struct {
	DepartmentID string `json:"department_id"`
	TenantID     string `json:"tenant_id"`
	TeamID       string `json:"team_id"`
	BusinessID   string `json:"businessId"`
}

type businessFile struct {
	Version  int                      `json:"version"`
	Profiles map[string]BusinessEntry `json:"profiles"`
}

type BusinessEntry struct {
	Username string       `json:"username"`
	StateID  string       `json:"state_id"`
	Catalog  []Department `json:"catalog"`
	Selected Selection    `json:"selected"`
}

func (p Paths) BusinessEntry(creds Credentials) (BusinessEntry, error) {
	var file businessFile
	if err := readJSON(p.Business(), &file); err != nil {
		return BusinessEntry{}, err
	}
	return file.entry(creds, p.BusinessOverride != "")
}

func (file businessFile) entry(creds Credentials, allowLegacy bool) (BusinessEntry, error) {
	if file.Version != 2 {
		return BusinessEntry{}, errors.New("business.json 版本不兼容")
	}
	entry := file.Profiles[creds.Profile]
	if entry.Username != creds.Username || entry.StateID != creds.StateID && !(allowLegacy && entry.StateID == "") {
		return BusinessEntry{}, errors.New("当前环境的业务目录与登录账号不匹配")
	}
	return entry, nil
}

func (p Paths) SelectedBusiness(creds Credentials) (string, error) {
	entry, err := p.BusinessEntry(creds)
	if err != nil {
		return "", err
	}
	saved := entry.Selected
	if !validHeader(saved.BusinessID) || !matchesSelection(entry.Catalog, saved) {
		return "", errors.New("当前环境 selected.businessId 无效或业务选择已失效")
	}
	return saved.BusinessID, nil
}

func matchesSelection(departments []Department, selected Selection) bool {
	for _, department := range departments {
		if department.ID != selected.DepartmentID {
			continue
		}
		for _, tenant := range department.Tenants {
			if tenant.ID != selected.TenantID {
				continue
			}
			if selected.TeamID == "" {
				return tenant.ID == selected.BusinessID
			}
			for _, team := range tenant.Teams {
				if (team.ID == selected.TeamID || team.Key == selected.TeamID) &&
					team.Status == "available" && team.BusinessID == selected.BusinessID {
					return true
				}
			}
		}
	}
	return false
}

func validHeader(value string) bool {
	return strings.TrimSpace(value) == value && value != "" && strings.IndexFunc(value, func(r rune) bool { return r < 32 || r == 127 }) == -1
}

func readJSON(path string, target any) error {
	contents, err := os.ReadFile(path)
	if err != nil {
		return errors.New("无法读取状态文件: " + path)
	}
	if err := json.Unmarshal(contents, target); err != nil {
		return errors.New("状态文件 JSON 无效: " + path)
	}
	return nil
}

func (p Paths) ExtendCredentials(profile Profile, current Credentials, businessID, cookie, token string, ttl time.Duration) error {
	unlock, err := p.LockState()
	if err != nil {
		return err
	}
	defer unlock()
	latest, err := p.CredentialsFor(profile)
	if err != nil {
		return err
	}
	if latest.StateID != current.StateID || latest.Username != current.Username || latest.Cookie != current.Cookie || latest.CSRFToken != current.CSRFToken {
		return errors.New("登录会话已由其他命令更新")
	}
	id, err := p.SelectedBusiness(latest)
	if err != nil || id != businessID {
		return errors.New("保活期间业务上下文已变化")
	}
	if cookie != "" && validHeader(cookie) {
		latest.Cookie = cookie
	}
	if token != "" && validHeader(token) {
		latest.CSRFToken = token
	}
	if expires, err := latest.Expiry(); err != nil || time.Until(expires) <= ttl {
		stamp, err := json.Marshal(time.Now().Add(ttl))
		if err != nil {
			return err
		}
		latest.ExpiresAt = stamp
	}
	var file credentialFile
	if err := readJSON(p.Credentials(), &file); err != nil {
		return err
	}
	file.Profiles[profile.Name] = latest
	return writeState(p.Credentials(), file)
}
