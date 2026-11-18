package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

var ErrNoAccess = errors.New("当前账号尚无有效的 CLI 环境授权")

func (s Session) EnvironmentStatuses(ctx context.Context, audit string) (map[string]string, error) {
	cfg := s.Config
	if !cfg.Access.Active() || cfg.Access.URL == "" {
		return nil, errors.New("权限检查未配置，无法查询环境授权状态")
	}
	current, err := s.Paths.CredentialsFor(cfg.Profile())
	if err != nil {
		return nil, errors.New("当前环境尚无登录账号，请先执行 ml login 查询 CLI 权限")
	}
	type target struct {
		Name        string `json:"environment"`
		Username    string `json:"username"`
		Origin      string `json:"platform_origin"`
		BusinessID  string `json:"business_id"`
		FullCommand string `json:"full_command,omitempty"`
	}
	targets := []target{}
	expected := map[string]target{}
	owners := map[string]string{}
	expired := map[string]bool{}
	businessID := ""
	for _, profile := range cfg.Profiles {
		creds, err := s.Paths.CredentialsFor(profile)
		if err != nil {
			continue
		}
		owners[profile.Name] = creds.Username
		expires, err := creds.Expiry()
		if err != nil {
			continue
		}
		if !time.Now().Before(expires) {
			expired[profile.Name] = true
			continue
		}
		id, err := s.Paths.SelectedBusiness(creds)
		if err != nil || creds.Username != current.Username {
			continue
		}
		check := target{Name: profile.Name, Username: creds.Username, Origin: profile.Origin(), BusinessID: id, FullCommand: audit}
		targets = append(targets, check)
		expected[profile.Name] = check
		if profile.Name == cfg.Current {
			businessID = id
		}
	}
	// The batch endpoint accepts a current-account summary when no business is selected.
	metadata := invocation{version: s.CLIVersion, id: localstate.NewID(), installation: s.Paths.InstallationID(), stderr: s.Stderr}
	client, err := accessTransport(cfg.Access)
	if err != nil {
		return nil, err
	}
	defer client.CloseIdleConnections()
	headers := metadata.headers(businessID)
	if businessID == "" {
		headers.Del("businessid")
	}
	base := strings.TrimRight(cfg.Access.URL, "/")
	if !strings.HasSuffix(base, "/cli-permission") {
		base += "/cli-permission"
	}
	req := map[string]any{"username": current.Username, "environments": targets}
	status, payload, err := requestJSON(ctx, client, http.MethodPost, base+"/api/v1/access/environments", req, headers, "权限服务")
	if err != nil {
		return nil, err
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("批量环境权限查询失败，HTTP %d", status)
	}
	var response struct {
		Username       string   `json:"username"`
		HasAccess      *bool    `json:"has_access"`
		Authorizations []target `json:"authorizations"`
		Environments   []struct {
			target
			Result json.RawMessage `json:"result"`
		} `json:"environments"`
	}
	if json.Unmarshal(payload, &response) != nil || response.HasAccess == nil || response.Username != current.Username || response.Environments == nil {
		return nil, errors.New("批量环境权限查询响应格式或账号不匹配")
	}
	if !*response.HasAccess {
		return nil, ErrNoAccess
	}
	if response.Authorizations == nil {
		return nil, errors.New("权限服务未返回完整授权环境列表")
	}
	grants := make(map[string]string)
	for _, grant := range response.Authorizations {
		if _, duplicate := grants[grant.Name]; duplicate || grant.Name == "" || grant.Origin == "" {
			return nil, errors.New("授权环境列表包含无效或重复数据")
		}
		grants[grant.Name] = strings.TrimRight(grant.Origin, "/")
	}
	decisions := make(map[string]bool)
	for _, check := range response.Environments {
		request, exists := expected[check.Name]
		_, duplicate := decisions[check.Name]
		var decision struct {
			Allowed     *bool           `json:"allowed"`
			Username    string          `json:"username"`
			Environment string          `json:"environment"`
			Policy      json.RawMessage `json:"command_policy"`
		}
		if !exists || duplicate || check.BusinessID != request.BusinessID || check.Username != request.Username ||
			json.Unmarshal(check.Result, &decision) != nil || decision.Allowed == nil ||
			(*decision.Allowed && (decision.Username != request.Username || decision.Environment != request.Name)) {
			return nil, errors.New("批量环境权限查询返回的环境、账号或业务不匹配")
		}
		if err := metadata.checkVersion(check.Result); err != nil {
			return nil, err
		}
		decisions[check.Name] = *decision.Allowed
		for _, profile := range cfg.Profiles {
			if profile.Name == check.Name {
				s.Paths.RememberPolicy(cfg.Access, profile, decision.Policy)
				break
			}
		}
	}
	if len(decisions) != len(targets) {
		return nil, errors.New("批量环境权限查询结果不完整")
	}
	statuses := make(map[string]string)
	for _, profile := range cfg.Profiles {
		decision, checked := decisions[profile.Name]
		switch {
		case grants[profile.Name] != profile.Origin() || checked && !decision:
			statuses[profile.Name] = "未授权"
		case owners[profile.Name] == current.Username && expired[profile.Name]:
			statuses[profile.Name] = "登录已过期"
		case checked:
			statuses[profile.Name] = "登录使用中"
		default:
			statuses[profile.Name] = "已授权"
		}
	}
	return statuses, nil
}
