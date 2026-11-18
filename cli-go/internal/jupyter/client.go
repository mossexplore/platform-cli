package jupyter

import (
	"bytes"
	"context"
	"crypto/tls"
	"crypto/x509"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/http/cookiejar"
	"net/url"
	"os"
	"strings"
	"time"
	"unicode"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

type Client struct {
	root   *url.URL
	token  string
	api    *platform.API
	http   *http.Client
	kernel string
	studio string
}

func Open(ctx context.Context, api *platform.API, paths localstate.Paths, cfg localstate.Config, studioID string) (*Client, error) {
	settings := cfg.Profile().Jupyter
	if settings.Mode == "webstudio" {
		return openStudio(ctx, api, paths, cfg, studioID, false)
	}
	if settings.Mode != "" && settings.Mode != "direct" {
		return nil, errors.New("jupyter.mode 仅支持 direct 或 webstudio")
	}
	if studioID != "" {
		return nil, errors.New("--studio-id 需要 jupyter.mode=webstudio")
	}
	address := settings.ServerURL
	if address == "" {
		address = cfg.Profile().Endpoint
	}
	tokenEnv := settings.TokenEnv
	if tokenEnv == "" {
		tokenEnv = "ML_JUPYTER_TOKEN"
	}
	token := os.Getenv(tokenEnv)
	if token == "" && settings.TokenFile != "" {
		data, err := os.ReadFile(paths.ConfigRelative(settings.TokenFile))
		if err != nil {
			return nil, errors.New("无法读取当前环境的 Jupyter token_file")
		}
		token = strings.TrimSpace(strings.TrimPrefix(string(data), "\ufeff"))
	}
	if token == "" || strings.IndexFunc(token, unicode.IsControl) >= 0 {
		return nil, errors.New("请设置当前环境的 Jupyter token_env 或 token_file")
	}
	return newClient(api, paths, cfg, address, token)
}

func newClient(api *platform.API, paths localstate.Paths, cfg localstate.Config, address, token string) (*Client, error) {
	root, err := url.Parse(address)
	if err != nil || root.User != nil || root.Hostname() == "" || root.RawQuery != "" || root.ForceQuery || root.Fragment != "" ||
		(root.Scheme != "http" && root.Scheme != "https") {
		return nil, errors.New("Jupyter server_url 须为不含凭据、查询参数或片段的 HTTP(S) 地址")
	}
	root.Path = strings.TrimRight(root.Path, "/") + "/"
	root.RawPath = ""
	profile := cfg.Profile()
	verify := profile.VerifyTLS
	if verify == nil {
		verify = cfg.API.VerifyTLS
	}
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	tlsConfig := &tls.Config{}
	if profile.Jupyter.CAFile != "" {
		ca, err := os.ReadFile(paths.ConfigRelative(profile.Jupyter.CAFile))
		if err != nil {
			return nil, errors.New("无法读取 Jupyter CA 文件")
		}
		tlsConfig.RootCAs = x509.NewCertPool()
		if !tlsConfig.RootCAs.AppendCertsFromPEM(ca) {
			return nil, errors.New("Jupyter CA 文件不含有效证书")
		}
	} else if verify != nil && !*verify {
		tlsConfig.InsecureSkipVerify = true // Existing per-profile TLS option.
	}
	transport.TLSClientConfig = tlsConfig
	jar, err := cookiejar.New(nil)
	if err != nil {
		return nil, err
	}
	kernel := profile.Jupyter.Kernel
	if kernel == "" {
		kernel = "python3"
	}
	return &Client{root: root, token: token, api: api, kernel: kernel, http: &http.Client{
		Transport: transport, Jar: jar, Timeout: time.Duration(cfg.API.TimeoutMS) * time.Millisecond,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}}, nil
}

func (c *Client) Close()         { c.http.CloseIdleConnections() }
func (c *Client) Kernel() string { return c.kernel }
func (c *Client) Result(data any) map[string]any {
	return map[string]any{"server_url": c.root.String(), "studio_id": c.studio, "business_id": c.api.BusinessID(), "result": data}
}

type StatusError struct{ Code int }

func (e StatusError) Error() string { return fmt.Sprintf("Jupyter 请求失败（HTTP %d）", e.Code) }

func (c *Client) request(ctx context.Context, method, endpoint string, query url.Values, body any) (*http.Response, error) {
	address := *c.root
	relative, err := url.Parse(endpoint)
	if err != nil || relative.IsAbs() || relative.Host != "" || strings.HasPrefix(relative.Path, "/") ||
		strings.Contains(relative.Path, "\\") {
		return nil, errors.New("Jupyter 请求路径无效")
	}
	for _, part := range strings.Split(relative.Path, "/") {
		if part == "." || part == ".." {
			return nil, errors.New("Jupyter 请求路径无效")
		}
	}
	address.Path += relative.Path
	address.RawQuery = query.Encode()
	var reader io.Reader
	if body != nil {
		data, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = bytes.NewReader(data)
	}
	request, err := http.NewRequestWithContext(ctx, method, address.String(), reader)
	if err != nil {
		return nil, errors.New("Jupyter 请求无效")
	}
	request.Header = c.api.RequestMetadata()
	if c.token != "" {
		request.Header.Set("Authorization", "token "+c.token)
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}
	if method != http.MethodGet {
		unlock, err := c.api.LockTarget()
		if err != nil {
			return nil, err
		}
		defer unlock()
		for _, cookie := range c.http.Jar.Cookies(&address) {
			if cookie.Name == "_xsrf" {
				request.Header.Set("X-XSRFToken", cookie.Value)
				break
			}
		}
	}
	response, err := c.http.Do(request)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, errors.New("Jupyter 网络请求失败")
	}
	return response, nil
}

func (c *Client) JSON(ctx context.Context, method, endpoint string, query url.Values, body any) (json.RawMessage, error) {
	response, err := c.request(ctx, method, endpoint, query, body)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	const maximum = 80 << 20
	data, err := io.ReadAll(io.LimitReader(response.Body, maximum+1))
	if err != nil || len(data) > maximum {
		return nil, errors.New("Jupyter 响应读取失败或超出大小上限")
	}
	if err := c.api.CheckVersion(data); err != nil {
		return nil, err
	}
	if response.StatusCode < 200 || response.StatusCode >= 300 {
		return nil, StatusError{response.StatusCode}
	}
	if len(data) == 0 || response.StatusCode == http.StatusNoContent {
		return json.RawMessage("null"), nil
	}
	if !json.Valid(data) {
		return nil, errors.New("Jupyter 未返回 JSON，请核对代理地址与登录状态")
	}
	return data, nil
}

func (c *Client) bootstrap(ctx context.Context) error {
	query := url.Values{}
	if c.token != "" {
		query.Set("token", c.token)
	}
	response, err := c.request(ctx, http.MethodGet, "lab", query, nil)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK && response.StatusCode != http.StatusFound && response.StatusCode != http.StatusSeeOther {
		return fmt.Errorf("Jupyter 会话初始化失败（HTTP %d）", response.StatusCode)
	}
	return nil
}
