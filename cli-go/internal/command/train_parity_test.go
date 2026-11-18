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

func TestTrainListUsesCorrectManagerProtocol(t *testing.T) {
	for _, profile := range []string{"wiserec", "mlops"} {
		t.Run(profile, func(t *testing.T) {
			paths := localstate.Paths{Dir: t.TempDir()}
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					assertAccess(t, w, r, "ml train list")
					return
				}
				body := readRequest(t, r)
				endpoint := "/ai/backend/mtp/traintask/queryList"
				if profile == "wiserec" {
					endpoint = "/ai/backend/modelDev/modelTrain/list"
					if nested, ok := body["data"].(map[string]any); ok {
						body = nested
					} else {
						t.Error("WiseRec request does not wrap data")
					}
				}
				if r.URL.Path != endpoint || body["businessId"] != "business-real" ||
					body["pageIndex"] != float64(2) || body["pageSize"] != float64(7) || body["taskName"] != "样例" {
					t.Errorf("unexpected %s request: %s %v", profile, r.URL.Path, body)
				}
				if profile == "wiserec" {
					fmt.Fprintln(w, `{"result":{"code":0,"data":{"count":21,"taskInfos":[{"taskId":"00000000-0000-4000-8000-000000000000","updateTime":"2026-09-08T06:54:36.000+00:00","extension":{"any":true}}]}}}`)
				} else {
					if _, exists := body["reverseTags"]; exists {
						t.Error("WiseRec-only filter sent to MLOps")
					}
					fmt.Fprintln(w, `{"result":{"code":0,"count":0}}`)
				}
			}))
			defer server.Close()
			paths = fixtureConfig(t, paths.Dir, server.URL, server.URL, false, profile, "")
			saveState(t, paths, server.URL)
			code, out, stderr := run(t, paths, "train", "list", "--page", "2", "--page-size", "7", "--name", "样例", "-o", "json")
			if code != 0 || stderr != "" {
				t.Fatalf("train list failed: %d %s %s", code, out, stderr)
			}
			var result struct {
				Count, PageIndex, PageSize int
				Items                      []map[string]json.RawMessage
			}
			if json.Unmarshal([]byte(out), &result) != nil || result.PageIndex != 2 || result.PageSize != 7 {
				t.Fatalf("unexpected result: %s", out)
			}
			if profile == "mlops" && (result.Count != 0 || result.Items == nil || len(result.Items) != 0) {
				t.Fatalf("empty MLOps result: %s", out)
			}
			if profile == "wiserec" && (result.Count != 21 || len(result.Items) != 1 || result.Items[0]["extension"] == nil) {
				t.Fatalf("unexpected WiseRec result: %s", out)
			}
		})
	}
}

func TestTrainingMutationStopsAfterBusinessChange(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	var probes, deletes atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			if probes.Add(1) == 2 {
				settings, err := localstate.LoadConfig(paths)
				if err != nil {
					t.Error(err)
					return
				}
				creds, err := paths.LoadCredentials(settings.Profile(), time.Now())
				if err != nil {
					t.Error(err)
					return
				}
				if _, err := paths.SelectBusiness(settings.Profile(), creds, "dept", "tenant", ""); err != nil {
					t.Error(err)
					return
				}
			}
			body := assertAccess(t, w, r, "ml train delete")
			if body["full_command"] != "ml train delete fixture-task --yes" {
				t.Errorf("incorrect audit command: %v", body["full_command"])
			}
		case "/ai/backend/mtp/traintask/queryList":
			fmt.Fprintln(w, `{"result":{"code":0,"count":1,"taskInfos":[{"taskId":"fixture-task","taskName":"待删除","teamId":"team"}]}}`)
		case "/ai/backend/modelDev/modelTrain/v2/delete":
			deletes.Add(1)
			fmt.Fprintln(w, `{"result":{"code":0}}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	paths = fixtureConfig(t, paths.Dir, server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	code, _, stderr := run(t, paths, "train", "delete", "fixture-task", "--yes")
	if code == 0 || !strings.Contains(stderr, "业务已变化") || probes.Load() != 2 || deletes.Load() != 0 {
		t.Fatalf("unsafe delete: code=%d %s, probes=%d deletes=%d", code, stderr, probes.Load(), deletes.Load())
	}
}

func assertBusinessHeader(t *testing.T, r *http.Request) {
	t.Helper()
	if r.Header.Get("businessid") != "business-real" {
		t.Errorf("wrong business ID in %s", r.URL.Path)
	}
}
func assertAccess(t *testing.T, w http.ResponseWriter, r *http.Request, command string) map[string]any {
	t.Helper()
	body := readRequest(t, r)
	if r.Header.Get("Cookie") != "" || r.Header.Get("csrftoken") != "" || body["command"] != command {
		t.Errorf("unexpected permission request for %s", command)
	}
	fmt.Fprintln(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
	return body
}
func readRequest(t *testing.T, r *http.Request) map[string]any {
	t.Helper()
	var body map[string]any
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		t.Error(err)
	}
	return body
}
