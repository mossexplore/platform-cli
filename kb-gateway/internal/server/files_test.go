package server

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"mime"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/kb-gateway/internal/weknora"
)

func TestFileGrantsAndDownload(t *testing.T) {
	const file = "PK\x03\x04\x00\xff"
	const alice = "test:alice:"
	const workbook = `{"id":"file-id","knowledge_base_id":"one","file_name":"报表.xlsx","folder_path":"资料","file_path":"private-path","file_size":6,"updated_at":"2026-09-08T06:54:36Z"}`
	const foreign = `{"id":"other-id","knowledge_base_id":"two","file_name":"禁止.xlsx","file_path":"foreign-path","file_size":6}`
	upstream := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-API-Key") != "upstream-key" || r.Header.Get("X-KB-User") != "" {
			t.Error("incorrect upstream credentials")
		}
		switch r.URL.Path {
		case "/api/v1/knowledge-bases":
			fmt.Fprint(w, `{"data":[{"id":"one","name":"资料一"},{"id":"two","name":"资料二"}]}`)
		case "/api/v1/knowledge-bases/one/knowledge":
			fmt.Fprintf(w, `{"data":[%s,{"id":"manual","knowledge_base_id":"one","file_name":"手工.md"}],"total":3}`, workbook)
		case "/api/v1/knowledge/file-id":
			fmt.Fprintf(w, `{"data":%s}`, workbook)
		case "/api/v1/knowledge/other-id":
			fmt.Fprintf(w, `{"data":%s}`, foreign)
		case "/api/v1/knowledge/large-id":
			fmt.Fprint(w, `{"data":{"id":"large-id","knowledge_base_id":"one","file_name":"large.xlsx","file_path":"private-path","file_size":7}}`)
		case "/api/v1/knowledge/file-id/download":
			fmt.Fprint(w, file)
		default:
			t.Errorf("unexpected upstream request %s", r.URL.Path)
			http.NotFound(w, r)
		}
	}))
	defer upstream.Close()
	visibility, err := weknora.ParseVisibility("one,two", "", "")
	if err != nil {
		t.Fatal(err)
	}
	list, err := weknora.ParseFileGrants(alice + "one,test:bob:one")
	if err != nil {
		t.Fatal(err)
	}
	download, err := weknora.ParseFileGrants(alice + "one")
	if err != nil {
		t.Fatal(err)
	}
	client := &weknora.Client{Base: upstream.URL, Key: "upstream-key", HTTP: upstream.Client(), Visibility: visibility,
		FileList: list, FileDownload: download, MaxFileBytes: 6, MaxBytes: 4096}
	key := strings.Repeat("k", 32)
	s := New(client, map[string]string{"ak": key}, []netip.Prefix{netip.MustParsePrefix("127.0.0.0/8")}, t.TempDir(), 20, 40)
	for _, tc := range []struct {
		path, user, action string
		status             int
	}{
		{"/v1/kb/files?kb=one&page_size=2", "bob", "kb_file_list", 200},
		{"/v1/kb/file?kb=one&id=file-id", "bob", "kb_file_download", 404},
		{"/v1/kb/file?kb=one&id=file-id", "alice", "kb_file_list", 403},
		{"/v1/kb/files?kb=two", "alice", "kb_file_list", 404},
		{"/v1/kb/file?kb=one&id=other-id", "alice", "kb_file_download", 404},
		{"/v1/kb/file?kb=one&id=large-id", "alice", "kb_file_download", 413},
		{"/v1/kb/file?kb=one&id=file-id", "alice", "kb_file_download", 200},
	} {
		r := httptest.NewRequest("GET", tc.path, nil)
		r.RemoteAddr = "127.0.0.1:42"
		fields := []string{"ak", "12345678-1234-4abc-8def-123456789abc", tc.user, "test", tc.action, strconv.FormatInt(time.Now().Unix()+300, 10)}
		for i, h := range []string{"AK", "Ticket-ID", "User", "Env", "Action", "Exp"} {
			r.Header.Set("X-KB-"+h, fields[i])
		}
		mac := hmac.New(sha256.New, []byte(key))
		fmt.Fprint(mac, "v1\n"+strings.Join(fields, "\n"))
		r.Header.Set("X-KB-Signature", hex.EncodeToString(mac.Sum(nil)))
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != tc.status {
			t.Fatalf("%+v: %d %s", tc, w.Code, w.Body)
		}
		if w.Code == 200 && tc.action == "kb_file_download" {
			media, params, err := mime.ParseMediaType(w.Header().Get("Content-Disposition"))
			if err != nil || media != "attachment" || params["filename"] != "报表.xlsx" ||
				w.Header().Get("Content-Length") != "6" || w.Body.String() != file {
				t.Fatal(w.Header(), w.Body)
			}
		}
		if w.Code == 200 && tc.action == "kb_file_list" {
			body := w.Body.String()
			for _, want := range []string{`"file_name":"报表.xlsx"`, `"has_more":true`, "2026-09-08 14:54:36"} {
				if !strings.Contains(body, want) {
					t.Errorf("missing %q in %s", want, body)
				}
			}
			if strings.Contains(body, "private-path") || strings.Contains(body, "手工.md") {
				t.Fatal(body)
			}
		}
	}
}

func TestCopyFileRejectsIncompleteOrOversizeBody(t *testing.T) {
	for _, body := range []string{"", "x", "xxx"} {
		var out bytes.Buffer
		if err := copyFile(&out, strings.NewReader(body), 2); err == nil || out.Len() >= 2 {
			t.Fatalf("accepted mismatched download %q: %q, %v", body, out.Bytes(), err)
		}
	}
}
