package command

import (
	"encoding/json"
	"encoding/pem"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestKBFileCommands(t *testing.T) {
	const id = "00000000-0000-4000-8000-000000000000"
	const book = "PK\x03\x04\x00\xff"
	var interrupted atomic.Bool
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assertBusinessHeader(t, r)
		if r.Header.Get("Cookie") != "" || r.Header.Get("csrftoken") != "" {
			t.Error("knowledge base traffic contains platform credentials")
		}
		q := r.URL.Query()
		switch r.URL.Path {
		case "/cli-permission/api/v1/access/check":
			command, _ := readRequest(t, r)["command"].(string)
			action := map[string]string{"ml kb file list": "kb_file_list", "ml kb file download": "kb_file_download"}[command]
			if action == "" {
				t.Errorf("unexpected admission command %v", command)
			}
			fmt.Fprintf(w, `{"allowed":true,"username":"preview-user","environment":"preview","kb_ticket":{
				"ticket_id":"fixture","sig":"signed","action":%q,"username":"preview-user","environment":"preview","ak":"test","exp":1800000000}}`, action)
		case "/v1/kb/files":
			if r.Header.Get("X-KB-Action") != "kb_file_list" || q.Get("page_size") != "20" {
				t.Error("invalid file list request")
			}
			switch q.Get("page") {
			case "1":
				if q.Get("kb") != "教学资料" {
					t.Error("first page did not use requested library name")
				}
				fmt.Fprintf(w, `{"kb_id":"library","page":1,"page_size":20,"has_more":true,"items":[{"id":%q,"file_name":"报表.xlsx","folder_path":"财务","file_size":6}]}`, id)
			case "2":
				if q.Get("kb") != "library" {
					t.Error("pagination did not retain the resolved library ID")
				}
				fmt.Fprint(w, `{"kb_id":"library","page":2,"page_size":20,"has_more":false,"items":[{"id":"second","file_name":"报表.xlsx","folder_path":"项目"}]}`)
			default:
				t.Error("unexpected page", q)
			}
		case "/v1/kb/file":
			if r.Header.Get("X-KB-Action") != "kb_file_download" || q.Get("kb") != "library" || q.Get("id") != id {
				t.Error("invalid download request")
			}
			w.Header().Set("Content-Type", "application/octet-stream")
			w.Header().Set("Content-Disposition", `attachment; filename="report.xlsx"`)
			w.Header().Set("Content-Length", "6")
			if interrupted.Load() {
				fmt.Fprint(w, book[:3])
				return
			}
			fmt.Fprint(w, book)
		default:
			t.Error("unexpected request", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer server.Close()
	dir := t.TempDir()
	ca := filepath.Join(dir, "test.pem")
	if err := os.WriteFile(ca, pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: server.Certificate().Raw}), 0600); err != nil {
		t.Fatal(err)
	}
	paths, err := localstate.NewPaths(dir, []byte(fmt.Sprintf(`{"current":"preview","profiles":[{"name":"preview","api_endpoint":"https://platform.test"}],
		"access_control":{"url":%q,"ca_source":"custom","ca_file":%q},"knowledge_base":{"enable":true,"url":%q}}`, server.URL, ca, server.URL)))
	if err != nil {
		t.Fatal(err)
	}
	saveState(t, paths, "https://platform.test")

	code, out, stderr := run(t, paths, "kb", "file", "list", "--kb", "教学资料", "--all", "-o", "json")
	var result kbFiles
	if code != 0 || json.Unmarshal([]byte(out), &result) != nil || len(result.Items) != 2 ||
		result.Items[0].ID != id || result.Items[1].Folder != "项目" || result.HasMore != nil {
		t.Fatal(code, out, stderr)
	}
	first := compactResult(t, paths, "--agent", "kb", "file", "list", "--kb", "教学资料")
	last := compactResult(t, paths, "kb", "file", "list", "--kb", "教学资料", "--agent")
	if !reflect.DeepEqual(first, last) || first["has_more"] != true ||
		first["fields"].(map[string]any)["file_size"] != "文件大小（字节）" {
		t.Fatal(first, last)
	}
	t.Setenv("COLUMNS", "50")
	code, out, stderr = run(t, paths, "kb", "file", "list", "--kb", "教学资料")
	if code != 0 || !strings.Contains(out, id) || !strings.Contains(out, "知识库 ID library") || !strings.Contains(stderr, "下一页") {
		t.Fatal(code, out, stderr)
	}
	target := filepath.Join(dir, "report.xlsx")
	if err := os.WriteFile(target, []byte("existing"), 0600); err != nil {
		t.Fatal(err)
	}
	args := []string{"kb", "file", "download", id, "--kb", "library", "--file", target}
	code, out, stderr = run(t, paths, args...)
	saved, err := os.ReadFile(filepath.Join(dir, "report (1).xlsx"))
	original, _ := os.ReadFile(target)
	if code != 0 || !strings.Contains(out, "report (1).xlsx") || err != nil || string(saved) != book || string(original) != "existing" {
		t.Fatal(code, out, stderr, err)
	}
	agentTarget := filepath.Join(dir, "agent-report.xlsx")
	agent := compactResult(t, paths, "kb", "file", "download", id, "--kb", "library", "--file", agentTarget, "--agent")
	saved, err = os.ReadFile(agentTarget)
	if err != nil || string(saved) != book || agent["bytes"] != float64(len(book)) || agent["file"] != agentTarget {
		t.Fatal(agent, err)
	}
	interrupted.Store(true)
	code, out, stderr = run(t, paths, args...)
	partial, err := filepath.Glob(filepath.Join(dir, ".ml-download-*"))
	if code == 0 || len(partial) != 0 || err != nil || !strings.Contains(stderr, "未完整保存") {
		t.Fatal(code, out, stderr, partial, err)
	}
	if _, err := os.Stat(filepath.Join(dir, "report (2).xlsx")); !os.IsNotExist(err) {
		t.Fatal("incomplete download was published", err)
	}
}
