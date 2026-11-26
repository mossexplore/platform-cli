package weknora

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
)

type transportFunc func(*http.Request) (*http.Response, error)

func (f transportFunc) RoundTrip(r *http.Request) (*http.Response, error) { return f(r) }

const catalog = `{"data":[{"id":"shared","name":"同名","indexing_strategy":{"wiki_enabled":true}},{"id":"preview","name":"同名","indexing_strategy":{"wiki_enabled":true}},{"id":"off","name":"未启用"}]}`

func wikiClient(t *testing.T, respond func(*http.Request) string) *Client {
	t.Helper()
	visibility, err := ParseVisibility("shared,off", "preview", "test:alice")
	if err != nil {
		t.Fatal(err)
	}
	httpClient := &http.Client{Transport: transportFunc(func(r *http.Request) (*http.Response, error) {
		if r.Method != "GET" || r.Header.Get("X-API-Key") != "scoped" {
			t.Error("invalid upstream request")
		}
		body := catalog
		if r.URL.Path != "/api/v1/knowledge-bases" {
			body = respond(r)
		}
		return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(body))}, nil
	})}
	return &Client{Base: "http://upstream", Key: "scoped", Visibility: visibility, HTTP: httpClient, MaxBytes: 8192, Preview: 4}
}

func TestPreviewIsolation(t *testing.T) {
	c := wikiClient(t, func(r *http.Request) string {
		if strings.HasSuffix(r.URL.Path, "/pages") && r.URL.Query().Get("status") != "published" {
			t.Error("missing status filter")
		}
		if strings.HasSuffix(r.URL.Path, "/concept/rag") {
			return `{"slug":"concept/rag","status":"published","content":"你好"}`
		}
		return `{"pages":[],"total":0}`
	})
	for _, identity := range []struct {
		env, user string
		admin     bool
	}{{"test", "alice", true}, {"prod", "alice", false}, {"test", "bob", false}} {
		t.Run(identity.env+identity.user, func(t *testing.T) {
			t.Parallel()
			for _, action := range []string{"kb_list", "kb_page_list", "kb_search", "kb_page_show"} {
				q := url.Values{"kb": {"preview"}, "slug": {"concept/rag"}, "q": {"搜索"}}
				data, err := c.Read(context.Background(), action, identity.env, identity.user, q)
				if action == "kb_list" {
					want := 1
					if identity.admin {
						want = 2
					}
					if err != nil || len(data["items"].([]obj)) != want {
						t.Fatal(data, err)
					}
				} else if identity.admin {
					if err != nil || data["kb_id"] != "preview" {
						t.Fatal(data, err)
					}
					if action == "kb_page_show" && (data["content"] != "你" || data["truncated"] != true) {
						t.Fatal(data)
					}
				} else if !errors.Is(err, Failure{404, "KB_NOT_FOUND"}) {
					t.Fatal(err)
				}
			}
			for _, target := range []string{"", "同名"} {
				data, err := c.Read(context.Background(), "kb_page_list", identity.env, identity.user, url.Values{"kb": {target}})
				if identity.admin {
					if !errors.Is(err, Failure{400, "AMBIGUOUS_KB_USE_ID"}) || len(data["candidates"].([]obj)) != 2 {
						t.Fatal(data, err)
					}
				} else if err != nil || data["kb_id"] != "shared" {
					t.Fatal(data, err)
				}
			}
		})
	}
}
func TestSearchWindow(t *testing.T) {
	for _, test := range []struct {
		body      string
		rows      int
		exhausted bool
	}{
		{`{"pages":[]}`, 0, false},
		{`{"pages":[{"status":"draft"},{"status":"draft"},{"status":"draft"}]}`, 0, true},
		{`{"pages":[{"status":"draft"},{"status":"published"}]}`, 1, false},
	} {
		c := wikiClient(t, func(r *http.Request) string {
			if r.URL.Query().Get("limit") != "3" || r.URL.Query().Get("q") != `\[ERROR\] \(timeout\)\.\*\$` {
				t.Fatal(r.URL)
			}
			return test.body
		})
		data, err := c.Read(context.Background(), "kb_search", "prod", "alice", url.Values{"q": {"[ERROR] (timeout).*$"}, "limit": {"1"}})
		if err != nil || len(data["items"].([]obj)) != test.rows || data["candidate_window_exhausted"] != test.exhausted {
			t.Fatal(data, err)
		}
	}
}
func TestInvalidUpstreamAndSlug(t *testing.T) {
	for _, slug := range []string{"../secret", "a//b", `a\b`, "a\nb"} {
		if _, err := slugPath(slug); err == nil {
			t.Fatal(slug)
		}
	}
	if _, err := ParseVisibility("shared", "shared", ""); err == nil {
		t.Fatal("overlapping lists")
	}
	for _, test := range []struct {
		body    string
		failure Failure
	}{{`{}`, upstream}, {strings.Repeat(" ", 9000), Failure{502, "UPSTREAM_RESPONSE_TOO_LARGE"}}} {
		c := wikiClient(t, func(*http.Request) string { return test.body })
		if _, err := c.Read(context.Background(), "kb_page_list", "prod", "alice", nil); !errors.Is(err, test.failure) {
			t.Fatal(err)
		}
	}
}
