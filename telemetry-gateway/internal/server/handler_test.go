package server

import (
	"bytes"
	"compress/gzip"
	"context"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/http/httptest"
	"net/netip"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
)

const trace = `{"resourceSpans":[{"resource":{"attributes":[{"key":"service.name","value":{"stringValue":"dsh-wiserec-cli"}}]},
"scopeSpans":[{"scope":{"name":"dsh-wiserec-cli"},"spans":[{"traceId":"0123456789abcdef0123456789abcdef","spanId":"0123456789abcdef","name":"dsh.turn","kind":1,
"startTimeUnixNano":"1790000000123456789","endTimeUnixNano":"1790000000123456790","status":{"code":2,"message":"span-private"},
"attributes":[{"key":"langfuse.observation.input","value":{"stringValue":"hello Authorization: Bearer abcsecret\ncsrftoken=sensitivecsrf sk-lf-sensitivekey"}},
{"key":"langfuse.observation.metadata.tool_exit_code","value":{"intValue":"-1"}},
{"key":"unknown","value":{"stringValue":"unlisted-private"}}],
"events":[{"name":"event-private"}]}]}]}]}`

type senderFunc func(context.Context, []byte) (int64, error)

func (f senderFunc) Send(ctx context.Context, payload []byte) (int64, error) { return f(ctx, payload) }

func testConfig() config.Config {
	return config.Config{
		Allowed:     []netip.Prefix{netip.MustParsePrefix("127.0.0.0/8")},
		IngestToken: "ingest-fixture", MaxBody: 4096, MaxExpanded: 8192, Rate: 100, Burst: 40,
	}
}

func request(method, path, payload, encoding, token, remote string) *http.Request {
	r := httptest.NewRequest(method, path, strings.NewReader(payload))
	r.RemoteAddr = remote
	r.Header.Set("Content-Type", "application/json")
	r.Header.Set("Content-Encoding", encoding)
	r.Header.Set("X-Ingest-Token", token)
	r.Header.Set("X-Forwarded-For", "127.0.0.1")
	return r
}

func gzipBody(t *testing.T, payload string) string {
	t.Helper()
	var packed bytes.Buffer
	writer := gzip.NewWriter(&packed)
	if _, err := writer.Write([]byte(payload)); err != nil {
		t.Fatal(err)
	}
	if err := writer.Close(); err != nil {
		t.Fatal(err)
	}
	return packed.String()
}

func TestWritesOnlyAllowedRoutesAndPayloadFields(t *testing.T) {
	var logs bytes.Buffer
	sends := 0
	handler := New(testConfig(), senderFunc(func(_ context.Context, payload []byte) (int64, error) {
		sends++
		if !json.Valid(payload) {
			t.Fatalf("invalid forwarded JSON: %s", payload)
		}
		for _, needle := range []string{"abcsecret", "sensitivecsrf", "sensitivekey", "private", "Authorization: Bearer"} {
			if bytes.Contains(payload, []byte(needle)) {
				t.Fatalf("forwarded %q", needle)
			}
		}
		for _, needle := range []string{`"scope":{"name":"dsh-wiserec-cli"}`, `"startTimeUnixNano":"1790000000123456789"`,
			`"status":{"code":2}`, `"intValue":"-1"`, `csrf`, `[REDACTED]`} {
			if !bytes.Contains(payload, []byte(needle)) {
				t.Fatalf("missing %q in %s", needle, payload)
			}
		}
		return 0, nil
	}), log.New(&logs, "", 0), "test")

	for _, tc := range []struct {
		method, path, body, encoding, token, remote string
		want                                        int
	}{
		{"GET", "/health", "", "", "", "", 200},
		{"GET", "/v1/traces", "", "", "", "", 404},
		{"POST", "/api/public/traces", "", "", "", "", 404},
		{"POST", "/v1/%74races", "", "", "", "", 404},
		{"POST", "/v1/traces", trace, "", "bad", "127.0.0.1:1234", 401},
		{"POST", "/v1/traces", trace, "", "ingest-fixture", "192.0.2.1:1234", 403},
		{"POST", "/v1/traces", trace, "br", "ingest-fixture", "127.0.0.1:1234", 415},
		{"POST", "/v1/traces", `{"resourceSpans":[]}`, "", "ingest-fixture", "127.0.0.1:1234", 200},
		{"POST", "/v1/traces", `{"resourceSpans":null}`, "", "ingest-fixture", "127.0.0.1:1234", 400},
		{"POST", "/v1/traces", trace + "{}", "", "ingest-fixture", "127.0.0.1:1234", 400},
		{"POST", "/v1/traces", trace, "", "ingest-fixture", "[::ffff:127.0.0.1]:1234", 200},
		{"POST", "/v1/traces", gzipBody(t, trace), "gzip", "ingest-fixture", "127.0.0.1:1234", 200},
	} {
		w := httptest.NewRecorder()
		handler.ServeHTTP(w, request(tc.method, tc.path, tc.body, tc.encoding, tc.token, tc.remote))
		if w.Code != tc.want {
			t.Errorf("%s %s: got %d want %d (%s)", tc.method, tc.path, w.Code, tc.want, w.Body)
		}
	}
	if sends != 2 || !strings.Contains(logs.String(), "client_ip=127.0.0.1") ||
		strings.Contains(logs.String(), "sensitive") || strings.Contains(logs.String(), "ingest-fixture") {
		t.Fatalf("sends=%d unexpected access log=%s", sends, logs.String())
	}
}

func TestLimitsCompressedAndExpandedBodies(t *testing.T) {
	cfg := testConfig()
	cfg.MaxBody, cfg.MaxExpanded = 128, 256
	handler := New(cfg, nil, nil, "test")
	for _, tc := range []struct {
		payload, encoding string
		want              int
	}{
		{strings.Repeat(" ", 129), "", 413},
		{gzipBody(t, strings.Repeat(" ", 257)), "gzip", 413},
		{gzipBody(t, strings.Repeat(" ", 257))[:12], "gzip", 400},
	} {
		w := httptest.NewRecorder()
		r := request("POST", "/v1/traces", tc.payload, tc.encoding, "ingest-fixture", "127.0.0.1:4321")
		r.ContentLength = -1
		handler.ServeHTTP(w, r)
		if w.Code != tc.want {
			t.Errorf("encoding %q: got %d want %d", tc.encoding, w.Code, tc.want)
		}
	}
}

func TestPartialUpstreamFailureAndRateLimit(t *testing.T) {
	cfg := testConfig()
	cfg.Rate, cfg.Burst = 1, 2
	sent := 0
	h := New(cfg, senderFunc(func(_ context.Context, _ []byte) (int64, error) {
		sent++
		if sent == 1 {
			return 1, nil
		}
		return 0, errors.New("upstream private")
	}), nil, "test")
	for i, expected := range []int{200, 502, 429} {
		w := httptest.NewRecorder()
		h.ServeHTTP(w, request("POST", "/v1/traces", trace, "", "ingest-fixture", "127.0.0.1:4321"))
		if w.Code != expected || (i == 0 && !strings.Contains(w.Body.String(), `"rejectedSpans":1`)) ||
			strings.Contains(w.Body.String(), "private") {
			t.Errorf("got %d %s, want %d", w.Code, w.Body, expected)
		}
	}
}
