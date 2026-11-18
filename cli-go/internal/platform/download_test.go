package platform

import (
	"context"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSignedLogDownloadUsesAllProxyForHTTPS(t *testing.T) {
	const content = "log from storage"
	storage := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprint(w, content)
	}))
	defer storage.Close()
	const downloadHost = "obs.invalid"
	proxy := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodConnect || r.Host != downloadHost+":443" {
			t.Errorf("unexpected proxy request %s %s", r.Method, r.Host)
			http.Error(w, "unexpected proxy request", http.StatusBadRequest)
			return
		}
		upstream, err := net.Dial("tcp", storage.Listener.Addr().String())
		if err != nil {
			t.Errorf("connect to test storage: %v", err)
			http.Error(w, "storage unavailable", http.StatusBadGateway)
			return
		}
		defer upstream.Close()
		client, buffered, err := http.NewResponseController(w).Hijack()
		if err != nil {
			t.Errorf("open tunnel: %v", err)
			return
		}
		defer client.Close()
		fmt.Fprint(buffered, "HTTP/1.1 200 Connection Established\r\n\r\n")
		if err := buffered.Flush(); err != nil {
			t.Errorf("start tunnel: %v", err)
			return
		}
		go io.Copy(upstream, buffered)
		_, _ = io.Copy(client, upstream)
	}))
	defer proxy.Close()

	for _, key := range []string{"HTTPS_PROXY", "https_proxy", "NO_PROXY", "no_proxy", "ALL_PROXY", "all_proxy"} {
		t.Setenv(key, "")
	}
	t.Setenv("all_proxy", proxy.URL)

	path, size, err := (&API{}).SignedLogDownload(t.Context(), "https://"+downloadHost+"/log.zip", "", t.TempDir(), "log", LogDownloadEvents{})
	if err != nil || size != int64(len(content)) {
		t.Fatalf("download through ALL_PROXY: %d %v", size, err)
	}
	if saved, err := os.ReadFile(path); err != nil || string(saved) != content {
		t.Fatalf("saved data: %q %v", saved, err)
	}
}

func TestSignedLogDownloadUsesSeparateHTTPSClient(t *testing.T) {
	const content = "log contents"
	server := httptest.NewTLSServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		for _, header := range []string{"Cookie", "Authorization", "businessid", "csrftoken"} {
			if r.Header.Get(header) != "" {
				t.Errorf("storage server received %s", header)
			}
		}
		switch r.URL.Path {
		case "/redirect":
			http.SetCookie(w, &http.Cookie{Name: "fixture", Value: "not-forwarded"})
			http.Redirect(w, r, "/logs?signature=fixture", http.StatusFound)
		case "/logs":
			if r.URL.Query().Get("signature") != "fixture" {
				t.Error("redirect lost its signature")
			}
			w.Header().Set("Content-Disposition", `attachment; filename="training.zip"`)
			fmt.Fprint(w, content)
		case "/downgrade":
			http.Redirect(w, r, "http://example.test/logs", http.StatusFound)
		default:
			t.Errorf("unexpected route %s", r.URL.Path)
			w.WriteHeader(http.StatusBadRequest)
		}
	}))
	defer server.Close()
	api := &API{}
	ctx := context.Background()
	dir := t.TempDir()
	var started bool
	var received []int64
	events := LogDownloadEvents{
		Start: func() { started = true },
		Progress: func(done, total int64) {
			if !started || total != int64(len(content)) {
				t.Errorf("unexpected progress %d/%d, started=%t", done, total, started)
			}
			received = append(received, done)
		},
	}
	target, size, err := api.SignedLogDownload(ctx, server.URL+"/redirect", "", dir, "fallback", events)
	if err != nil || target != filepath.Join(dir, "training.zip") || size != int64(len(content)) {
		t.Fatalf("download: %q %d %v", target, size, err)
	}
	if saved, err := os.ReadFile(target); err != nil || string(saved) != content {
		t.Fatalf("saved data: %q %v", saved, err)
	}
	if len(received) < 2 || received[0] != 0 || received[len(received)-1] != int64(len(content)) {
		t.Fatalf("missing start or final byte count: %v", received)
	}
	_, _, err = api.SignedLogDownload(ctx, server.URL+"/downgrade", "", dir, "fallback", LogDownloadEvents{})
	if err == nil || !strings.Contains(err.Error(), "跳转地址无效") {
		t.Fatalf("expected insecure redirect rejection: %v", err)
	}
	_, _, err = api.SignedDownload(ctx, server.URL+"/logs?signature=private-fixture", target, "algorithm", true)
	if err == nil || !strings.Contains(err.Error(), "证书验证失败") || strings.Contains(err.Error(), "private-fixture") {
		t.Fatalf("expected safe TLS diagnostic for algorithm download: %v", err)
	}
}
