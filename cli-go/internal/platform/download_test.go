package platform

import (
	"context"
	"fmt"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

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
	target, size, err := api.SignedLogDownload(ctx, server.URL+"/redirect", "", dir, "fallback")
	if err != nil || target != filepath.Join(dir, "training.zip") || size != int64(len(content)) {
		t.Fatalf("download: %q %d %v", target, size, err)
	}
	if saved, err := os.ReadFile(target); err != nil || string(saved) != content {
		t.Fatalf("saved data: %q %v", saved, err)
	}
	_, _, err = api.SignedLogDownload(ctx, server.URL+"/downgrade", "", dir, "fallback")
	if err == nil || !strings.Contains(err.Error(), "跳转地址无效") {
		t.Fatalf("expected insecure redirect rejection: %v", err)
	}
	_, _, err = api.SignedDownload(ctx, server.URL+"/logs?signature=private-fixture", target, "algorithm", true)
	if err == nil || !strings.Contains(err.Error(), "证书验证失败") || strings.Contains(err.Error(), "private-fixture") {
		t.Fatalf("expected safe TLS diagnostic for algorithm download: %v", err)
	}
}
