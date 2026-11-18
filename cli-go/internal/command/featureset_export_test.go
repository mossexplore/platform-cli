package command

import (
	"compress/gzip"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

const featuresetExportPath = "/ai/backend/dpp/proxy/featureStore/featureset/exportFeatures"

func TestFeatureSetExportAcceptsCSVMislabeledAsJSON(t *testing.T) {
	const csv = "\ufeff特征名称,描述,扩展字段\r\nclick_label,\"逗号,换行\n双引号\"\"\",[]\r\n"
	for _, tc := range []struct {
		kind, lang string
		compressed bool
	}{
		{kind: "wide", lang: "zh_cn"},
		{kind: "model", lang: "en_us", compressed: true},
	} {
		t.Run(tc.kind, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				if r.URL.Path == "/cli-permission/api/v1/access/check" {
					assertAccess(t, w, r, "ml featureset "+tc.kind+" export")
					return
				}
				query := r.URL.Query()
				if r.URL.Path != featuresetExportPath || r.Method != http.MethodGet ||
					query.Get("setId") != "fixture-set" || query.Get("businessId") != "business-real" || query.Get("lang") != tc.lang {
					t.Errorf("unexpected export request: %s %s", r.Method, r.URL)
					w.WriteHeader(http.StatusBadRequest)
					return
				}
				w.Header().Set("Content-Type", "application/json; charset=UTF-8")
				w.Header().Set("Content-Disposition", "attachment;fileName=featuresInSet.csv")
				var body io.Writer = w
				if tc.compressed {
					w.Header().Set("Content-Encoding", "gzip")
					compressed := gzip.NewWriter(w)
					defer compressed.Close()
					body = compressed
				}
				_, _ = io.WriteString(body, csv)
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			dir := t.TempDir()
			t.Chdir(dir)
			existing := filepath.Join(dir, "featuresInSet.csv")
			if err := os.WriteFile(existing, []byte("keep"), 0600); err != nil {
				t.Fatal(err)
			}

			code, out, stderr := run(t, paths, "featureset", tc.kind, "export", "fixture-set", "--lang", tc.lang, "-o", "json")
			var result struct {
				SetID, Lang, File string
				Bytes             int64
			}
			if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &result) != nil ||
				result.SetID != "fixture-set" || result.Lang != tc.lang || result.Bytes != int64(len(csv)) ||
				!filepath.IsAbs(result.File) || filepath.Base(result.File) != "featuresInSet (1).csv" {
				t.Fatalf("unexpected export result (%d): %s %s", code, out, stderr)
			}
			for file, want := range map[string]string{existing: "keep", result.File: csv} {
				data, err := os.ReadFile(file)
				if err != nil || string(data) != want {
					t.Fatalf("unexpected bytes in %s: %q, %v", file, data, err)
				}
			}
			files, err := os.ReadDir(dir)
			if err != nil || len(files) != 2 {
				t.Fatalf("unexpected files after export: %v, %v", files, err)
			}
		})
	}
}

func TestFeatureSetExportRejectsErrorResponses(t *testing.T) {
	for _, tc := range []struct {
		name, body, message string
		status              int
	}{
		{"JSON error", `{"result":{"code":17}}`, "接口返回 JSON，未返回 CSV 文件", 200},
		{"HTML login", "<html>login</html>", "返回 HTML 页面，请重新登录", 200},
		{"version error", `{"code":"CLI_VERSION_TOO_OLD"}`, "CLI_VERSION_TOO_OLD", 200},
		{"HTTP error", `{"result":{"code":17}}`, "HTTP 403", 403},
	} {
		t.Run(tc.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				assertBusinessHeader(t, r)
				switch r.URL.Path {
				case "/cli-permission/api/v1/access/check":
					assertAccess(t, w, r, "ml featureset model export")
				case featuresetExportPath:
					w.Header().Set("Content-Type", "application/json")
					w.WriteHeader(tc.status)
					_, _ = io.WriteString(w, tc.body)
				default:
					t.Errorf("unexpected route: %s", r.URL.Path)
					w.WriteHeader(http.StatusNotFound)
				}
			}))
			defer server.Close()
			paths := fixtureConfig(t, t.TempDir(), server.URL, server.URL, false, "wiserec", "")
			saveState(t, paths, server.URL)
			dir := t.TempDir()
			code, out, stderr := run(t, paths, "featureset", "model", "export", "fixture-set", "--file", filepath.Join(dir, "features.csv"), "-o", "json")
			if code == 0 || out != "" || !strings.Contains(stderr, tc.message) {
				t.Fatalf("unexpected result (%d): %s %s", code, out, stderr)
			}
			files, err := os.ReadDir(dir)
			if err != nil || len(files) != 0 {
				t.Fatalf("failed export left files: %v, %v", files, err)
			}
		})
	}
}
