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

func multiEnvFixture(t *testing.T, endpoint, accessURL string) localstate.Paths {
	t.Helper()
	dir := t.TempDir()
	raw := fmt.Sprintf(`{
		"current":"dev",
		"profiles":[
			{"name":"dev","alias":"开发环境","api_endpoint":%q,"platform_type":"wiserec","output_format":"table"},
			{"name":"uat","alias":"测试环境","api_endpoint":%q,"platform_type":"mlops","output_format":"table"}
		],
		"access_control":{"url":%q,"enable":true}
	}`, endpoint, endpoint, accessURL)
	paths, err := localstate.NewPaths(dir, []byte(raw))
	if err != nil {
		t.Fatal(err)
	}
	return paths
}

func saveSharedEnvState(t *testing.T, paths localstate.Paths, profileName, origin, username string) {
	t.Helper()
	expiry, err := json.Marshal(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	creds := localstate.Credentials{
		Origin: origin, Profile: profileName, Username: username,
		Cookie: "fixture=local", CSRFToken: "test-csrf", ExpiresAt: expiry,
	}
	catalog := []localstate.Department{{ID: "dept-1", Name: "部门一", Tenants: []localstate.Tenant{
		{ID: "tenant-global", Name: "全局租户"},
		{ID: "tenant-a", Name: "租户A"},
		{ID: "tenant-b", Name: "租户B"},
	}}}
	if _, err := paths.WithoutSession().SaveLogin(creds, catalog, "tenant-global"); err != nil {
		t.Fatal(err)
	}
}

func TestDSHSessionCommandMatrixAndFailClosed(t *testing.T) {
	base := multiEnvFixture(t, "https://preview.example.test", "https://permissions.example.test")
	if _, err := base.LoadOrInitializeConfig(); err != nil {
		t.Fatal(err)
	}
	saveSharedEnvState(t, base, "dev", "https://preview.example.test", "alice")

	// 1. DSH_SHELL=1 without DSH_SESSION_ID must fail closed on every state command.
	broken := base.WithSession(localstate.DetectSessionScope(func(key string) (string, bool) {
		if key == "DSH_SHELL" {
			return "1", true
		}
		return "", false
	}))
	for _, args := range [][]string{{"context", "--json"}, {"env", "use", "dev"}, {"user", "info"}} {
		code, _, stderr := run(t, broken, args...)
		if code == 0 || !strings.Contains(stderr, "DSH_SESSION_ID") {
			t.Fatalf("expected fail-closed on %v: code=%d stderr=%s", args, code, stderr)
		}
	}

	// 2. Fresh DSH session (unbound env): allow bootstrap commands, reject env-dependent commands.
	sess := base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "dsh-sess-1"})
	code, out, stderr := run(t, sess, "context", "--json")
	if code != 0 || stderr != "" || !strings.Contains(out, "会话隔离 (dsh)") ||
		!strings.Contains(out, "dsh-sess-1") || !strings.Contains(out, "未绑定") {
		t.Fatalf("unbound context: code=%d out=%s stderr=%s", code, out, stderr)
	}
	code, out, _ = run(t, sess, "env", "list", "-o", "json")
	if code != 0 || !strings.Contains(out, `"dev"`) || !strings.Contains(out, `"uat"`) {
		t.Fatalf("unbound env list: code=%d out=%s", code, out)
	}
	code, out, stderr = run(t, sess, "tree", "--all")
	if code != 0 || stderr != "" || !strings.Contains(out, "当前环境：未绑定（会话模式）") {
		t.Fatalf("unbound tree --all: code=%d out=%s stderr=%s", code, out, stderr)
	}
	for _, blocked := range [][]string{{"env", "show"}, {"auth", "status"}, {"business", "list"}, {"business", "show"}, {"tree"}, {"user", "info"}} {
		code, _, stderr := run(t, sess, blocked...)
		if code == 0 || !strings.Contains(stderr, "尚未绑定环境") {
			t.Fatalf("expected unbound env block for %v: code=%d stderr=%s", blocked, code, stderr)
		}
	}

	// 3. Bind env only: allow env show, auth status, business list, tree; reject business show & user info.
	code, _, stderr = run(t, sess, "env", "use", "dev")
	if code != 0 || !strings.Contains(stderr, "尚未选择业务") {
		t.Fatalf("env use dev: code=%d stderr=%s", code, stderr)
	}
	code, out, stderr = run(t, sess, "env", "show")
	if code != 0 || stderr != "" || !strings.Contains(out, "dev") {
		t.Fatalf("env show: code=%d out=%s stderr=%s", code, out, stderr)
	}
	code, out, stderr = run(t, sess, "auth", "status")
	if code != 0 || stderr != "" || !strings.Contains(out, "alice") || !strings.Contains(out, "businessId") {
		t.Fatalf("auth status: code=%d out=%s stderr=%s", code, out, stderr)
	}
	code, out, stderr = run(t, sess, "business", "list")
	if code != 0 || stderr != "" || !strings.Contains(out, "tenant-a") || strings.Contains(out, "*当前") {
		t.Fatalf("business list unbound should have no current marker: code=%d out=%s stderr=%s", code, out, stderr)
	}
	for _, blocked := range [][]string{{"business", "show"}, {"user", "info"}} {
		code, _, stderr := run(t, sess, blocked...)
		if code == 0 || !strings.Contains(stderr, "尚未选择业务") {
			t.Fatalf("expected unbound business block for %v: code=%d stderr=%s", blocked, code, stderr)
		}
	}

	// 4. Bind tenant-a and confirm business list/show & context reflect it without altering global state.
	code, out, stderr = run(t, sess, "business", "use", "--tenant", "tenant-a")
	if code != 0 || !strings.Contains(out, "tenant-a") || !strings.Contains(stderr, "已切换") {
		t.Fatalf("business use: code=%d out=%s stderr=%s", code, out, stderr)
	}
	code, out, stderr = run(t, sess, "business", "list")
	if code != 0 || stderr != "" || !strings.Contains(out, "[tenant-a] *当前") || strings.Contains(out, "[tenant-global] *当前") {
		t.Fatalf("business list bound: code=%d out=%s stderr=%s", code, out, stderr)
	}
	code, out, stderr = run(t, base, "context", "--json")
	if code != 0 || stderr != "" || !strings.Contains(out, "全局默认") || !strings.Contains(out, "tenant-global") {
		t.Fatalf("global context altered: code=%d out=%s stderr=%s", code, out, stderr)
	}
}

func TestConcurrentSessionsDoNotCrossTalkOrTriggerTargetChanged(t *testing.T) {
	var server *httptest.Server
	server = httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			var body map[string]string
			if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
				t.Errorf("decode access body: %v", err)
				return
			}
			fmt.Fprintf(w, `{"allowed":true,"username":%q,"environment":%q}`, body["username"], body["environment"])
		case "/ai/user/info":
			biz := r.Header.Get("ai-businessId")
			if biz != r.Header.Get("businessid") {
				t.Errorf("mismatched business headers: %q vs %q", biz, r.Header.Get("businessid"))
			}
			fmt.Fprintf(w, `{"result":{"code":0,"data":{"businessId":%q}}}`, biz)
		default:
			http.NotFound(w, r)
		}
	}))
	defer server.Close()

	base := multiEnvFixture(t, server.URL, server.URL)
	if _, err := base.LoadOrInitializeConfig(); err != nil {
		t.Fatal(err)
	}
	saveSharedEnvState(t, base, "dev", server.URL, "alice")
	saveSharedEnvState(t, base, "uat", server.URL, "alice")

	sessA := base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "parallel-a"})
	sessB := base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "parallel-b"})

	if code, _, stderr := run(t, sessA, "env", "use", "dev"); code != 0 {
		t.Fatalf("sessA env use: %s", stderr)
	}
	if code, _, stderr := run(t, sessA, "business", "use", "--tenant", "tenant-a"); code != 0 {
		t.Fatalf("sessA business use: %s", stderr)
	}
	if code, _, stderr := run(t, sessB, "env", "use", "dev"); code != 0 {
		t.Fatalf("sessB env use: %s", stderr)
	}
	if code, _, stderr := run(t, sessB, "business", "use", "--tenant", "tenant-b"); code != 0 {
		t.Fatalf("sessB business use: %s", stderr)
	}

	var wg sync.WaitGroup
	errCh := make(chan error, 40)
	runLoop := func(paths localstate.Paths, expectedTenant string) {
		defer wg.Done()
		for i := 0; i < 10; i++ {
			var out, stderr bytes.Buffer
			code := Run(context.Background(), Options{
				Args: []string{"user", "info", "-o", "json"}, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) { return paths, nil },
			})
			if code != 0 || !strings.Contains(out.String(), expectedTenant) {
				errCh <- fmt.Errorf("tenant %s iter %d failed: code=%d out=%s stderr=%s", expectedTenant, i, code, out.String(), stderr.String())
				return
			}
		}
	}

	wg.Add(3)
	go runLoop(sessA, "tenant-a")
	go runLoop(sessB, "tenant-b")
	go func() {
		defer wg.Done()
		sessC := base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "parallel-c"})
		for i := 0; i < 5; i++ {
			var out, stderr bytes.Buffer
			_ = Run(context.Background(), Options{
				Args: []string{"env", "use", "uat"}, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) { return sessC, nil },
			})
			_ = Run(context.Background(), Options{
				Args: []string{"env", "use", "dev"}, Version: "1.2.3", Stdout: &out, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) { return sessC, nil },
			})
		}
	}()
	wg.Wait()
	close(errCh)
	for err := range errCh {
		t.Fatal(err)
	}

	// Verify global config.json was never modified by parallel sessions.
	raw, err := os.ReadFile(base.Config())
	if err != nil || string(raw) != `{"current":"dev"}` {
		t.Fatalf("global config modified: %s %v", raw, err)
	}
}
