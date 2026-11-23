package config

import "testing"

func TestValidatesUpstreamAndLimits(t *testing.T) {
	values := map[string]string{
		"LANGFUSE_BASE_URL": "http://langfuse-web:3000", "LANGFUSE_PUBLIC_KEY": "public", "LANGFUSE_SECRET_KEY": "secret",
	}
	get := func(key string) string { return values[key] }
	cfg, err := Load(get)
	if err != nil || cfg.LangfuseURL.Path != "/api/public/otel/v1/traces" || cfg.MaxBody != 4<<20 ||
		cfg.MaxExpanded != 8<<20 || len(cfg.Allowed) != 2 || cfg.Listen != ":8088" {
		t.Fatalf("unexpected defaults: %v", err)
	}
	for _, tc := range [][2]string{
		{"LANGFUSE_BASE_URL", "http://user:pass@localhost"},
		{"LANGFUSE_BASE_URL", "http://localhost/prefix"},
		{"LANGFUSE_INGESTION_VERSION", "3"},
		{"GATEWAY_ALLOWED_CIDRS", "not-a-network"},
		{"GATEWAY_MAX_BODY_BYTES", "5000000"},
		{"GATEWAY_RATE_LIMIT_BURST", "-1"},
		{"GATEWAY_INGEST_TOKEN", "bad\nvalue"},
		{"GATEWAY_ALLOWED_ENVIRONMENTS", "sit,*"},
		{"GATEWAY_ALLOW_CONTENT_FOR_ENVIRONMENTS", "sit,,uat"},
	} {
		before, set := values[tc[0]]
		values[tc[0]] = tc[1]
		if _, err := Load(get); err == nil {
			t.Errorf("accepted invalid %s", tc[0])
		}
		if set {
			values[tc[0]] = before
		} else {
			delete(values, tc[0])
		}
	}
}

func TestEnvironmentLists(t *testing.T) {
	for _, tc := range []struct {
		value, env string
		want       bool
	}{
		{"*", "", true},
		{"", "prod", true},
		{"-", "sit", false},
		{" SIT , UAT ", "sit", true},
		{" SIT , UAT ", "", false},
		{" SIT , UAT ", "prod", false},
	} {
		set, err := ParseEnvironments(tc.value)
		if err != nil || set.Allows(tc.env) != tc.want {
			t.Fatalf("list %q, environment %q: %v, %v", tc.value, tc.env, set.Allows(tc.env), err)
		}
	}
}
