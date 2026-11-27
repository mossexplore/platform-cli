package command

import (
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestEnvironmentListVisibility(t *testing.T) {
	for _, tc := range []struct {
		name, defaults, login, response, wantState, hint string
		wantNames                                        []string
		wantRequests                                     int32
	}{
		{"anonymous", `,"default_visible_environments":["dev"]`, "", "", "默认可见", "", []string{"dev"}, 0},
		{"omitted", "", "", "", "", "", nil, 0},
		{"empty", `,"default_visible_environments":[]`, "", "", "", "", nil, 0},
		{"authorized elsewhere", `,"default_visible_environments":["dev"]`, "uat", "ok", "登录已过期", "", []string{"dev", "uat", "staging"}, 1},
		{"no grants", `,"default_visible_environments":["dev"]`, "uat", "denied", "未授权", "尚无有效", []string{"dev"}, 1},
		{"query failure", `,"default_visible_environments":["dev"]`, "uat", "error", "授权状态未知", "HTTP 503", []string{"dev"}, 1},
		{"ambiguous account", `,"default_visible_environments":["dev"]`, "multiple", "", "授权状态未知", "多个登录账号", []string{"dev"}, 0},
	} {
		t.Run(tc.name, func(t *testing.T) {
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				requests.Add(1)
				var body struct {
					Username     string
					Environments []json.RawMessage
				}
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				if r.URL.Path != "/cli-permission/api/v1/access/environments" || body.Username != "alice" ||
					len(body.Environments) != 0 || r.Header.Get("businessid") != "" {
					t.Errorf("unexpected account-only query: path=%s body=%+v", r.URL.Path, body)
				}
				switch tc.response {
				case "ok":
					fmt.Fprint(w, `{"username":"alice","has_access":true,"authorizations":[
						{"environment":"uat","platform_origin":"https://uat.example.test"},
						{"environment":"staging","platform_origin":"https://staging.example.test"}],"environments":[]}`)
				case "denied":
					fmt.Fprint(w, `{"username":"alice","has_access":false,"environments":[]}`)
				default:
					w.WriteHeader(http.StatusServiceUnavailable)
				}
			}))
			defer server.Close()
			paths, err := localstate.NewPaths(t.TempDir(), []byte(fmt.Sprintf(`{
				"current":"dev","profiles":[
					{"name":"dev","api_endpoint":"https://dev.example.test"},
					{"name":"uat","api_endpoint":"https://uat.example.test"},
					{"name":"staging","api_endpoint":"https://staging.example.test"},
					{"name":"private","api_endpoint":"https://private.example.test"}],
				"access_control":{"url":%q}%s}`, server.URL, tc.defaults)))
			if err != nil {
				t.Fatal(err)
			}
			saveExpired := func(profile, username string) {
				t.Helper()
				expiry, err := json.Marshal(time.Now().Add(-time.Hour))
				if err != nil {
					t.Fatal(err)
				}
				_, err = paths.SaveLogin(localstate.Credentials{
					Origin: "https://" + profile + ".example.test", Profile: profile, Username: username,
					Cookie: "fixture=local", CSRFToken: "test-csrf", ExpiresAt: expiry,
				}, nil, "", "")
				if err != nil {
					t.Fatal(err)
				}
			}
			if tc.login != "" {
				saveExpired("uat", "alice")
			}
			if tc.login == "multiple" {
				saveExpired("private", "bob")
			}
			code, out, stderr := run(t, paths, "env", "list", "-o", "json")
			var rows []map[string]string
			if code != 0 || json.Unmarshal([]byte(out), &rows) != nil || rows == nil || len(rows) != len(tc.wantNames) {
				t.Fatalf("code=%d stdout=%s stderr=%s", code, out, stderr)
			}
			for i, name := range tc.wantNames {
				if rows[i]["环境标识"] != name {
					t.Errorf("row %d = %v, want %s", i, rows[i], name)
				}
			}
			if tc.response == "ok" && (rows[0]["状态"] != "未授权" ||
				rows[1]["状态"] != "登录已过期" || rows[2]["状态"] != "已授权") {
				t.Errorf("unexpected states: %s", out)
			}
			if requests.Load() != tc.wantRequests || !strings.Contains(out, tc.wantState) ||
				!strings.Contains(stderr, tc.hint) || tc.hint == "" && stderr != "" {
				t.Errorf("requests=%d stdout=%s stderr=%s", requests.Load(), out, stderr)
			}
		})
	}
}

func TestEnvUseAgentReturnsSharedLoginStatus(t *testing.T) {
	paths, err := localstate.NewPaths(t.TempDir(), []byte(`{"current":"uat","profiles":[
		{"name":"dev","platform_type":"wiserec","api_endpoint":"https://dev.example.com/api","base_url":"https://dev.example.com"},
		{"name":"uat","platform_type":"wiserec","api_endpoint":"https://uat.example.com/api","base_url":"https://uat.example.com"}
	],"auth":{"auto_ping":false}}`))
	if err != nil {
		t.Fatal(err)
	}
	expiry, err := json.Marshal(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	if _, err := paths.SaveLogin(localstate.Credentials{
		Origin:    "https://dev.example.com",
		Profile:   "dev",
		Username:  "alice",
		Cookie:    "c=1",
		CSRFToken: "t=1",
		ExpiresAt: expiry,
	}, nil, "", ""); err != nil {
		t.Fatal(err)
	}
	sess := paths
	sess.Session = localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "dsh-new-session"}

	code, out, stderr := run(t, sess, "env", "use", "dev", "--agent")
	if code != 0 {
		t.Fatalf("env use dev --agent failed: code=%d stderr=%s", code, stderr)
	}
	var got map[string]string
	if err := json.Unmarshal([]byte(out), &got); err != nil {
		t.Fatalf("invalid json: %v\nout=%s", err, out)
	}
	if got["environment"] != "dev" || got["loginStatus"] != "有效" || got["businessId"] != "未绑定" {
		t.Fatalf("unexpected env use --agent result: %+v", got)
	}
}
