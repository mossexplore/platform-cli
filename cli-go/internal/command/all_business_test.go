package command

import (
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestAllBusinessListRequests(t *testing.T) {
	const row = `{"businessId":"other-tenant","token":"fixture-opaque"}`
	for _, tc := range []struct {
		command, manager, path, result string
		nested                         bool
	}{
		{"service list", "wiserec", "/ai/backend/mep/services/queryList", `"count":1,"services":[` + row + `]`, false},
		{"model list", "mlops", "/ai/backend/mep/models/queryList", `"count":1,"models":[` + row + `]`, false},
		{"dataset list", "wiserec", "/ai/backend/mtp/dataSet/queryList", `"totalSize":1,"data":[` + row + `]`, false},
		{"train list", "wiserec", "/ai/backend/modelDev/modelTrain/list", `"data":{"count":1,"taskInfos":[` + row + `]}`, true},
		{"train list", "mlops", "/ai/backend/mtp/traintask/queryList", `"count":1,"taskInfos":[` + row + `]`, false},
		{"algorithm list", "wiserec", "/ai/backend/modelDev/algorithmWarehouse/list", `"data":{"total":1,"list":[` + row + `]}`, true},
		{"deployment template list", "mlops", "/ai/backend/mep/scm/deploytemplate/queryList", `"count":1,"deployTemplates":[` + row + `]`, false},
		{"resource template list", "mlops", "/ai/backend/mep/resourcetemp/queryList", `"count":1,"resourceTemplateInfoList":[` + row + `]`, false},
		{"webstudio list", "mlops", "/ai/backend/webstudio/dataExplorer/queryEnvList", `"count":1,"envs":[` + row + `]`, false},
		{"mtp swanboard project list", "wiserec", "/ai/backend/mtp/swanboard/project/list", `"count":1,"data":[` + row + `]`, false},
		{"offline experiment list", "wiserec", "/ai/backend/experiment/project/list", `"total":1,"data":[` + row + `]`, false},
	} {
		t.Run(tc.manager+"/"+tc.command, func(t *testing.T) {
			var requests atomic.Int32
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					body := assertAccess(t, w, r, "ml "+tc.command)
					if body["full_command"] != "ml "+tc.command+" -A -o json" {
						t.Errorf("audit command: %v", body["full_command"])
					}
					return
				}
				requests.Add(1)
				assertBusinessHeader(t, r)
				if r.Header.Get("ai-businessId") != "business-real" || r.URL.Path != tc.path {
					t.Errorf("unexpected request path or business header: %s", r.URL.Path)
				}
				switch tc.command {
				case "offline experiment list":
					if r.Method != "GET" || r.URL.Query().Get("businessId") != "ALL" {
						t.Errorf("offline query: %s %s", r.Method, r.URL.RawQuery)
					}
				default:
					body := readRequest(t, r)
					if tc.nested {
						body, _ = body["data"].(map[string]any)
					}
					value, present := body["businessId"]
					if r.Method != "POST" || !present || value != nil {
						t.Errorf("expected explicit JSON null: %s %v", r.Method, body)
					}
					if tc.command == "service list" && body["clusterBusinessId"] != "business-real" {
						t.Errorf("clusterBusinessId: %v", body)
					}
				}
				fmt.Fprintf(w, `{"result":{"code":0,%s}}`, tc.result)
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, tc.manager, "")
			saveState(t, paths, server.URL)
			setTestAdminRole(t, paths, false, true)
			args := strings.Fields(tc.command)
			code, out, stderr := run(t, paths, append(args, "--help")...)
			if code != 0 || !strings.Contains(out, "-A, --all-business") {
				t.Fatalf("missing Go option help: %d %s %s", code, out, stderr)
			}
			code, out, stderr = run(t, paths, append(args, "-A", "-o", "json")...)
			if code != 0 || stderr != "" || !strings.Contains(out, "other-tenant") || requests.Load() != 1 {
				t.Fatalf("query: %d %s %s (requests %d)", code, out, stderr, requests.Load())
			}
			if tc.command == "webstudio list" && !strings.Contains(out, "fixture-opaque") {
				t.Fatalf("Web Studio changed a server field: %s", out)
			}
		})
	}
}

func TestAllBusinessLegacyCredentials(t *testing.T) {
	var probes, lists atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			assertAccess(t, w, r, "ml service list")
		case "/ai/user/info":
			probes.Add(1)
			fmt.Fprint(w, `{"result":{"code":0,"username":"preview-user","isSuperAdmin":true,"isAISupporter":false}}`)
		case "/ai/backend/mep/services/queryList":
			lists.Add(1)
			fmt.Fprint(w, `{"result":{"code":0,"count":1,"services":[{"serviceId":"00000000-0000-4000-8000-000000000000","businessId":"tenant-b"}]}}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)
	before := testCredentials(t, paths)
	for range 2 {
		code, out, stderr := run(t, paths, "service", "list", "--all-business")
		if code != 0 || stderr != "" || !strings.Contains(out, "业务编码") || !strings.Contains(out, "tenant-b") ||
			!strings.Contains(out, "00000000-0000-4000-8000-000000000000") {
			t.Fatalf("query: %d %s %s", code, out, stderr)
		}
	}
	after := testCredentials(t, paths)
	if after.StateID != before.StateID || !after.HasAdminFlags() || after.AdminRoleLabel() != "超级管理员" ||
		probes.Load() != 1 || lists.Load() != 2 {
		t.Fatalf("role persistence or request count: %s / %d / %d", after.AdminRoleLabel(), probes.Load(), lists.Load())
	}
	setTestAdminRole(t, paths, false, false)
	code, _, stderr := run(t, paths, "service", "list", "-A")
	if code != 1 || !strings.Contains(stderr, "不具备超级管理员") || lists.Load() != 2 {
		t.Fatalf("ordinary account: %d %s", code, stderr)
	}
}

func TestAllBusinessTreeVisibility(t *testing.T) {
	for manager, want := range map[string]int{"wiserec": 10, "mlops": 7} {
		paths := fixtureConfig(t, t.TempDir(), "https://preview.example.test", "", false, manager, "")
		saveState(t, paths, "https://preview.example.test")
		for _, enable := range []bool{false, true} {
			setTestAdminRole(t, paths, false, enable)
			code, out, stderr := run(t, paths, "tree", "--all")
			total := 0
			for line := range strings.SplitSeq(out, "\n") {
				if strings.HasSuffix(line, "支持 -A") {
					total++
				}
			}
			if code != 0 || stderr != "" || enable && total != want || !enable && total != 0 {
				t.Fatalf("%s (admin %t): %d %s %s", manager, enable, code, out, stderr)
			}
		}
	}
}

func TestFeatureTaskListUsesSelectedBusiness(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		requests.Add(1)
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			assertAccess(t, w, r, "ml feature-task list")
		case "/ai/backend/mtp/traintask/queryList":
			if body := readRequest(t, r); body["businessId"] != "business-real" {
				t.Errorf("feature task query did not use the selected business: %v", body)
			}
			fmt.Fprint(w, `{"result":{"code":0,"count":0,"taskInfos":[]}}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	setTestAdminRole(t, paths, true, false)
	for _, flag := range []string{"-A", "--all-business"} {
		code, out, stderr := run(t, paths, "feature-task", "list", flag)
		if code != 2 || out != "" || !strings.Contains(stderr, flag) {
			t.Fatalf("unsupported flag %s: %d %s %s", flag, code, out, stderr)
		}
	}
	code, out, stderr := run(t, paths, "feature-task", "list", "--help")
	if code != 0 || stderr != "" || strings.Contains(out, "--all-business") || requests.Load() != 0 {
		t.Fatalf("feature-task help or rejected flags: %d %s %s (%d requests)", code, out, stderr, requests.Load())
	}
	code, out, stderr = run(t, paths, "feature-task", "list", "-o", "json")
	if code != 0 || stderr != "" || !strings.Contains(out, `"items": []`) || requests.Load() != 2 {
		t.Fatalf("selected business query: %d %s %s (%d requests)", code, out, stderr, requests.Load())
	}
}

func TestStudioListRawOutputAndValidation(t *testing.T) {
	for _, tc := range []struct {
		name, response string
		ok             bool
	}{
		{"valid", `{"result":{"code":0,"count":1,"envs":[{"accessUrl":"https://fixture.test/?token=example"}]}}`, true},
		{"business failure", `{"result":{"code":1,"count":0,"envs":[]}}`, false},
		{"invalid count", `{"result":{"code":0,"count":null,"envs":[]}}`, false},
		{"invalid record", `{"result":{"code":0,"count":1,"envs":[null]}}`, false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					assertAccess(t, w, r, "ml webstudio list")
					return
				}
				if body := readRequest(t, r); body["businessId"] != "business-real" {
					t.Errorf("default scope: %v", body)
				}
				fmt.Fprint(w, tc.response)
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			code, out, stderr := run(t, paths, "webstudio", "list", "-o", "json")
			if tc.ok && (code != 0 || !strings.Contains(out, "token=example")) || !tc.ok && (code == 0 || out != "" || stderr == "") {
				t.Fatalf("unexpected result: %d %s %s", code, out, stderr)
			}
		})
	}
	code, _, stderr := run(t, localstate.Paths{}, "webstudio", "list", "-A", "--business-id", "other")
	if code == 0 || !strings.Contains(stderr, "不能同时使用") {
		t.Fatalf("expected flag conflict before reading configuration: %d %s", code, stderr)
	}
}

func setTestAdminRole(t *testing.T, paths localstate.Paths, superAdmin, supporter bool) {
	t.Helper()
	if err := paths.UpdateAdminFlags(testCredentials(t, paths), superAdmin, supporter); err != nil {
		t.Fatal(err)
	}
}

func testCredentials(t *testing.T, paths localstate.Paths) localstate.Credentials {
	t.Helper()
	cfg, err := localstate.LoadConfig(paths)
	if err != nil {
		t.Fatal(err)
	}
	creds, err := paths.LoadCredentials(cfg.Profile(), time.Now())
	if err != nil {
		t.Fatal(err)
	}
	return creds
}
