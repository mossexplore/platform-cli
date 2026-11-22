package forwarder

import (
	"context"
	"io"
	"net/http"
	"net/url"
	"strings"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
)

type roundTripFunc func(*http.Request) (*http.Response, error)

func (f roundTripFunc) RoundTrip(req *http.Request) (*http.Response, error) { return f(req) }

func TestForwardsFixedProtocolAndStripsUpstreamDetails(t *testing.T) {
	upstream, _ := url.Parse("http://127.0.0.1:3000/api/public/otel/v1/traces")
	sender := New(config.Config{LangfuseURL: upstream, PublicKey: "fixture-pk", SecretKey: "fixture-sk", UpstreamTimeout: time.Second})
	for _, tc := range []struct {
		status   int
		body     string
		rejected int64
		fail     bool
	}{
		{200, "{}", 0, false},
		{200, "", 0, false},
		{200, `{"partialSuccess":{"rejectedSpans":"2","errorMessage":"do not expose"}}`, 2, false},
		{200, `{"partialSuccess":{"rejectedSpans":-1}}`, 0, true},
		{200, strings.Repeat(" ", 65537), 0, true},
		{401, "secret from upstream", 0, true},
		{307, "", 0, true},
	} {
		hits := 0
		sender.client.Transport = roundTripFunc(func(req *http.Request) (*http.Response, error) {
			hits++
			user, password, ok := req.BasicAuth()
			body, err := io.ReadAll(req.Body)
			req.Body.Close()
			if req.URL.String() != upstream.String() || req.Method != "POST" || !ok ||
				user != "fixture-pk" || password != "fixture-sk" || req.Header.Get("x-langfuse-ingestion-version") != "4" ||
				req.Header.Get("Content-Type") != "application/json" || string(body) != "{}" || err != nil {
				t.Fatal("unexpected upstream request")
			}
			return &http.Response{StatusCode: tc.status, Header: http.Header{"Location": {"http://127.0.0.1:9"}},
				Body: io.NopCloser(strings.NewReader(tc.body))}, nil
		})
		rejected, err := sender.Send(context.Background(), []byte("{}"))
		if hits != 1 || rejected != tc.rejected || (err != nil) != tc.fail ||
			(err != nil && strings.Contains(err.Error(), "secret from upstream")) {
			t.Errorf("status %d, hits %d, rejects %d, error %v", tc.status, hits, rejected, err)
		}
	}
}
