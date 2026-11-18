package platform

import (
	"encoding/json"
	"fmt"
	"net/url"
	"regexp"
	"strings"
	"unicode"
)

type VersionDenial struct {
	Code, Current, Minimum, Recommended, UpgradeURL string
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
		{"当前版本", d.Current}, {"最低要求", d.Minimum}, {"推荐版本", d.Recommended}, {"升级说明", d.UpgradeURL},
	} {
		if field.value != "" {
			fmt.Fprintf(&result, "\n  %s：%s", field.label, field.value)
		}
	}
	if d.UpgradeURL == "" {
		result.WriteString("\n  请联系管理员获取升级说明。")
	}
	return result.String()
}

func (d *VersionDenial) MSIDownloadURL() string {
	address, err := url.Parse(d.UpgradeURL)
	if err != nil || !validSignedURL(address) || !strings.HasSuffix(strings.ToLower(address.Path), ".msi") {
		return ""
	}
	return d.UpgradeURL
}
