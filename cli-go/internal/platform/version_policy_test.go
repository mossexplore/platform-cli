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
		{"signed upgrade link with a fragment", `{"allowed":false,"reason":"CLI_VERSION_TOO_OLD","upgrade_url":"https://example.test/release.msi?download=1#details"}`,
			"https://example.test/release.msi?download=1#details", "https://example.test/release.msi?download=1"},
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
			if !errors.As(err, &denial) || denial.UpgradeURL != test.wantURL || denial.MSIUpgrade() != (MSIUpgrade{URL: test.wantMSI}) {
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

func TestMSIUpgradeDigestRequiresVerifiedAccessDenial(t *testing.T) {
	invocation := invocation{version: "1.0.16"}
	const rawURL = "https://example.test/upgrade.msi?download=1"
	const hash = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
	for _, test := range []struct {
		name, endpoint, fragment   string
		explicitDenial, wantDigest bool
	}{
		{"HTTPS permission denial", "https://access.example.test", "sha256=" + strings.ToUpper(hash), true, true},
		{"HTTP permission denial", "http://access.example.test", "sha256=" + hash, true, false},
		{"platform gateway denial", "", "sha256=" + hash, true, false},
		{"permission response without explicit denial", "https://access.example.test", "sha256=" + hash, false, false},
		{"invalid hexadecimal", "https://access.example.test", "sha256=z" + hash[1:], true, false},
		{"missing digest", "https://access.example.test", "sha256", true, false},
		{"truncated digest", "https://access.example.test", "sha256=" + hash[:63], true, false},
		{"duplicate digest", "https://access.example.test", "sha256=" + hash + "&sha256=" + hash, true, false},
	} {
		t.Run(test.name, func(t *testing.T) {
			address := rawURL + "#" + test.fragment
			payload := []byte(`{"allowed":false,"code":"CLI_VERSION_TOO_OLD","upgrade_url":"` + address + `"}`)
			err := invocation.checkVersion(payload)
			if test.endpoint != "" {
				err = invocation.checkAccessVersion(payload, test.endpoint, test.explicitDenial)
			}
			var denial *VersionDenial
			if !errors.As(err, &denial) || denial.UpgradeURL != address {
				t.Fatalf("expected denial with its original link: %v", err)
			}
			expected := MSIUpgrade{}
			if test.wantDigest {
				expected = MSIUpgrade{URL: rawURL, SHA256: hash}
			}
			if actual := denial.MSIUpgrade(); actual != expected {
				t.Fatalf("unexpected automatic upgrade package: %+v", actual)
			}
		})
	}
}
