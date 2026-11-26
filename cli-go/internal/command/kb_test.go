package command

import (
	"bufio"
	"bytes"
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
)

func kbPaths(t *testing.T) localstate.Paths {
	t.Helper()
	paths, err := localstate.NewPaths(t.TempDir(), []byte(`{"current":"preview","profiles":[{"name":"preview","api_endpoint":"https://platform.test"}],"access_control":{"url":"https://permission.test"},"knowledge_base":{"enable":true,"url":"https://kb.test"}}`))
	if err != nil {
		t.Fatal(err)
	}
	return paths
}

func TestKBTreeAndLocalOverride(t *testing.T) {
	p := kbPaths(t)
	for _, enabled := range []bool{true, false} {
		raw := fmt.Sprintf(`{"enable":%t,"url":"https://other.test","default_kb":"example"}`, enabled)
		if err := os.WriteFile(filepath.Join(p.Dir, "kb.json"), []byte(raw), 0600); err != nil {
			t.Fatal(err)
		}
		cfg, err := p.KBSettings()
		if err != nil || cfg.URL != "https://kb.test" || cfg.Default != "example" {
			t.Fatal(cfg, err)
		}
		for _, args := range [][]string{{"tree", "--all"}, {"--help"}} {
			code, out, stderr := run(t, p, args...)
			if code != 0 || strings.Contains(out, "查询共享 Wiki 知识库") != enabled {
				t.Fatalf("%v: %s %s", args, out, stderr)
			}
		}
	}
}

func TestKBReadUsesOneAdmission(t *testing.T) {
	paths := kbPaths(t)
	saveState(t, paths, "https://platform.test")
	for _, mode := range []string{"signed", "legacy", "redirect"} {
		original := http.DefaultTransport
		transport := original.(*http.Transport).Clone()
		var visited []string
		transport.DialTLSContext = func(ctx context.Context, network, addr string) (net.Conn, error) {
			client, server := net.Pipe()
			go func() {
				defer server.Close()
				r, err := http.ReadRequest(bufio.NewReader(server))
				if err != nil {
					t.Error(err)
					return
				}
				visited = append(visited, r.Host+r.URL.Path)
				if r.Header.Get("businessid") != "business-real" || r.Header.Get("Cookie") != "" || r.Header.Get("csrftoken") != "" {
					t.Error("incorrect business or credential headers")
				}
				status := "200 OK"
				body := `{"items":[]}`
				switch r.Host {
				case "permission.test":
					ticket := ""
					if mode != "legacy" {
						ticket = `,"kb_ticket":{"ticket_id":"fixture","sig":"signed","action":"kb_search","username":"preview-user","environment":"preview","ak":"test","exp":1800000000}`
					}
					body = `{"allowed":true,"username":"preview-user","environment":"preview"` + ticket + "}"
				case "kb.test":
					if mode == "redirect" {
						status = "302 Found"
						body = ""
					}
					if r.Header.Get("X-KB-Action") != "kb_search" || r.URL.Query().Get("q") != "查询" {
						t.Error("incorrect gateway query")
					}
				default:
					t.Error("unexpected destination", r.Host)
				}
				fmt.Fprintf(server, "HTTP/1.1 %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n%s", status, len(body), body)
			}()
			return client, nil
		}
		http.DefaultTransport = transport
		code, out, stderr := run(t, paths, "kb", "search", "查询", "-o", "json")
		http.DefaultTransport = original
		want := "permission.test/cli-permission/api/v1/access/check"
		if mode == "legacy" {
			if code == 0 || !strings.Contains(stderr, "票据") {
				t.Fatal(code, stderr)
			}
		} else {
			want += ",kb.test/v1/kb/search"
			if mode == "redirect" {
				if code == 0 || !strings.Contains(stderr, "302") || !strings.Contains(stderr, "重定向") {
					t.Fatal(code, stderr)
				}
			} else if code != 0 || !strings.Contains(out, "items") {
				t.Fatal(code, out, stderr)
			}
		}
		if strings.Join(visited, ",") != want {
			t.Fatalf("requests: %v", visited)
		}
	}
}

func TestKBMalformedOverride(t *testing.T) {
	p := kbPaths(t)
	path := filepath.Join(p.Dir, "kb.json")
	if err := os.WriteFile(path, []byte("{"), 0600); err != nil {
		t.Fatal(err)
	}
	code, _, stderr := run(t, p, "kb", "list")
	if code == 0 || !strings.Contains(stderr, path) {
		t.Fatal(code, stderr)
	}
}
func TestKBPageTable(t *testing.T) {
	t.Setenv("COLUMNS", "45")
	slug := "summary/00000000-0000-4000-8000-000000000000"
	var out bytes.Buffer
	cmd := &cobra.Command{}
	cmd.SetOut(&out)
	raw := fmt.Sprintf(`{"page":2,"page_size":10,"total":21,"items":[{"slug":%q,"new_field":true,"rank":1}]}`, slug)
	if err := writeKBResult(cmd, "pages", "table", []byte(raw)); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(out.String(), slug) || !strings.Contains(out.String(), "第 2 页，每页 10 条，共 21 条") {
		t.Fatal(out.String())
	}
}
