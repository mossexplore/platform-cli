package platform

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const mepCommand = "mep config get"

type Session struct {
	Paths      localstate.Paths
	Config     localstate.Config
	CLIVersion string
	Stderr     io.Writer
	Diagnostic io.Writer
}

func (s Session) QueryMEP(ctx context.Context, key, audit string) (json.RawMessage, error) {
	api, err := s.Authorize(ctx, mepCommand, audit)
	if err != nil {
		return nil, err
	}
	defer api.Close()
	defer api.RecordActivity()
	return api.JSON(ctx, http.MethodPost, "/ai/backend/mep/config/queryConfig", nil, map[string]string{"key": key})
}

func (s Session) requireAccess(ctx context.Context, metadata *invocation, profile localstate.Profile,
	username, businessID, command, audit string) error {
	client, err := accessTransport(s.Config.Access)
	if err != nil {
		return err
	}
	defer client.CloseIdleConnections()
	base := strings.TrimRight(s.Config.Access.URL, "/")
	if !strings.HasSuffix(base, "/cli-permission") {
		base += "/cli-permission"
	}
	body := map[string]string{
		"environment": profile.Name, "platform_origin": profile.Origin(),
		"username": username, "command": "ml " + command,
		"full_command": audit,
	}
	requestStart := time.Now()
	status, payload, err := requestJSON(ctx, client, http.MethodPost, base+"/api/v1/access/check",
		body, metadata.headers(businessID), "权限服务")
	if s.Diagnostic != nil {
		fmt.Fprintf(s.Diagnostic, "权限服务：%s\n请求耗时：%d ms\n", base, time.Since(requestStart).Milliseconds())
		if status != 0 {
			fmt.Fprintf(s.Diagnostic, "HTTP 状态：%d\n", status)
		}
	}
	if err != nil {
		return err
	}
	var result struct {
		Reason      string          `json:"reason"`
		Allowed     *bool           `json:"allowed"`
		Username    string          `json:"username"`
		Environment string          `json:"environment"`
		Policy      json.RawMessage `json:"command_policy"`
	}
	validJSON := json.Unmarshal(payload, &result) == nil
	if validJSON && status == http.StatusOK && result.Username == username && result.Environment == profile.Name {
		s.Paths.RememberPolicy(s.Config.Access, profile, result.Policy)
	}
	denied := validJSON && status == http.StatusOK && result.Allowed != nil && !*result.Allowed
	if err := metadata.checkAccessVersion(payload, base, denied); err != nil {
		return err
	}
	if status != http.StatusOK {
		return fmt.Errorf("权限检查失败，HTTP %d，业务请求已停止", status)
	}
	if !validJSON || result.Allowed == nil {
		return errors.New("权限服务响应格式错误，业务请求已停止")
	}
	if !*result.Allowed {
		if result.Reason == "ENVIRONMENT_MISMATCH" {
			return errors.New("当前 api_endpoint 与权限管理系统登记的平台地址不一致，业务请求已停止")
		}
		return errors.New("当前账号或命令未获授权，业务请求已停止")
	}
	if result.Username != username || result.Environment != profile.Name {
		return errors.New("权限服务返回的账号或环境与当前登录不一致")
	}
	return nil
}

const DefaultMEPKey = "mep_service_access_type"

type invocation struct {
	version, id, installation string
	stderr                    io.Writer
	warned                    bool
}

func (i *invocation) headers(businessID string) http.Header {
	header := make(http.Header)
	header.Set("X-CLI-Name", "wiserec-cli")
	header.Set("X-CLI-Version", i.version)
	header.Set("X-CLI-Protocol-Version", "1")
	header.Set("X-CLI-Invocation-ID", i.id)
	header.Set("X-Request-ID", localstate.NewID())
	header.Set("businessid", businessID)
	if i.installation != "" {
		header.Set("X-CLI-Installation-ID", i.installation)
	}
	return header
}

func (i *invocation) checkVersion(payload json.RawMessage) error {
	var envelope struct {
		Code    json.RawMessage `json:"code"`
		Reason  string          `json:"reason"`
		Allowed *bool           `json:"allowed"`
		Policy  struct {
			Warning bool `json:"warning"`
		} `json:"version_policy"`
	}
	if json.Unmarshal(payload, &envelope) != nil {
		return nil
	}
	var code string
	_ = json.Unmarshal(envelope.Code, &code)
	if code == "" {
		code = envelope.Reason
	}
	switch code {
	case "CLI_VERSION_REQUIRED", "CLI_VERSION_INVALID", "CLI_VERSION_TOO_OLD",
		"CLI_VERSION_BLOCKED", "CLI_PROTOCOL_UNSUPPORTED":
		return versionDenial(code, i.version, payload)
	}
	if envelope.Allowed != nil && !*envelope.Allowed &&
		(envelope.Reason == "COMMAND_DISABLED" || envelope.Reason == "COMMAND_REQUIRED") {
		return errors.New("服务端拒绝命令：当前环境禁止该操作或要求完整命令路径")
	}
	if envelope.Policy.Warning && !i.warned && i.stderr != nil {
		fmt.Fprintln(i.stderr, "[提示] 权限服务建议升级 CLI")
		i.warned = true
	}
	return nil
}
