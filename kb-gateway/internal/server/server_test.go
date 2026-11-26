package server

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/kb-gateway/internal/weknora"
)

type fixedCatalog struct{}

func (fixedCatalog) RoundTrip(*http.Request) (*http.Response, error) {
	return &http.Response{StatusCode: 200, Body: io.NopCloser(strings.NewReader(`{"data":[]}`))}, nil
}

func TestRouteAdmissionAndAudit(t *testing.T) {
	key := strings.Repeat("k", 32)
	dir := t.TempDir()
	s := New(&weknora.Client{Base: "http://upstream", HTTP: &http.Client{Transport: fixedCatalog{}}, MaxBytes: 1024}, map[string]string{"ak": key}, []netip.Prefix{netip.MustParsePrefix("127.0.0.0/8")}, dir, 20, 40)
	id := "12345678-1234-4abc-8def-123456789abc"
	for _, test := range []struct {
		method, path string
		ticket       bool
		status       int
	}{
		{"GET", "/health", false, 200}, {"POST", "/v1/kb/list", false, 405}, {"PUT", "/v1/kb/list", false, 405}, {"DELETE", "/v1/kb/list", false, 405}, {"GET", "/extra", false, 404}, {"GET", "/v1/kb/list", false, 401}, {"GET", "/v1/kb/page", true, 403}, {"GET", "/v1/kb/list?q=token%3Dprivate", true, 200},
	} {
		r := httptest.NewRequest(test.method, test.path, nil)
		r.RemoteAddr = "127.0.0.1:42"
		r.Header.Set("X-KB-User", "unverified")
		if test.ticket {
			exp := strconv.FormatInt(time.Now().Unix()+300, 10)
			fields := []string{"ak", id, "alice", "test", "kb_list", exp}
			for i, h := range []string{"AK", "Ticket-ID", "User", "Env", "Action", "Exp"} {
				r.Header.Set("X-KB-"+h, fields[i])
			}
			mac := hmac.New(sha256.New, []byte(key))
			io.WriteString(mac, "v1\n"+strings.Join(fields, "\n"))
			r.Header.Set("X-KB-Signature", hex.EncodeToString(mac.Sum(nil)))
		}
		w := httptest.NewRecorder()
		s.ServeHTTP(w, r)
		if w.Code != test.status {
			t.Fatalf("%v: %d %s", test, w.Code, w.Body)
		}
	}
	files, _ := filepath.Glob(filepath.Join(dir, "*.jsonl"))
	if len(files) != 1 {
		t.Fatal(files)
	}
	raw, err := os.ReadFile(files[0])
	if err != nil {
		t.Fatal(err)
	}
	records := strings.Split(strings.TrimSpace(string(raw)), "\n")
	if len(records) != 3 || strings.Contains(string(raw), "private") {
		t.Fatalf("unexpected records: %s", raw)
	}
	for i, status := range []int{401, 403, 200} {
		var entry struct {
			Ticket                 string `json:"ticket_id"`
			Timestamp, Actor, Code string
			Status                 int
		}
		if err := json.Unmarshal([]byte(records[i]), &entry); err != nil || entry.Status != status {
			t.Fatal(records[i], err)
		}
		if status == 401 && (entry.Ticket != "" || entry.Actor != "" || entry.Code != "INVALID_TICKET") {
			t.Fatal(entry)
		}
		if status != 401 && (entry.Ticket != id || entry.Actor != "alice") {
			t.Fatal(entry)
		}
		if status == 403 && entry.Code != "ACTION_DENIED" {
			t.Fatal(entry)
		}
		if _, err := time.Parse(time.DateTime, entry.Timestamp); err != nil {
			t.Fatal(err)
		}
	}
}

func TestProxyTrustControlsRateLimitKey(t *testing.T) {
	loopback := netip.MustParsePrefix("127.0.0.0/8")
	for _, test := range []struct {
		name    string
		trusted []netip.Prefix
		headers []string
		want    []int
	}{
		{"direct", nil, []string{"192.0.2.1", "192.0.2.2"}, []int{401, 429}},
		{"trusted", []netip.Prefix{loopback}, []string{"192.0.2.1", "::ffff:192.0.2.1", "192.0.2.2"}, []int{401, 429, 401}},
		{"other proxy", []netip.Prefix{netip.MustParsePrefix("192.0.2.0/24")}, []string{"bad", "192.0.2.1"}, []int{401, 429}},
	} {
		t.Run(test.name, func(t *testing.T) {
			s := New(nil, nil, []netip.Prefix{loopback}, t.TempDir(), 1, 1)
			s.TrustedProxies = test.trusted
			for i, ip := range test.headers {
				r := httptest.NewRequest("GET", "/v1/kb/list", nil)
				r.RemoteAddr = "127.0.0.1:42"
				r.Header.Set("X-Real-IP", ip)
				w := httptest.NewRecorder()
				s.ServeHTTP(w, r)
				if w.Code != test.want[i] {
					t.Fatalf("%s: %d", ip, w.Code)
				}
			}
		})
	}
}
