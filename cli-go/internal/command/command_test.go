package command

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestVersionDoesNotReadState(t *testing.T) {
	var out, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args: []string{"--version"}, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
		Paths: func() (localstate.Paths, error) {
			t.Fatal("version attempted to read state")
			return localstate.Paths{}, nil
		},
	})
	if code != 0 || out.String() != "ml 1.2.3\n" || stderr.Len() != 0 {
		t.Fatalf("version: %d %s %s", code, &out, &stderr)
	}
}

func TestContextAndTree(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	paths = fixtureConfig(t, paths.Dir, "https://preview.example.test/path?private=value#secret", "https://permissions.example.test", true, "mlops", "")
	code, out, stderr := run(t, paths, "context", "--json")
	if code != 0 || stderr != "" || !strings.Contains(out, "当前环境") ||
		strings.Contains(out, "preview.example.test") || strings.Contains(out, "平台地址") {
		t.Fatalf("context: %d %s %s", code, out, stderr)
	}
	code, out, stderr = run(t, paths, "context")
	if code != 0 || stderr != "" || !strings.Contains(out, "┃ 字段") ||
		strings.Index(out, "运行模式") >= strings.Index(out, "CLI 版本") {
		t.Fatalf("context table: %d %s %s", code, out, stderr)
	}
	code, out, stderr = run(t, paths, "tree")
	if code != 0 || stderr != "" || strings.Contains(out, "查询当前登录用户信息") {
		t.Fatalf("filtered tree: %d %s %s", code, out, stderr)
	}
	code, out, stderr = run(t, paths, "tree", "--all")
	if code != 0 || stderr != "" || !strings.Contains(out, "查询当前登录用户信息  [当前环境禁用]") ||
		!strings.Contains(out, "├── login  ") || strings.Index(out, "├── login  ") >= strings.Index(out, "├── tree  ") {
		t.Fatalf("full tree: %d %s %s", code, out, stderr)
	}
}

func TestMEPRemovedFromCLI(t *testing.T) {
	for _, manager := range []string{"wiserec", "mlops"} {
		paths := fixtureConfig(t, t.TempDir(), "https://preview.example.test", "", false, manager, "")
		for _, args := range [][]string{{"--help"}, {"tree"}, {"tree", "--all"}} {
			code, out, stderr := run(t, paths, args...)
			if code != 0 || stderr != "" || strings.Contains(out, "mep") {
				t.Fatalf("%s %v: %d %s %s", manager, args, code, out, stderr)
			}
		}
	}
	var out, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args: []string{"mep", "config", "get"}, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
		Paths: func() (localstate.Paths, error) {
			t.Fatal("removed command attempted to read state")
			return localstate.Paths{}, nil
		},
	})
	if code == 0 || out.Len() != 0 || !strings.Contains(stderr.String(), `unknown command "mep"`) {
		t.Fatalf("removed command: %d %s %s", code, &out, &stderr)
	}
}

func runWithMEP(paths localstate.Paths, args ...string) (int, string, string) {
	var out, stderr bytes.Buffer
	options := Options{Args: args, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
		Paths: func() (localstate.Paths, error) { return paths, nil }}
	root := newRoot(options)
	root.AddCommand(newMEP(options, func() (localstate.Paths, localstate.Config, error) {
		cfg, err := paths.LoadOrInitializeConfig()
		return paths, cfg, err
	}))
	if err := root.ExecuteContext(context.Background()); err != nil {
		return 1, out.String(), err.Error()
	}
	return 0, out.String(), stderr.String()
}

func TestMEPRequestBoundaries(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	var mu sync.Mutex
	var serverOrigin string
	var events []string
	wantAudit := "ml mep config get test-key -o json"
	var accessReply = `{"allowed":true,"username":"preview-user","environment":"preview"}`
	var accessID, accessRequestID string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		mu.Lock()
		defer mu.Unlock()
		events = append(events, r.URL.Path)
		var body map[string]string
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil || r.Method != "POST" {
			t.Errorf("invalid request: %s %v", r.Method, err)
		}
		if r.Header.Get("businessid") != "business-real" || r.Header.Get("X-CLI-Version") != "1.2.3" {
			t.Errorf("unexpected business identity or version")
		}
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			if r.Header.Get("Cookie") != "" || r.Header.Get("csrftoken") != "" {
				t.Error("access service received browser credentials")
			}
			if body["environment"] != "preview" || body["username"] != "preview-user" ||
				body["platform_origin"] != serverOrigin || body["command"] != "ml mep config get" ||
				body["full_command"] != wantAudit {
				t.Errorf("unexpected access body: %v", body)
			}
			accessID, accessRequestID = r.Header.Get("X-CLI-Invocation-ID"), r.Header.Get("X-Request-ID")
			fmt.Fprintln(w, accessReply)
		case "/ai/backend/mep/config/queryConfig":
			if body["key"] != "test-key" || r.Header.Get("Cookie") != "fixture=local" ||
				r.Header.Get("csrftoken") != "test-csrf" || r.Header.Get("ai-businessId") != "business-real" {
				t.Error("incorrect platform request")
			}
			if accessID == "" || r.Header.Get("X-CLI-Invocation-ID") != accessID ||
				accessRequestID == r.Header.Get("X-Request-ID") {
				t.Error("incorrect invocation correlation")
			}
			fmt.Fprintln(w, `{"result":{"code":0},"additional":9223372036854775807}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	mu.Lock()
	serverOrigin = server.URL
	mu.Unlock()
	paths = fixtureConfig(t, paths.Dir, server.URL+"/ui?local=fixture", server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	legacy := `{"current":"preview","profiles":[{"name":"preview","api_endpoint":"https://untrusted.example.test"}],"access_control":{"enable":false}}`
	if err := os.WriteFile(paths.Config(), []byte(legacy), 0600); err != nil {
		t.Fatal(err)
	}
	code, out, stderr := runWithMEP(paths, "mep", "config", "get", "test-key", "-o", "json")
	if code != 0 || stderr != "" || !strings.Contains(out, "9223372036854775807") {
		t.Fatalf("query: %d %s %s", code, out, stderr)
	}
	mu.Lock()
	sequence := strings.Join(events, ",")
	mu.Unlock()
	if sequence != "/cli-permission/api/v1/access/check,/ai/backend/mep/config/queryConfig" {
		t.Fatalf("request sequence: %s", sequence)
	}

	mu.Lock()
	wantAudit = "ml mep config get test-key -o table"
	mu.Unlock()
	code, out, stderr = runWithMEP(paths, "mep", "config", "get", "test-key", "-o", "table")
	if code != 0 || stderr != "" || !strings.Contains(out, "┃ 字段") ||
		!strings.Contains(out, `{"code": 0}`) || !strings.Contains(out, "9223372036854775807") {
		t.Fatalf("query table: %d %s %s", code, out, stderr)
	}

	for _, reply := range []string{
		`{"allowed":false,"reason":"DENIED"}`,
		`{"allowed":true,"username":"someone-else","environment":"preview"}`,
		`{"allowed":true,"username":"preview-user","environment":"different"}`,
		`{"allowed":"true","username":"preview-user","environment":"preview"}`,
		`{"allowed":false,"reason":"CLI_VERSION_TOO_OLD"}`,
	} {
		mu.Lock()
		accessReply, events = reply, nil
		wantAudit = "ml mep config get test-key"
		mu.Unlock()
		code, out, stderr = runWithMEP(paths, "mep", "config", "get", "test-key")
		if code == 0 || out != "" || stderr == "" {
			t.Fatalf("expected denial: %s %d %s %s", reply, code, out, stderr)
		}
		mu.Lock()
		sequence = strings.Join(events, ",")
		mu.Unlock()
		if sequence != "/cli-permission/api/v1/access/check" {
			t.Fatalf("request escaped denial: %s", sequence)
		}
	}

	mu.Lock()
	accessReply = fmt.Sprintf(`{"allowed":false,"reason":"COMMAND_DISABLED","username":"preview-user","environment":"preview",
		"command_policy":{"environment":"preview","platform_origin":%q,"revision":1,"deny":["ml mep config get"]}}`, server.URL)
	mu.Unlock()
	code, out, stderr = runWithMEP(paths, "mep", "config", "get", "test-key")
	if code == 0 || out != "" || !strings.Contains(stderr, "服务端拒绝命令") {
		t.Fatalf("server command policy: %d %s %s", code, out, stderr)
	}
	code, out, stderr = runWithMEP(paths, "tree")
	if code != 0 || stderr != "" || strings.Contains(out, "查询一个 MEP 配置项") {
		t.Fatalf("cached server policy: %d %s %s", code, out, stderr)
	}

	mu.Lock()
	events = nil
	mu.Unlock()
	paths = fixtureConfig(t, paths.Dir, "http://127.0.0.1:1/ui", server.URL, false, "mlops", "")
	code, out, stderr = runWithMEP(paths, "mep", "config", "get", "test-key")
	if code == 0 || out != "" || !strings.Contains(stderr, "登录缓存") {
		t.Fatalf("changed origin: %d %s %s", code, out, stderr)
	}
	paths = fixtureConfig(t, paths.Dir, server.URL, server.URL, false, "mlops", "")
	business, err := os.ReadFile(paths.Business())
	if err != nil {
		t.Fatal(err)
	}
	modified := strings.Replace(string(business), `"selected":{"department_id":"dept","tenant_id":"tenant","team_id":"team","businessId":"business-real"}`, `"selected":{"department_id":"dept","tenant_id":"tenant","team_id":"team","businessId":"business-other"}`, 1)
	if modified == string(business) {
		t.Fatal("did not modify the current selection")
	}
	if err := os.WriteFile(paths.Business(), []byte(modified), 0600); err != nil {
		t.Fatal(err)
	}
	code, out, stderr = runWithMEP(paths, "mep", "config", "get", "test-key")
	if code == 0 || out != "" || !strings.Contains(stderr, "selected.businessId") {
		t.Fatalf("invalid selection: %d %s %s", code, out, stderr)
	}
	mu.Lock()
	eventCount := len(events)
	mu.Unlock()
	if eventCount != 0 {
		t.Fatalf("invalid local session made %d requests", eventCount)
	}
}

func run(t *testing.T, paths localstate.Paths, args ...string) (int, string, string) {
	t.Helper()
	var out, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args: args, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
		Paths: func() (localstate.Paths, error) { return paths, nil },
	})
	return code, out.String(), stderr.String()
}

func fixtureConfig(t *testing.T, dir, endpoint, access string, deny bool, manager, jupyterURL string) localstate.Paths {
	t.Helper()
	rules := "[]"
	if deny {
		rules = `["ml user"]`
	}
	input := fmt.Sprintf(`{"current":"preview","profiles":[
		{"name":"other","api_endpoint":"https://other.example.test","platform_type":"wiserec"},
		{"name":"preview","api_endpoint":%q,"platform_type":%q,"command_policy":{"deny":%s},"jupyter":{"server_url":%q}}],
		"access_control":{"url":%q}}`, endpoint, manager, rules, jupyterURL, access)
	paths, err := localstate.NewPaths(dir, []byte(input))
	if err != nil {
		t.Fatal(err)
	}
	return paths
}

func saveState(t *testing.T, paths localstate.Paths, origin string) {
	t.Helper()
	expiry, err := json.Marshal(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	credentials := localstate.Credentials{
		Profile: "preview", Origin: origin, Username: "preview-user",
		Cookie: "fixture=local", CSRFToken: "test-csrf", ExpiresAt: expiry,
	}
	catalog := []localstate.Department{{ID: "dept", Tenants: []localstate.Tenant{{
		ID: "tenant", Teams: []localstate.Team{{ID: "team", Key: "browser-alias", Status: "available", BusinessID: "business-real"}},
	}}}}
	id, err := paths.SaveLogin(credentials, catalog, "browser-alias", "")
	if err != nil || id != "business-real" {
		t.Fatalf("save login: %s %v", id, err)
	}
}
