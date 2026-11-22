package forwarder

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"strconv"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
)

type Sender struct {
	client              *http.Client
	url, user, password string
}

func New(cfg config.Config) *Sender {
	transport := http.DefaultTransport.(*http.Transport).Clone()
	transport.Proxy = nil
	return &Sender{
		url: cfg.LangfuseURL.String(), user: cfg.PublicKey, password: cfg.SecretKey,
		client: &http.Client{
			Transport:     transport,
			Timeout:       cfg.UpstreamTimeout,
			CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
		},
	}
}

func (s *Sender) Send(ctx context.Context, payload []byte) (int64, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, s.url, bytes.NewReader(payload))
	if err != nil {
		return 0, errors.New("cannot construct upstream request")
	}
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("x-langfuse-ingestion-version", "4")
	request.SetBasicAuth(s.user, s.password)
	response, err := s.client.Do(request)
	if err != nil {
		return 0, errors.New("upstream unavailable")
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return 0, errors.New("upstream rejected the request")
	}
	const limit = 64 << 10
	data, err := io.ReadAll(io.LimitReader(response.Body, limit+1))
	if err != nil || len(data) > limit {
		return 0, errors.New("invalid upstream response")
	}
	// Some Langfuse versions acknowledge ingestion with an empty body.
	if len(bytes.TrimSpace(data)) == 0 {
		return 0, nil
	}

	var result struct {
		Partial struct {
			Rejected json.RawMessage `json:"rejectedSpans"`
		} `json:"partialSuccess"`
	}
	if err := json.Unmarshal(data, &result); err != nil {
		return 0, errors.New("invalid upstream response")
	}
	if len(result.Partial.Rejected) == 0 {
		return 0, nil
	}
	rejected := bytes.Trim(result.Partial.Rejected, `"`)
	count, err := strconv.ParseInt(string(rejected), 10, 64)
	if err != nil || count < 0 {
		return 0, errors.New("invalid upstream response")
	}
	return count, nil
}
