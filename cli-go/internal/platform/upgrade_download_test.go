package platform

import (
	"bytes"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSaveUpgradeMSI(t *testing.T) {
	payload := append(bytes.Clone(msiFileHeader), []byte("fixture data")...)
	for _, test := range []struct {
		name   string
		body   []byte
		size   int64
		status int
		err    string
	}{
		{"complete", payload, int64(len(payload)), http.StatusOK, ""},
		{"unknown length", payload, -1, http.StatusOK, ""},
		{"partial", payload, int64(len(payload) + 1), http.StatusOK, "下载未完成"},
		{"page", []byte("<html>download page</html>"), -1, http.StatusOK, "未返回 MSI"},
		{"oversize", payload, maxUpgradeBytes + 1, http.StatusOK, "超过 256 MiB"},
		{"gateway error", payload, -1, http.StatusForbidden, "HTTP 403"},
	} {
		t.Run(test.name, func(t *testing.T) {
			destination := filepath.Join(t.TempDir(), "upgrade.msi")
			response := &http.Response{StatusCode: test.status, ContentLength: test.size,
				Body: io.NopCloser(bytes.NewReader(test.body))}
			var received int64
			err := saveUpgradeMSI(response, destination, func(n, total int64) {
				received = n
				if total != test.size {
					t.Fatalf("reported total %d, want %d", total, test.size)
				}
			})
			if test.err != "" {
				if err == nil || !strings.Contains(err.Error(), test.err) {
					t.Fatalf("expected %q, got %v", test.err, err)
				}
				return
			}
			if err != nil || received != int64(len(payload)) {
				t.Fatalf("download failed: %d bytes, %v", received, err)
			}
			got, err := os.ReadFile(destination)
			if err != nil || !bytes.Equal(got, payload) {
				t.Fatalf("downloaded file: %q %v", got, err)
			}
		})
	}
}
