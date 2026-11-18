package command

import (
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
	paths := localstate.Paths{Dir: t.TempDir()}
	t.Setenv("ML_JUPYTER_TOKEN", "fixture-jupyter")
	var created, deleted, executed atomic.Int32
	upgrader := websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }}
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.URL.Path == "/cli-permission/api/v1/access/check" {
			assertAccess(t, w, r, "ml jupyter exec")
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
			send(parent, "display_data", "iopub", map[string]any{"data": map[string]any{"application/vnd.wiserec.exec+json": map[string]any{
				"status": "SUCCEEDED", "exit_code": 0, "stdout": "测试\n", "stderr": "",
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
	writeConfig(t, paths, server.URL, server.URL, false)
	updateFixtureProfile(t, paths, func(profile map[string]any) {
		profile["jupyter"] = map[string]string{"server_url": server.URL + "/jupyter/"}
	})
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "jupyter", "exec", "-o", "json", "--", "echo", "测试")
	var envelope struct {
		BusinessID string         `json:"business_id"`
		Result     map[string]any `json:"result"`
	}
	if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &envelope) != nil || envelope.BusinessID != "business-real" ||
		envelope.Result["status"] != "SUCCEEDED" || envelope.Result["stdout"] != "测试\n" ||
		created.Load() != 1 || deleted.Load() != 1 || executed.Load() != 1 {
		t.Fatalf("unexpected execution: %d\n%s\n%s", code, out, stderr)
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
	writeConfig(t, paths, server.URL, server.URL, false)
	saveState(t, paths, server.URL)
	code, out, stderr := run(t, paths, "jupyter", "files", "delete", "not-empty", "-o", "json")
	if code != 1 || stderr != "" || !strings.Contains(out, "仅允许删除空目录") || writes.Load() != 0 {
		t.Fatalf("unexpected deletion: %d, %s, %s", code, out, stderr)
	}
}
