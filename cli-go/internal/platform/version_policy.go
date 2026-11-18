package platform

import (
	"crypto/sha256"
	"encoding/hex"
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

type MSIUpgrade struct {
	URL    string
	SHA256 string
}

func (d *VersionDenial) MSIUpgrade() (MSIUpgrade, error) {
	if d.UpgradeURL == "" {
		return MSIUpgrade{}, nil
	}
	address, err := url.Parse(d.UpgradeURL)
	if err != nil || !validSignedURL(address) || !strings.HasSuffix(strings.ToLower(address.Path), ".msi") {
		return MSIUpgrade{}, errors.New("MSI 下载地址必须是 HTTPS 的 .msi 直链")
	}
	key, hash, _ := strings.Cut(address.Fragment, "=")
	address.Fragment, address.RawFragment = "", ""
	if !strings.EqualFold(key, "sha256") {
		return MSIUpgrade{URL: address.String()}, nil
	}

	// A digest in an unauthenticated response could otherwise authorize any MSI
	// chosen by the sender. A fragment declaring a digest never falls back to signing.
	if _, err := hex.DecodeString(hash); err != nil || len(hash) != 2*sha256.Size {
		return MSIUpgrade{}, errors.New("MSI 下载地址的 #sha256= 后须填写完整的 64 个十六进制字符")
	}
	if !d.verifiedAccessDenial {
		return MSIUpgrade{}, errors.New("SHA-256 升级地址须由经证书验证的 HTTPS 权限服务返回，可运行 ml access status --diagnose 核对")
	}
	return MSIUpgrade{URL: address.String(), SHA256: strings.ToLower(hash)}, nil
}
