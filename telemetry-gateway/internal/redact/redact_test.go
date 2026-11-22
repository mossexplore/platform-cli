package redact

import "testing"

func TestRedactionIsIdempotentAfterClientMasking(t *testing.T) {
	input := "sample csrftoken=[REDACTED] and api_key=[REDACTED]"
	if result := Text(input); result != input {
		t.Errorf("already redacted value changed: %q", result)
	}
	raw := "Bearer temporary-value\npk-lf-private\n-----BEGIN PRIVATE KEY-----\nsecret\n-----END PRIVATE KEY-----"
	want := "[REDACTED]\n[REDACTED]\n[REDACTED]"
	if result := Text(raw); result != want || Text(result) != want {
		t.Errorf("incorrect redaction: %q", result)
	}
}
