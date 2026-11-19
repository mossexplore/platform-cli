package platform

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"unicode"
)

type VersionDenial struct {
	Code, Current, Minimum, Recommended, UpgradeURL string
	verifiedAccessDenial                            bool
}

var policyVersion = regexp.MustCompile(`^(0|[1-9][0-9]{0,8})(\.(0|[1-9][0-9]{0,8})){2,3}$`)

func versionDenial(code, current string, payload json.RawMessage) *VersionDenial {
	var details struct {
		Minimum     string `json:"minimum_version"`
		Recommended string `json:"recommended_version"`
		UpgradeURL  string `json:"upgrade_url"`
	}
	// A malformed optional field must never suppress a recognized denial.
	_ = json.Unmarshal(payload, &details)
	denial := &VersionDenial{Code: code, Current: current}
	if policyVersion.MatchString(details.Minimum) {
		denial.Minimum = details.Minimum
	}
	if policyVersion.MatchString(details.Recommended) {
		denial.Recommended = details.Recommended
	}
	address, err := url.Parse(details.UpgradeURL)
	if err == nil && (address.Scheme == "https" || address.Scheme == "http") &&
		address.Hostname() != "" && address.User == nil &&
		!strings.ContainsFunc(details.UpgradeURL, unicode.IsSpace) &&
		!strings.ContainsFunc(details.UpgradeURL, unicode.IsControl) {
		denial.UpgradeURL = details.UpgradeURL
	}
	return denial
}

func (d *VersionDenial) Error() string {
	message := "当前 CLI 版本或协议未获准入"
	if d.Code == "CLI_VERSION_TOO_OLD" {
		message = "WiseRec Go CLI 版本过低，命令已停止"
	}
	var result strings.Builder
	fmt.Fprintf(&result, "%s（%s）", message, d.Code)
	for _, field := range []struct{ label, value string }{
		{"当前版本", d.Current}, {"最低要求", d.Minimum}, {"推荐版本", d.Recommended},
	} {
		if field.value != "" {
			fmt.Fprintf(&result, "\n  %s：%s", field.label, field.value)
		}
	}
	return result.String()
}

// checkAccessVersion marks only explicit denials returned by the configured
// permission service over its certificate-verified HTTPS transport.
func (i *invocation) checkAccessVersion(payload json.RawMessage, endpoint string, denied bool) error {
	err := i.checkVersion(payload)
	if refusal, ok := err.(*VersionDenial); ok && denied {
		address, parseErr := url.Parse(endpoint)
		refusal.verifiedAccessDenial = parseErr == nil && validSignedURL(address)
	}
	return err
}

// MSIUpgradeURL accepts OBS object paths with no extension. The installer saves
// the response under a local .msi name and inspects the downloaded package.
func (d *VersionDenial) MSIUpgradeURL() (string, error) {
	if d.UpgradeURL == "" {
		return "", nil
	}
	address, err := url.Parse(d.UpgradeURL)
	if err != nil || !validSignedURL(address) {
		return "", errors.New("MSI 下载地址必须使用 HTTPS")
	}
	if !d.verifiedAccessDenial {
		return "", errors.New("自动升级地址须由经证书验证的 HTTPS 权限服务返回，可运行 ml access status --diagnose 核对")
	}
	// Preserve the exact signed OBS path and query. A fragment is local to the
	// client and older links may still carry a digest there.
	downloadURL, _, _ := strings.Cut(d.UpgradeURL, "#")
	return downloadURL, nil
}
