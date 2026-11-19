package platform

import (
	"errors"
	"strings"
	"testing"
)

func TestVersionDenialRetainsUpgradeInformation(t *testing.T) {
	i := invocation{version: "1.0.14"}
	for _, test := range []struct {
		name, payload, wantURL string
	}{
		{"precheck", `{"allowed":false,"reason":"CLI_VERSION_TOO_OLD","minimum_version":"1.0.15","recommended_version":"1.0.16","upgrade_url":"https://example.test/release.msi?download=1"}`,
			"https://example.test/release.msi?download=1"},
		{"gateway page", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"https://example.test/upgrade.html"}`,
			"https://example.test/upgrade.html"},
		{"HTTP for manual use", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"http://example.test/release.msi"}`,
			"http://example.test/release.msi"},
		{"unsafe URL", `{"code":"CLI_VERSION_TOO_OLD","upgrade_url":"https://user:password@example.test/release.msi"}`, ""},
		{"malformed metadata", `{"allowed":false,"reason":"CLI_VERSION_TOO_OLD","upgrade_url":[],"minimum_version":{"bad":true}}`, ""},
	} {
		t.Run(test.name, func(t *testing.T) {
			err := i.checkVersion([]byte(test.payload))
			var denial *VersionDenial
			if !errors.As(err, &denial) || denial.UpgradeURL != test.wantURL {
				t.Fatalf("unexpected denial: %#v (%v)", denial, err)
			}
			if strings.Contains(err.Error(), "升级说明") || strings.Contains(err.Error(), "example.test") {
				t.Fatalf("version denial exposes the download link: %v", err)
			}
		})
	}
}

func TestMSIUpgradeURL(t *testing.T) {
	invocation := invocation{version: "1.1.0"}
	const signedOBS = "https://obs.example.test/installer/%61b91ca013e?Signature=a%2bb&Expires=1700000000"
	for _, test := range []struct {
		name, endpoint, address, wantProblem string
		explicitDenial                       bool
	}{
		{"extensionless OBS object", "https://access.example.test", signedOBS, "", true},
		{"legacy fragment is ignored", "https://access.example.test", signedOBS + "#sha256=unused", "", true},
		{"HTTP permission denial", "http://access.example.test", signedOBS, "HTTPS 权限服务", true},
		{"platform gateway denial", "", signedOBS, "HTTPS 权限服务", true},
		{"permission response without explicit denial", "https://access.example.test", signedOBS, "HTTPS 权限服务", false},
		{"unencrypted download", "https://access.example.test", "http://obs.example.test/installer", "必须使用 HTTPS", true},
	} {
		t.Run(test.name, func(t *testing.T) {
			payload := []byte(`{"allowed":false,"code":"CLI_VERSION_TOO_OLD","upgrade_url":"` + test.address + `"}`)
			err := invocation.checkVersion(payload)
			if test.endpoint != "" {
				err = invocation.checkAccessVersion(payload, test.endpoint, test.explicitDenial)
			}
			var denial *VersionDenial
			if !errors.As(err, &denial) || denial.UpgradeURL != test.address {
				t.Fatalf("expected denial with its original link: %v", err)
			}
			address, problem := denial.MSIUpgradeURL()
			if test.wantProblem != "" {
				if address != "" || problem == nil || !strings.Contains(problem.Error(), test.wantProblem) {
					t.Fatalf("unexpected upgrade block: %q, %v", address, problem)
				}
			} else if address != signedOBS || problem != nil {
				t.Fatalf("unexpected download URL: %q, %v", address, problem)
			}
		})
	}
}
