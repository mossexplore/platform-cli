package command

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/gorilla/websocket"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestJupyterExecUsesDedicatedKernelAndCleansIt(t *testing.T) {
	script := "token = 'fixture-value'\nprint(token)"
	paths := localstate.Paths{Dir: t.TempDir()}
	t.Setenv("ML_JUPYTER_TOKEN", "fixture-jupyter")
	var created, deleted, executed, exitCode atomic.Int32
	started := make(chan struct{}, 1)
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.URL.Path == "/cli-permission/api/v1/access/check" {
			body := assertAccess(t, w, r, "ml jupyter exec")
			want := "ml jupyter exec -o json -- python -c " + quoteCommandArg(script) + " " + quoteCommandArg("")
			agentWant := strings.Replace(want, "-o json", "--agent", 1)
			if body["full_command"] != want && body["full_command"] != agentWant {
				t.Errorf("unexpected full command: %q", body["full_command"])
			}
			return
		}
		if r.Header.Get("Authorization") != "token fixture-jupyter" || r.Header.Get("Cookie") != "" || r.Header.Get("csrftoken") != "" {
			t.Error("Jupyter received wrong authentication headers")
		}
		switch r.URL.Path {
		case "/jupyter/api/contents/":
			if r.Method != http.MethodGet || r.URL.Query().Get("content") != "0" {
				t.Errorf("invalid location check %s", r.Method)
			}
			fmt.Fprintln(w, `{"type":"directory"}`)
		case "/jupyter/api/kernels":
			created.Add(1)
			body := readRequest(t, r)
			if r.Method != http.MethodPost || body["name"] != "python3" || body["path"] != "" {
				t.Errorf("invalid kernel start: %s, %v", r.Method, body)
			}
			fmt.Fprintln(w, `{"id":"fixture-kernel"}`)
		case "/jupyter/api/kernels/fixture-kernel/channels":
			connect, err := upgrader.Upgrade(w, r, nil)
			if err != nil {
				t.Error(err)
				return
			}
			defer connect.Close()
			recv := func(kind string) string {
				var message struct {
					Header  map[string]string
					Content map[string]any
				}
				if err := connect.ReadJSON(&message); err != nil {
					t.Error(err)
					return ""
				}
				if message.Header["msg_type"] != kind {
					t.Errorf("unexpected message %#v", message.Header)
				}
				if kind == "execute_request" {
					if code, _ := message.Content["code"].(string); !strings.Contains(code, "run_process") {
						t.Error("missing embedded worker")
					}
					executed.Add(1)
				}
				return message.Header["msg_id"]
			}
			send := func(parent, kind, channel string, data any) {
				err := connect.WriteJSON(map[string]any{"header": map[string]string{"msg_type": kind}, "parent_header": map[string]string{"msg_id": parent}, "channel": channel, "content": data})
				if err != nil {
					t.Error(err)
				}
			}
			parent := recv("kernel_info_request")
			send(parent, "kernel_info_reply", "shell", map[string]any{"language_info": map[string]string{"name": "python"}})
			parent = recv("execute_request")
			send("unrelated", "status", "iopub", map[string]string{"execution_state": "idle"})
			status := "SUCCEEDED"
			switch exitCode.Load() {
			case -1:
				status = "TIMED_OUT"
			case -2:
				started <- struct{}{}
				_, _, _ = connect.ReadMessage()
				return
			case 0:
			default:
				status = "FAILED"
			}
			send(parent, "display_data", "iopub", map[string]any{"data": map[string]any{"application/vnd.wiserec.exec+json": map[string]any{
				"status": status, "exit_code": exitCode.Load(), "stdout": "测试\n", "stderr": "",
			}}})
			send(parent, "execute_reply", "shell", map[string]string{"status": "ok"})
			send(parent, "status", "iopub", map[string]string{"execution_state": "idle"})
		case "/jupyter/api/kernels/fixture-kernel":
			if r.Method != http.MethodDelete {
				t.Errorf("expected DELETE, got %s", r.Method)
			}
			deleted.Add(1)
			w.WriteHeader(http.StatusNoContent)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	paths = fixtureConfig(t, paths.Dir, server.URL, server.URL, false, "mlops", server.URL+"/jupyter/")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "jupyter", "exec", "-o", "json", "--", "python", "-c", script, "")
	var envelope struct {
		BusinessID string         `json:"business_id"`
		Result     map[string]any `json:"result"`
	}
	if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &envelope) != nil || envelope.BusinessID != "business-real" ||
		envelope.Result["status"] != "SUCCEEDED" || envelope.Result["stdout"] != "测试\n" ||
		created.Load() != 1 || deleted.Load() != 1 || executed.Load() != 1 {
		t.Fatalf("unexpected execution: %d\n%s\n%s", code, out, stderr)
	}
	agent := compactResult(t, paths, "jupyter", "exec", "--agent", "--", "python", "-c", script, "")
	if agent["status"] != "SUCCEEDED" || agent["stdout"] != "测试\n" || agent["exit_code"] != float64(0) || created.Load() != 2 || executed.Load() != 2 || deleted.Load() != 2 {
		t.Fatal(agent, created.Load(), executed.Load(), deleted.Load())
	}
	for _, tc := range []struct {
		remote, exit int
		status       string
	}{
		{42, 42, "FAILED"}, {125, 125, "FAILED"}, {255, 255, "FAILED"},
		{-1, 124, "TIMED_OUT"},
	} {
		exitCode.Store(int32(tc.remote))
		code, out, stderr := run(t, paths, "jupyter", "exec", "--agent", "--", "python", "-c", script, "")
		var result struct {
			Status string `json:"status"`
			Code   int    `json:"exit_code"`
		}
		if code != tc.exit || stderr != "" || json.Unmarshal([]byte(out), &result) != nil || result.Status != tc.status || result.Code != tc.remote {
			t.Fatalf("want exit %d (%s); got %d %s %s", tc.exit, tc.status, code, out, stderr)
		}
	}
	exitCode.Store(-2)
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	go func() {
		select {
		case <-started:
			cancel()
		case <-ctx.Done():
		}
	}()
	var stdout, diagnostic bytes.Buffer
	code = Run(ctx, Options{
		Args:    []string{"jupyter", "exec", "--agent", "--", "python", "-c", script, ""},
		Version: "1.2.3", Stdout: &stdout, Stderr: &diagnostic,
		Paths: func() (localstate.Paths, error) { return paths, nil },
	})
	var interrupted struct{ Status string }
	if code != 130 || json.Unmarshal(stdout.Bytes(), &interrupted) != nil || interrupted.Status != "INTERRUPTED" ||
		!strings.Contains(diagnostic.String(), "已取消操作") {
		t.Fatal(code, stdout.String(), diagnostic.String())
	}
}

func TestJupyterFileDeletionRejectsNonemptyDirectory(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	t.Setenv("ML_JUPYTER_TOKEN", "fixture-jupyter")
	var writes atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			assertAccess(t, w, r, "ml jupyter files delete")
		case "/api/contents/not-empty":
			if r.Method != http.MethodGet {
				writes.Add(1)
			}
			fmt.Fprintln(w, `{"type":"directory","content":[{"name":"data.txt"}]}`)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
		}
	}))
	defer server.Close()
	paths = fixtureConfig(t, paths.Dir, server.URL, server.URL, false, "mlops", "")
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "jupyter", "files", "delete", "not-empty", "-o", "json")
	if code != 1 || stderr != "" || !strings.Contains(out, "仅允许删除空目录") || writes.Load() != 0 {
		t.Fatalf("unexpected deletion: %d, %s, %s", code, out, stderr)
	}
}
