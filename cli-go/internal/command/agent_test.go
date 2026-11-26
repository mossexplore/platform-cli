package command

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"unicode"
	"unicode/utf8"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func compactResult(t *testing.T, paths localstate.Paths, args ...string) map[string]any {
	t.Helper()
	code, out, stderr := run(t, paths, args...)
	var result map[string]any
	if code != 0 || strings.Count(out, "\n") != 1 || json.Unmarshal([]byte(out), &result) != nil {
		t.Fatalf("%v: %d %q %q", args, code, out, stderr)
	}
	return result
}

func TestAgentSelection(t *testing.T) {
	paths := kbPaths(t)
	t.Setenv("ML_AGENT", "1")
	compactResult(t, paths, "context")
	for _, args := range [][]string{{"context", "--json"}, {"--agent=false", "context", "--json"}} {
		code, out, _ := run(t, paths, args...)
		if code != 0 || !strings.Contains(out, "\n  ") {
			t.Fatal(args, code, out)
		}
	}
	for _, args := range [][]string{{"--agent", "context", "--json"}, {"dataset", "list", "-o", "table", "--agent"}, {"--agent", "kb", "file", "list", "--output", "json"}} {
		var out, stderr bytes.Buffer
		code := Run(context.Background(), Options{Args: args, Stdout: &out, Stderr: &stderr, Version: "test", Paths: func() (localstate.Paths, error) { t.Fatal("conflict read state"); return paths, nil }, KBSettings: paths.KBSettings})
		if code != 2 || out.Len() != 0 || !strings.Contains(stderr.String(), "不能与") {
			t.Fatal(args, code, out.String(), stderr.String())
		}
	}
	for _, args := range [][]string{{"--agent", "tree", "--all"}, {"tree", "--all", "--agent"}} {
		tree := compactResult(t, paths, args...)
		nodes := tree["commands"].([]any)
		if nodes[0].(map[string]any)["name"] != "kb" {
			t.Fatal("missing conditional KB commands")
		}
	}
	code, tree, stderr := run(t, paths, "tree", "--all", "--agent=false")
	if code != 0 {
		t.Fatal(stderr)
	}
	for _, line := range strings.Split(tree, "\n") {
		_, label, found := strings.Cut(line, "── ")
		if !found {
			continue
		}
		_, summary, found := strings.Cut(label, "  ")
		if !found {
			t.Fatal(line)
		}
		summary, _, _ = strings.Cut(summary, "  ")
		last, _ := utf8.DecodeLastRuneInString(summary)
		if summary == "" || unicode.IsPunct(last) {
			t.Fatal("invalid command tree description", line)
		}
	}
	if result := compactResult(t, paths, "auth", "ping", "tick", "--capabilities"); result["protocol"] == nil || result["budget_ms"] == nil {
		t.Fatal(result)
	}
}

func TestAgentRegisteredInvocations(t *testing.T) {
	paths := kbPaths(t)
	root := newRoot(Options{KBSettings: paths.KBSettings, Version: "test"})
	var visit func(*cobra.Command)
	visit = func(cmd *cobra.Command) {
		if cmd.Runnable() {
			t.Run(cmd.CommandPath(), func(t *testing.T) {
				args := append([]string{"--agent"}, strings.Fields(cmd.CommandPath())[1:]...)
				code, out, stderr := run(t, paths, append(args, "--help")...)
				if code != 0 || !strings.Contains(out, "--agent") || !strings.Contains(out, cmd.CommandPath()) || stderr != "" {
					t.Fatal(args, code, out, stderr)
				}
				// Exercise the runnable entry point as well as help. Stop at the
				// configuration boundary so mutations, downloads and login cannot run.
				if cmd == root || cmd.CommandPath() == "ml service" {
					return
				}
				cmd.LocalNonPersistentFlags().VisitAll(func(flag *pflag.Flag) {
					if isRequiredHelpFlag(flag) {
						args = append(args, "--"+flag.Name, "fixture")
					}
				})
				for _, name := range strings.Fields(cmd.Use)[1:] {
					if strings.HasPrefix(name, "[") || name == "--" {
						continue
					}
					args = append(args, "fixture")
				}
				switch cmd.CommandPath() {
				case "ml business":
					args = append(args, "tenant")
				case "ml auth ping tick":
					args = append(args, "--capabilities")
				}
				var result, diagnostic bytes.Buffer
				code = Run(context.Background(), Options{Args: args, Version: "test", Stdout: &result, Stderr: &diagnostic, KBSettings: paths.KBSettings, Paths: func() (localstate.Paths, error) { return localstate.Paths{}, errors.New("fixture unavailable") }})
				switch cmd.CommandPath() {
				case "ml jupyter terminal open", "ml jupyter terminal attach":
					if code != 1 || result.Len() != 0 || !strings.Contains(diagnostic.String(), "交互式终端") {
						t.Fatal(args, code, result.String(), diagnostic.String())
					}
				default:
					if strings.HasPrefix(cmd.CommandPath(), "ml jupyter files ") || cmd.CommandPath() == "ml jupyter exec" {
						var failure struct{ Status, Error string }
						if code != 1 || diagnostic.Len() != 0 || json.Unmarshal(result.Bytes(), &failure) != nil || failure.Status != "FAILED" || failure.Error != "fixture unavailable" {
							t.Fatal(args, code, result.String(), diagnostic.String())
						}
					} else if code != 1 || result.Len() != 0 || !strings.Contains(diagnostic.String(), "fixture unavailable") {
						t.Fatal(args, code, result.String(), diagnostic.String())
					}
				}

			})
		}
		for _, child := range cmd.Commands() {
			visit(child)
		}
	}
	visit(root)
}

func TestAgentQueryWorkflow(t *testing.T) {
	desc := strings.Repeat("汉", 257)
	hosts := make([]map[string]any, 10)
	for i := range hosts {
		hosts[i] = map[string]any{"nodeName": fmt.Sprintf("pod-%d", i), "clusterName": "cluster", "health_status": 0}
	}
	hostPage, err := json.Marshal(map[string]any{"result": map[string]any{"code": 0, "count": 23, "data": hosts}})
	if err != nil {
		t.Fatal(err)
	}
	for _, tc := range []struct {
		args, reply, mode string
		total             any
	}{
		{"dataset list --page 2", fmt.Sprintf(`{"result":{"code":0,"totalSize":21,"data":[{"dataSetId":"ds","description":%q,"fileSize":0,"modifyTime":"2026-09-08T06:54:36.000+00:00","ignored":"noise"}]}}`, desc), "paged", float64(21)},
		{"service host list svc", string(hostPage), "fixedFirstPage", float64(23)},
		{"service deployment list svc", `{"result":{"code":0,"data":[]}}`, "fixedFirstPage", nil},
		{"train history list task", `{"result":{"code":0,"count":1,"jobs":[{"jobId":"job","jobType":"dps-train","roleJobInfo":[{"roleJobId":"a","sysParam":"{\"plogUploadSuccess\":\"1\"}"},{"roleJobId":"b","sysParam":"{}"}]}]}}`, "paged", float64(1)},
	} {
		t.Run(tc.args, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					fmt.Fprint(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
					return
				}
				fmt.Fprint(w, tc.reply)
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			v := compactResult(t, paths, append(strings.Fields(tc.args), "--agent")...)
			items := v["items"].([]any)
			if v["returnedCount"] != float64(len(items)) || v["pagination"] != tc.mode || v["total"] != tc.total {
				t.Fatal(v)
			}
			switch {
			case strings.HasPrefix(tc.args, "service host"):
				if len(items) != 10 || v["pageIndex"] != float64(1) || v["pageSize"] != float64(10) {
					t.Fatal(v)
				}
				for i, raw := range items {
					row := raw.(map[string]any)
					if row["nodeName"] != fmt.Sprintf("pod-%d", i) || row["clusterName"] != "cluster" || row["health_status"] != float64(0) {
						t.Fatal(row)
					}
				}
			case strings.HasPrefix(tc.args, "dataset"):
				r := items[0].(map[string]any)
				if r["fileSize"] != float64(0) || r["ignored"] != nil || r["modifyTime"] != "2026-09-08 14:54:36" || r["description"] != strings.Repeat("汉", 256) || r["_truncated"].(map[string]any)["description"] != float64(257) {
					t.Fatal(r)
				}
			case strings.HasPrefix(tc.args, "train"):
				roles := items[0].(map[string]any)["roleJobInfo"].([]any)
				if roles[0].(map[string]any)["plogReady"] != true || roles[1].(map[string]any)["plogReady"] != false || roles[0].(map[string]any)["roleJobId"] != "a" {
					t.Fatal(roles)
				}
			}
		})
	}
}

func TestAgentConfigPreservesDocument(t *testing.T) {
	const config = `{"null":null,"array":[],"object":{},"empty":"","false":false,"integer":9007199254740993}`
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if strings.HasSuffix(r.URL.Path, "/access/check") {
			assertAccess(t, w, r, "ml featureset wide config")
			return
		}
		fmt.Fprintf(w, `{"result":{"code":0,"des":"success","featureJson":%q}}`, config)
	}))
	defer server.Close()
	paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "featureset", "wide", "config", "set", "--agent")
	if code != 0 || out != config+"\n" {
		t.Fatal(code, out, stderr)
	}
}

func TestAgentMockKeepsPartialFailure(t *testing.T) {
	var stdout, stderr bytes.Buffer
	cmd := &cobra.Command{}
	cmd.SetOut(&output.AgentWriter{Writer: &stdout})
	cmd.SetErr(&stderr)
	var result platform.Record
	if err := json.Unmarshal([]byte(`{"nodeList":[{"hostName":"a","retCode":0,"mockResponse":"{}"},{"hostName":"b","retCode":3,"mockResponse":"unavailable"}]}`), &result); err != nil {
		t.Fatal(err)
	}
	err := renderServiceMock(cmd, nil, result, "json", false)
	var response struct {
		NodeList []struct {
			HostName     string
			RetCode      int
			MockResponse any
		}
	}
	if err != silentExit(1) || !strings.Contains(stderr.String(), "b") || json.Unmarshal(stdout.Bytes(), &response) != nil || len(response.NodeList) != 2 || response.NodeList[1].RetCode != 3 || response.NodeList[1].MockResponse != "unavailable" {
		t.Fatal(err, stdout.String(), stderr.String())
	}
}

func TestAgentListCommandSchemas(t *testing.T) {
	for _, tc := range []struct{ args, rows, mode string }{
		{"model list", "models", "paged"}, {"service list", "services", "paged"},
		{"resource template list", "resourceTemplateInfoList", "paged"}, {"deployment template list", "deployTemplates", "paged"},
		{"feature-task list", "taskInfos", "paged"}, {"feature-task execution list task", "jobs", "paged"},
		{"featureset wide list", "featureSetInfoList", "paged"}, {"featureset model list", "featureSetInfoList", "paged"},
		{"quality feature list", "featureList", "paged"}, {"quality wide-featureset list", "featureSetList", "paged"},
		{"quality wide-featureset label-assemble feature list --set-id s --definition-id d", "featureList", "paged"},
		{"quality wide-featureset feature-assemble feature list --set-id s --definition-id d", "featureList", "paged"},
		{"quality wide-featureset label-assemble list --set-id s", "sampleDefinitionList", "unpaged"},
		{"quality wide-featureset feature-assemble list --set-id s", "sampleDefinitionList", "unpaged"},
		{"algorithm list", "data.list", "paged"}, {"sample-task list", "taskInfos", "paged"}, {"sample-task list --source new", "data.list", "paged"},
		{"sample-task execution list task", "jobs", "paged"}, {"sample-task period list task", "instances", "paged"}, {"webstudio list", "envs", "paged"},
		{"offline experiment list", "data", "paged"}, {"offline experiment trial list project", "data", "paged"},
		{"mtp swanboard project list", "data", "paged"}, {"mtp swanboard project namespace list project", "data", "unpaged"},
		{"mtp swanboard experiment feature list experiment", "data", "paged"}, {"train list", "data.taskInfos", "paged"},
	} {
		t.Run(tc.args, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				if strings.HasSuffix(r.URL.Path, "/access/check") {
					fmt.Fprint(w, `{"allowed":true,"username":"preview-user","environment":"preview"}`)
					return
				}
				result := map[string]any{"code": 0, "count": 0, "totalCount": 0, "total": 0}
				fields := strings.Split(tc.rows, ".")
				if len(fields) == 2 {
					result[fields[0]] = map[string]any{fields[1]: []any{}, "total": 0, "count": 0}
				} else {
					result[tc.rows] = []any{}
				}
				if err := json.NewEncoder(w).Encode(map[string]any{"result": result}); err != nil {
					t.Error(err)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			v := compactResult(t, paths, append([]string{"--agent"}, strings.Fields(tc.args)...)...)
			items, ok := v["items"].([]any)
			if !ok || len(items) != 0 || v["returnedCount"] != float64(0) || v["pagination"] != tc.mode {
				t.Fatal(v)
			}
		})
	}
}
