package platform

import (
	"errors"
	"strings"
	"testing"
)

func TestVersionDenialRetainsUpgradeInformation(t *testing.T) {
	i := invocation{version: "1.0.14"}
	for _, test := range []struct {
		name, payload, wantURL, wantMSI string
	}{
		{"precheck", `{"allowed":false,"reason":"CLI_VERSION_TOO_OLD","minimum_version":"1.0.15","recommended_version":"1.0.16","upgrade_url":"https://example.test/release.msi?download=1"}`,
			"https://example.test/release.msi?download=1", "https://example.test/release.msi?download=1"},
		{"gateway page", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"https://example.test/upgrade.html"}`,
			"https://example.test/upgrade.html", ""},
		{"HTTP for manual use", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"http://example.test/release.msi"}`,
			"http://example.test/release.msi", ""},
		{"unsafe URL", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"https://user:password@example.test/release.msi"}`, "", ""},
		{"malformed metadata", `{"allowed":false,"reason":"CLI_VERSION_TOO_OLD","upgrade_url":[],"minimum_version":{"bad":true}}`, "", ""},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := i.checkVersion([]byte(test.payload))
			var denial *VersionDenial
			if !errors.As(err, &denial) || denial.UpgradeURL != test.wantURL || denial.MSIDownloadURL() != test.wantMSI {
				t.Fatalf("unexpected denial: %#v (%v)", denial, err)
			}
			if !strings.Contains(err.Error(), "命令已停止（CLI_VERSION_TOO_OLD）") ||
				!strings.Contains(err.Error(), "当前版本：1.0.14") {
				t.Fatalf("unexpected message: %v", err)
			}
			if test.name == "precheck" && (!strings.Contains(err.Error(), "最低要求：1.0.15") ||
				!strings.Contains(err.Error(), "推荐版本：1.0.16")) {
				t.Fatalf("missing version information: %v", err)
			}
			if test.wantURL == "" && !strings.Contains(err.Error(), "请联系管理员") {
				t.Fatalf("missing manual fallback: %v", err)
			}
		})
	}
}
