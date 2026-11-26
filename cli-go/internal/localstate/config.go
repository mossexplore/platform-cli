package localstate

import (
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"fmt"
	"net"
	"net/url"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"time"
	"unicode/utf8"
)

type Paths struct {
	Dir              string
	BusinessOverride string
	Session          SessionScope
	packaged         *Config
}

// The packaging script overlays this placeholder with the validated build input.
//
//go:embed config.embedded.json
var packagedConfig []byte

func DefaultPaths() (Paths, error) {
	// Keep the Go client's state independent of the Python client.
	root, err := os.UserConfigDir()
	if err != nil {
		return Paths{}, errors.New("无法定位当前账号的用户配置目录")
	}
	paths, err := NewPaths(filepath.Join(root, "ml-go-preview"), packagedConfig)
	if err != nil {
		return Paths{}, err
	}
	paths.Session = DetectSessionScope(os.LookupEnv)
	return paths, nil
}

func NewPaths(dir string, packaged []byte) (Paths, error) {
	cfg, err := decodeConfig(packaged)
	if err != nil {
		return Paths{}, fmt.Errorf("Go CLI 内置配置无效，请使用完整的安装包: %w", err)
	}
	return Paths{Dir: dir, packaged: &cfg}, nil
}

func (p Paths) Config() string      { return filepath.Join(p.Dir, "config.json") }
func (p Paths) Credentials() string { return filepath.Join(p.Dir, "credentials.json") }
func (p Paths) Business() string {
	if p.BusinessOverride != "" {
		return p.BusinessOverride
	}
	return filepath.Join(p.Dir, "business.json")
}
func (p Paths) ConfigRelative(filename string) string {
	if home, err := os.UserHomeDir(); err == nil && (strings.HasPrefix(filename, "~/") || strings.HasPrefix(filename, "~\\")) {
		return filepath.Join(home, filename[2:])
	}
	if filepath.IsAbs(filename) {
		return filename
	}
	return filepath.Join(p.Dir, filename)
}

type Config struct {
	Current                    string    `json:"current"`
	Profiles                   []Profile `json:"profiles"`
	DefaultVisibleEnvironments []string  `json:"default_visible_environments"`
	API                        struct {
		TimeoutMS int   `json:"timeout"`
		VerifyTLS *bool `json:"verify_ssl"`
	} `json:"api"`
	Auth struct {
		TTLSeconds  int   `json:"expires_in_seconds"`
		AutoPing    *bool `json:"auto_ping"`
		PingMinutes int   `json:"ping_interval_minutes"`
	} `json:"auth"`
	Browser struct {
		LoginTimeoutMS int `json:"login_timeout"`
	} `json:"browser"`
	Knowledge KnowledgeBase `json:"knowledge_base"`
	Access    Access        `json:"access_control"`
}

type Profile struct {
	Alias        string        `json:"alias"`
	Name         string        `json:"name"`
	Endpoint     string        `json:"api_endpoint"`
	PlatformType string        `json:"platform_type"`
	VerifyTLS    *bool         `json:"verify_ssl"`
	Output       string        `json:"output_format"`
	Jupyter      JupyterConfig `json:"jupyter"`
	Policy       struct {
		Deny []string `json:"deny"`
	} `json:"command_policy"`
}

type JupyterConfig struct {
	Mode         string            `json:"mode"`
	ServerURL    string            `json:"server_url"`
	Gateways     map[string]string `json:"server_urls_by_region"`
	TokenEnv     string            `json:"token_env"`
	TokenFile    string            `json:"token_file"`
	BusinessFile string            `json:"business_file"`
	CAFile       string            `json:"ca_file"`
	Kernel       string            `json:"kernel"`
}

type Access struct {
	URL         string  `json:"url"`
	Enable      *bool   `json:"enable"`
	EnabledOld  *bool   `json:"enabled"`
	TimeoutSecs float64 `json:"timeout_seconds"`
	UseEnvProxy bool    `json:"use_env_proxy"`
	CASource    string  `json:"ca_source"`
	CAFile      string  `json:"ca_file"`
}

func LoadConfig(paths Paths) (Config, error) {
	cfg, _, err := paths.loadConfig()
	return cfg, err
}

func ValidateConfigFile(path string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	if _, err := decodeConfig(data); err != nil {
		return fmt.Errorf("打包配置无效: %s（%w）", path, err)
	}
	return nil
}

func decodeConfig(data []byte) (Config, error) {
	cfg := Config{}
	cfg.API.TimeoutMS = 30000
	cfg.Auth.TTLSeconds = 1800
	cfg.Auth.PingMinutes = 10
	cfg.Browser.LoginTimeoutMS = 300000
	cfg.Access.TimeoutSecs = 15
	cfg.Access.CASource = "env"
	if err := json.Unmarshal(bytes.TrimPrefix(data, []byte("\xef\xbb\xbf")), &cfg); err != nil {
		return Config{}, errors.New("配置不是有效的 JSON 或字段类型不符")
	}
	if err := cfg.validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

func (c *Config) validate() error {
	if c.Current == "" || len(c.Profiles) == 0 {
		return errors.New("须配置 current 和 profiles")
	}
	seen := make(map[string]bool)
	for i := range c.Profiles {
		profile := &c.Profiles[i]
		if profile.Name == "" || seen[profile.Name] {
			return errors.New("配置中的环境标识不能为空或重复")
		}
		seen[profile.Name] = true
		endpoint, err := parseHTTPURL(profile.Endpoint)
		if err != nil || endpoint.User != nil {
			return fmt.Errorf("环境 %q 的 api_endpoint 无效或含凭据", profile.Name)
		}
		if profile.PlatformType == "" {
			profile.PlatformType = "wiserec"
		}
		if profile.PlatformType != "wiserec" && profile.PlatformType != "mlops" {
			return fmt.Errorf("环境 %q 的 platform_type 仅支持 wiserec 或 mlops", profile.Name)
		}
		if profile.Output == "" {
			profile.Output = "table"
		}
		if err := validateDeny(profile.Policy.Deny); err != nil {
			return fmt.Errorf("环境 %q 的禁止命令规则无效: %w", profile.Name, err)
		}
	}
	if !seen[c.Current] {
		return errors.New("profiles 中不存在 current 指定的环境")
	}
	visible := make(map[string]bool)
	for _, name := range c.DefaultVisibleEnvironments {
		if !seen[name] || visible[name] {
			return fmt.Errorf("default_visible_environments 中的环境标识 %q 不存在或重复", name)
		}
		visible[name] = true
	}
	if c.API.TimeoutMS <= 0 || int64(c.API.TimeoutMS) > int64((1<<63-1)/time.Millisecond) {
		return errors.New("api.timeout 超出有效范围")
	}
	if c.Auth.TTLSeconds <= 0 || int64(c.Auth.TTLSeconds) > int64((1<<63-1)/time.Second) {
		return errors.New("auth.expires_in_seconds 超出有效范围")
	}
	if c.Auth.PingMinutes <= 0 || int64(c.Auth.PingMinutes) > int64((1<<63-1)/time.Minute) {
		return errors.New("auth.ping_interval_minutes 超出有效范围")
	}
	if c.Browser.LoginTimeoutMS <= 0 || int64(c.Browser.LoginTimeoutMS) > int64((1<<63-1)/time.Millisecond) {
		return errors.New("browser.login_timeout 超出有效范围")
	}
	if err := c.Knowledge.validate(c.Access.URL); err != nil {
		return err
	}
	return c.Access.validate()
}

var commandPath = regexp.MustCompile(`^[a-z0-9][a-z0-9-]*( [a-z0-9][a-z0-9-]*)*$`)

func validateDeny(rules []string) error {
	if len(rules) > 500 {
		return errors.New("最多允许 500 条规则")
	}
	seen := make(map[string]bool)
	for _, rule := range rules {
		path := strings.TrimPrefix(rule, "ml ")
		if utf8.RuneCountInString(rule) > 128 || !commandPath.MatchString(path) || seen[path] {
			return errors.New("规则须使用不重复的命令路径，最多 128 字符")
		}
		seen[path] = true
	}
	return nil
}

func (c Config) Profile() Profile {
	for _, profile := range c.Profiles {
		if profile.Name == c.Current {
			return profile
		}
	}
	return Profile{}
}

func (c Config) RequireProfile() (Profile, error) {
	if c.Current == "" {
		return Profile{}, ErrSessionEnvUnbound
	}
	profile := c.Profile()
	if profile.Name == "" {
		return Profile{}, ErrSessionEnvUnbound
	}
	return profile, nil
}

func (p Profile) Origin() string {
	endpoint, _ := url.Parse(p.Endpoint)
	host := strings.ToLower(endpoint.Hostname())
	port := endpoint.Port()
	if port != "" {
		host = net.JoinHostPort(host, port)
	} else if strings.Contains(host, ":") {
		host = "[" + host + "]"
	}
	return (&url.URL{Scheme: endpoint.Scheme, Host: host}).String()
}

func (p Profile) PublicEndpoint() string {
	endpoint, _ := url.Parse(p.Endpoint)
	endpoint.User, endpoint.Fragment, endpoint.RawFragment = nil, "", ""
	endpoint.RawQuery, endpoint.ForceQuery = "", false
	return endpoint.String()
}

func Denied(path string, rules []string) bool {
	for _, rule := range rules {
		rule = strings.TrimPrefix(rule, "ml ")
		if path == rule || strings.HasPrefix(path, rule+" ") {
			return true
		}
	}
	return false
}

func (a Access) Active() bool {
	if a.Enable != nil {
		return *a.Enable
	}
	return a.EnabledOld == nil || *a.EnabledOld
}

func (a Access) validate() error {
	if a.Enable != nil && a.EnabledOld != nil {
		return errors.New("access_control.enable 和 enabled 不能同时设置")
	}
	if a.TimeoutSecs < 1 || a.TimeoutSecs > 120 {
		return errors.New("access_control.timeout_seconds 必须在 1–120 秒之间")
	}
	if a.CASource != "env" && a.CASource != "custom" && a.CASource != "certifi" {
		return errors.New("access_control.ca_source 必须为 certifi、env 或 custom")
	}
	if a.CASource == "custom" && !filepath.IsAbs(a.CAFile) {
		return errors.New("custom CA 模式须提供 ca_file 的绝对路径")
	}
	if a.CASource != "custom" && a.CAFile != "" {
		return errors.New("ca_file 仅可与 custom CA 模式一起使用")
	}
	if a.Active() && (a.URL != "" || a.Enable != nil || a.EnabledOld != nil) {
		endpoint, err := parseHTTPURL(a.URL)
		if err != nil || endpoint.User != nil || endpoint.RawQuery != "" || endpoint.ForceQuery ||
			endpoint.Fragment != "" || (endpoint.EscapedPath() != "" && endpoint.EscapedPath() != "/" &&
			endpoint.EscapedPath() != "/cli-permission" && endpoint.EscapedPath() != "/cli-permission/") {
			return errors.New("access_control.url 必须为 HTTP(S) 地址，路径仅允许 /cli-permission，且不含凭据、查询或片段")
		}
	}
	return nil
}

func parseHTTPURL(value string) (*url.URL, error) {
	endpoint, err := url.Parse(value)
	if err != nil || endpoint.Hostname() == "" || (endpoint.Scheme != "http" && endpoint.Scheme != "https") {
		return nil, errors.New("无效 HTTP(S) 地址")
	}
	return endpoint, nil
}

func (c Config) PingEnabled() bool { return c.Auth.AutoPing == nil || *c.Auth.AutoPing }
