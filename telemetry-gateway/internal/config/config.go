package config

import (
	"errors"
	"fmt"
	"net/netip"
	"net/url"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	Listen               string
	LangfuseURL          *url.URL
	PublicKey, SecretKey string
	IngestToken          string
	Allowed              []netip.Prefix
	MaxBody, MaxExpanded int64
	UpstreamTimeout      time.Duration
	Rate, Burst          int
}

func Load(get func(string) string) (Config, error) {
	cfg := Config{
		Listen: get("GATEWAY_LISTEN_ADDR"), IngestToken: get("GATEWAY_INGEST_TOKEN"),
		PublicKey: get("LANGFUSE_PUBLIC_KEY"), SecretKey: get("LANGFUSE_SECRET_KEY"),
	}
	if cfg.Listen == "" {
		cfg.Listen = ":8088"
	}
	base, err := url.Parse(get("LANGFUSE_BASE_URL"))
	if err != nil || (base.Scheme != "http" && base.Scheme != "https") ||
		base.Hostname() == "" || base.User != nil || base.RawQuery != "" || base.ForceQuery ||
		base.Fragment != "" || base.Opaque != "" || (base.Path != "" && base.Path != "/") {
		return Config{}, errors.New("LANGFUSE_BASE_URL must be an HTTP(S) origin")
	}
	base.Path = "/api/public/otel/v1/traces"
	cfg.LangfuseURL = base
	if !validSecret(cfg.PublicKey) || strings.Contains(cfg.PublicKey, ":") || !validSecret(cfg.SecretKey) {
		return Config{}, errors.New("valid LANGFUSE_PUBLIC_KEY and LANGFUSE_SECRET_KEY are required")
	}
	if v := get("LANGFUSE_INGESTION_VERSION"); v != "" && v != "4" {
		return Config{}, errors.New("LANGFUSE_INGESTION_VERSION must be 4")
	}
	if cfg.IngestToken != "" && !validSecret(cfg.IngestToken) {
		return Config{}, errors.New("invalid GATEWAY_INGEST_TOKEN")
	}
	networks := get("GATEWAY_ALLOWED_CIDRS")
	if networks == "" {
		networks = "127.0.0.0/8,::1/128"
	}
	for raw := range strings.SplitSeq(networks, ",") {
		prefix, err := netip.ParsePrefix(strings.TrimSpace(raw))
		if err != nil {
			return Config{}, errors.New("invalid GATEWAY_ALLOWED_CIDRS")
		}
		cfg.Allowed = append(cfg.Allowed, prefix.Masked())
	}

	values := []struct {
		name     string
		def, max int
	}{
		{"GATEWAY_MAX_BODY_BYTES", 4 << 20, 4 << 20},
		{"GATEWAY_MAX_DECOMPRESSED_BYTES", 8 << 20, 8 << 20},
		{"GATEWAY_UPSTREAM_TIMEOUT_SECONDS", 10, 60},
		{"GATEWAY_RATE_LIMIT_RPS", 20, 1000},
		{"GATEWAY_RATE_LIMIT_BURST", 40, 2000},
	}
	loaded := make([]int, len(values))
	for i, parameter := range values {
		loaded[i] = parameter.def
		if raw := get(parameter.name); raw != "" {
			value, err := strconv.Atoi(raw)
			if err != nil || value < 1 || value > parameter.max {
				return Config{}, fmt.Errorf("%s must be between 1 and %d", parameter.name, parameter.max)
			}
			loaded[i] = value
		}
	}
	cfg.MaxBody, cfg.MaxExpanded = int64(loaded[0]), int64(loaded[1])
	cfg.UpstreamTimeout = time.Duration(loaded[2]) * time.Second
	cfg.Rate, cfg.Burst = loaded[3], loaded[4]
	return cfg, nil
}

func validSecret(value string) bool {
	if len(value) == 0 || len(value) > 1024 {
		return false
	}
	for _, char := range value {
		if char < '!' || char > '~' {
			return false
		}
	}
	return true
}
