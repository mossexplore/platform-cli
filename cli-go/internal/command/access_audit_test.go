package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAccessAuditRedactsSensitiveValues(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.URL.Path != "/cli-permission/api/v1/access/check" {
			t.Errorf("unexpected route %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		body := readRequest(t, r)
		want := "ml train config update task " + quoteHistoryArg("--customize-config=[REDACTED]")
		if body["command"] != "ml train config update" || body["full_command"] != want {
			t.Errorf("unexpected audit fields: %v", body)
		}
		fmt.Fprintln(w, `{"allowed":false}`)
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "train", "config", "update", "task", "--customize-config=fixture-secret")
	if code != 1 || out != "" || !strings.Contains(stderr, "未获授权") {
		t.Fatalf("unexpected result: %d %s %s", code, out, stderr)
	}
}

func TestEnvironmentAccessAuditIncludesOptions(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.URL.Path != "/cli-permission/api/v1/access/environments" || r.Method != http.MethodPost {
			t.Errorf("unexpected route %s %s", r.Method, r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		var body struct {
			Username     string
			Environments []struct {
				Environment string
				BusinessID  string `json:"business_id"`
				FullCommand string `json:"full_command"`
			}
		}
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Error(err)
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		if body.Username != "preview-user" || len(body.Environments) != 1 ||
			body.Environments[0].Environment != "preview" || body.Environments[0].BusinessID != "business-real" ||
			body.Environments[0].FullCommand != "ml env list -o json" {
			t.Errorf("wrong batch check: %+v", body)
		}
		fmt.Fprintf(w, `{"username":"preview-user","has_access":true,
			"authorizations":[{"environment":"preview","platform_origin":%q}],
			"environments":[{"environment":"preview","username":"preview-user","business_id":"business-real",
				"result":{"allowed":true,"username":"preview-user","environment":"preview"}}]}`, "http://"+r.Host)
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "env", "list", "-o", "json")
	if code != 0 || stderr != "" || !json.Valid([]byte(out)) || !strings.Contains(out, "登录使用中") {
		t.Fatalf("unexpected result (%d): %s %s", code, out, stderr)
	}
}

func TestOldVersionHidesUpgradeLinkWithoutPromptOrBusinessRequest(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.URL.Path != "/cli-permission/api/v1/access/check" {
			t.Errorf("version denial allowed a business request: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		fmt.Fprintln(w, `{"allowed":false,"code":"CLI_VERSION_TOO_OLD","minimum_version":"2.0.0",
			"recommended_version":"2.0.1","upgrade_url":"https://example.test/upgrade.msi"}`)
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)

	code, out, stderr := run(t, paths, "user", "info", "-o", "json")
	if code != 1 || out != "" || !strings.Contains(stderr, "[错误] WiseRec Go CLI 版本过低") ||
		!strings.Contains(stderr, "最低要求：2.0.0") || !strings.Contains(stderr, "推荐版本：2.0.1") ||
		strings.Contains(stderr, "升级说明") || strings.Contains(stderr, "https://example.test/upgrade.msi") || strings.Contains(stderr, "[y/N]") {
		t.Fatalf("unexpected result: %d %q %q", code, out, stderr)
	}
}
