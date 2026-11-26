package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"reflect"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

var ErrTargetChanged = errors.New("执行期间环境、账号或业务已变化，请重新核对后执行")

type API struct {
	session     Session
	profile     localstate.Profile
	credentials localstate.Credentials
	businessID  string
	command     string
	audit       string
	metadata    invocation
	client      *http.Client
	used        bool
	confirmed   bool
}

func (s Session) Authorize(ctx context.Context, command, audit string) (*API, error) {
	profile, err := s.Config.RequireProfile()
	if err != nil {
		return nil, err
	}
	if localstate.Denied(command, profile.Policy.Deny) {
		return nil, fmt.Errorf("当前环境 %s 禁止执行 ml %s", profile.Name, command)
	}
	if !s.Config.Access.Active() || s.Config.Access.URL == "" {
		return nil, errors.New("Go 客户端的业务命令需要启用并配置在线权限校验")
	}
	credentials, err := s.Paths.LoadCredentials(profile, time.Now())
	if err != nil {
		return nil, err
	}
	businessID, err := s.Paths.SelectedBusiness(credentials)
	if err != nil {
		return nil, err
	}
	if audit == "" {
		audit = "ml " + command
	}
	metadata := invocation{
		version: s.CLIVersion, id: localstate.NewID(), installation: s.Paths.InstallationID(), stderr: s.Stderr,
	}
	if err := s.requireAccess(ctx, &metadata, profile, credentials.Username, businessID, command, audit); err != nil {
		return nil, err
	}
	return &API{
		session: s, profile: profile, credentials: credentials, businessID: businessID,
		command: command, audit: audit, metadata: metadata, client: businessTransport(s.Config),
	}, nil
}

func (a *API) BusinessID() string                         { return a.businessID }
func (a *API) Username() string                           { return a.credentials.Username }
func (a *API) PlatformType() string                       { return a.profile.PlatformType }
func (a *API) CheckTarget() error                         { return a.checkTarget() }
func (a *API) RequestMetadata() http.Header               { return a.metadata.headers(a.businessID) }
func (a *API) CheckVersion(payload json.RawMessage) error { return a.metadata.checkVersion(payload) }
func (a *API) SetMinimumTimeout(timeout time.Duration) {
	if a.client.Timeout < timeout {
		a.client.Timeout = timeout
	}
}
func (a *API) Close() { a.client.CloseIdleConnections() }

func (a *API) endpoint(path string, query url.Values) (string, error) {
	address, err := url.Parse(path)
	if err != nil || address.IsAbs() || address.Host != "" || address.Fragment != "" ||
		address.RawQuery != "" || !strings.HasPrefix(address.Path, "/ai/") {
		return "", errors.New("平台接口路径无效")
	}
	for _, part := range strings.Split(address.Path, "/") {
		if part == "." || part == ".." {
			return "", errors.New("平台接口路径无效")
		}
	}
	address.RawQuery = query.Encode()
	return a.profile.Origin() + address.String(), nil
}

func (a *API) headers() http.Header {
	headers := a.metadata.headers(a.businessID)
	headers.Set("ai-businessId", a.businessID)
	setPlatformCookie(headers, a.credentials.Cookie)
	headers.Set("csrftoken", a.credentials.CSRFToken)
	headers.Set("Referer", a.profile.PublicEndpoint())
	return headers
}

func setPlatformCookie(headers http.Header, cookie string) {
	headers.Set("Cookie", cookie)
	if cookie != "" {
		headers.Set("ai-request-source", "wiserec-cli")
	}
}

func (a *API) JSON(ctx context.Context, method, path string, query url.Values, body any) (json.RawMessage, error) {
	endpoint, err := a.endpoint(path, query)
	if err != nil {
		return nil, err
	}
	a.used = true
	status, data, err := requestJSON(ctx, a.client, method, endpoint, body, a.headers(), "平台接口")
	if err != nil {
		return nil, err
	}
	if err := a.metadata.checkVersion(data); err != nil {
		return nil, err
	}
	switch {
	case status == 401 || status == 403 || status == 419 || status == 440,
		status >= 300 && status < 400:
		return nil, fmt.Errorf("平台认证未通过，HTTP %d，请运行 ml login", status)
	case status < 200 || status >= 300:
		return nil, fmt.Errorf("平台接口请求失败，HTTP %d", status)
	}
	a.confirmed = a.confirmed || confirmedPlatform(data)
	return data, nil
}

func (a *API) checkTarget() error {
	current, err := localstate.LoadConfig(a.session.Paths)
	if err != nil {
		return err
	}
	profile, err := current.RequireProfile()
	if err != nil {
		return ErrTargetChanged
	}
	if profile.Name != a.profile.Name || profile.Endpoint != a.profile.Endpoint ||
		profile.PlatformType != a.profile.PlatformType ||
		!reflect.DeepEqual(profile.Jupyter, a.profile.Jupyter) ||
		!reflect.DeepEqual(current.Access, a.session.Config.Access) ||
		!reflect.DeepEqual(profile.VerifyTLS, a.profile.VerifyTLS) ||
		!reflect.DeepEqual(current.API.VerifyTLS, a.session.Config.API.VerifyTLS) {
		return ErrTargetChanged
	}
	if localstate.Denied(a.command, profile.Policy.Deny) {
		return ErrTargetChanged
	}
	credentials, err := a.session.Paths.LoadCredentials(profile, time.Now())
	if err != nil {
		return err
	}
	businessID, err := a.session.Paths.SelectedBusiness(credentials)
	if err != nil {
		return err
	}
	if credentials.StateID != a.credentials.StateID || credentials.Username != a.credentials.Username || businessID != a.businessID {
		return ErrTargetChanged
	}
	return nil
}

func (a *API) LockTarget() (func(), error) {
	unlock, err := a.session.Paths.LockState()
	if err != nil {
		return nil, err
	}
	if err := a.checkTarget(); err != nil {
		unlock()
		return nil, err
	}
	return unlock, nil
}

func (a *API) beginMutation(ctx context.Context) (func(), error) {
	if err := a.checkTarget(); err != nil {
		return nil, err
	}
	if a.used {
		if err := a.session.requireAccess(ctx, &a.metadata, a.profile, a.credentials.Username, a.businessID, a.command, a.audit); err != nil {
			return nil, err
		}
	}
	return a.LockTarget()
}

func (a *API) Mutation(ctx context.Context, method, path string, query url.Values, body any) (json.RawMessage, error) {
	unlock, err := a.beginMutation(ctx)
	if err != nil {
		return nil, err
	}
	defer unlock()
	result, err := a.JSON(ctx, method, path, query, body)
	if err != nil {
		return nil, fmt.Errorf("操作结果未能确认：%w，请先查询资源状态", err)
	}
	return result, nil
}
