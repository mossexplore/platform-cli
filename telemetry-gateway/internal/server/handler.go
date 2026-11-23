package server

import (
	"compress/gzip"
	"context"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"io"
	"log"
	"mime"
	"net/http"
	"net/netip"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/redact"
)

type Sender interface {
	Send(context.Context, []byte) (int64, error)
}

type Handler struct {
	config.Config
	sender    Sender
	logger    *log.Logger
	version   string
	rate      limiter
	inFlight  chan struct{}
	tokenHash [32]byte
}

var beijing = time.FixedZone("Asia/Shanghai", 8*60*60)

func New(cfg config.Config, sender Sender, logger *log.Logger, version string) *Handler {
	return &Handler{
		Config: cfg, sender: sender, logger: logger, version: version,
		rate:      limiter{rate: float64(cfg.Rate), burst: float64(cfg.Burst), buckets: make(map[netip.Addr]bucket)},
		inFlight:  make(chan struct{}, 16),
		tokenHash: sha256.Sum256([]byte(cfg.IngestToken)),
	}
}

func reply(w http.ResponseWriter, status int, response any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(response)
}

func (h *Handler) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.Method == http.MethodGet && r.URL.EscapedPath() == "/health":
		reply(w, http.StatusOK, map[string]string{"status": "ok", "version": h.version})
	case r.Method == http.MethodPost && r.URL.EscapedPath() == "/v1/traces":
		now := time.Now()
		peer, _ := netip.ParseAddrPort(r.RemoteAddr)
		ip := peer.Addr().Unmap()
		status, message, size, counts, rejected := h.ingest(w, r, ip, now)
		rejected += int64(counts.Filtered)
		if h.logger != nil {
			h.logger.Printf("%s client_ip=%s bytes=%d spans=%d rejected_spans=%d status=%d duration_ms=%d filtered_spans=%d",
				now.In(beijing).Format(time.DateTime), ip, size, counts.Received, rejected, status, time.Since(now).Milliseconds(), counts.Filtered)
		}
		switch {
		case status == http.StatusOK && rejected > 0:
			reply(w, status, map[string]any{"partialSuccess": map[string]any{"rejectedSpans": rejected}})
		case status == http.StatusOK:
			reply(w, status, struct{}{})
		default:
			reply(w, status, map[string]any{"code": status, "message": message})
		}
	default:
		reply(w, http.StatusNotFound, map[string]string{"message": "not found"})
	}
}

func (h *Handler) ingest(w http.ResponseWriter, r *http.Request, ip netip.Addr, now time.Time) (status int, message string, size int, counts redact.Counts, rejected int64) {
	allowed := false
	for _, network := range h.Allowed {
		if network.Contains(ip) {
			allowed = true
			break
		}
	}
	if !allowed {
		return http.StatusForbidden, "source not allowed", 0, counts, 0
	}
	if !h.rate.allow(ip, now) {
		return http.StatusTooManyRequests, "rate limit exceeded", 0, counts, 0
	}
	actual := sha256.Sum256([]byte(r.Header.Get("X-Ingest-Token")))
	if h.IngestToken != "" && (subtle.ConstantTimeCompare(actual[:], h.tokenHash[:]) != 1 ||
		len(r.Header.Values("X-Ingest-Token")) != 1) {
		return http.StatusUnauthorized, "invalid ingest token", 0, counts, 0
	}
	media, _, err := mime.ParseMediaType(r.Header.Get("Content-Type"))
	if err != nil || media != "application/json" {
		return http.StatusUnsupportedMediaType, "expected application/json", 0, counts, 0
	}
	select {
	case h.inFlight <- struct{}{}:
		defer func() { <-h.inFlight }()
	default:
		return http.StatusServiceUnavailable, "gateway busy", 0, counts, 0
	}

	payload, status := h.readPayload(w, r)
	if status != http.StatusOK {
		return status, "invalid request body", 0, counts, 0
	}
	size = len(payload)
	clean, counts, err := redact.Traces(payload, h.AllowedEnvironments, h.ContentEnvironments)
	if err != nil {
		return http.StatusBadRequest, "invalid OTLP spans", size, counts, 0
	}
	count := counts.Received - counts.Filtered
	if count == 0 {
		return http.StatusOK, "", size, counts, 0
	}
	if int64(len(clean)) > h.MaxExpanded {
		return http.StatusRequestEntityTooLarge, "payload exceeds forwarding limit", size, counts, 0
	}
	rejected, err = h.sender.Send(r.Context(), clean)
	if err != nil || rejected > int64(count) {
		return http.StatusBadGateway, "ingestion upstream unavailable", size, counts, 0
	}
	return http.StatusOK, "", size, counts, rejected
}

func (h *Handler) readPayload(w http.ResponseWriter, r *http.Request) ([]byte, int) {
	if r.ContentLength > h.MaxBody {
		return nil, http.StatusRequestEntityTooLarge
	}
	body := http.MaxBytesReader(w, r.Body, h.MaxBody)
	defer body.Close()
	var input io.Reader = body
	switch strings.ToLower(strings.TrimSpace(r.Header.Get("Content-Encoding"))) {
	case "", "identity":
	case "gzip":
		expanded, err := gzip.NewReader(body)
		if err != nil {
			return nil, readError(err)
		}
		defer expanded.Close()
		input = expanded
	default:
		return nil, http.StatusUnsupportedMediaType
	}
	payload, err := io.ReadAll(io.LimitReader(input, h.MaxExpanded+1))
	if err != nil {
		return nil, readError(err)
	}
	if int64(len(payload)) > h.MaxExpanded {
		return nil, http.StatusRequestEntityTooLarge
	}
	return payload, http.StatusOK
}

func readError(err error) int {
	var limit *http.MaxBytesError
	if errors.As(err, &limit) {
		return http.StatusRequestEntityTooLarge
	}
	return http.StatusBadRequest
}
