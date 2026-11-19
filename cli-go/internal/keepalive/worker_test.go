package keepalive

import (
	"slices"
	"testing"
)

func TestWorkerEnvironmentStripsSessionVars(t *testing.T) {
	input := []string{
		"PATH=/usr/bin",
		"DSH_SHELL=1",
		"DSH_SESSION_ID=sess-1",
		"dsh_session_id=sess-win",
		"ML_SESSION_ID=override-1",
		"ml_session_id=override-win",
		"KEEP_ME=ok",
	}
	got := workerEnvironment(input)
	want := []string{"PATH=/usr/bin", "KEEP_ME=ok"}
	if !slices.Equal(got, want) {
		t.Fatalf("workerEnvironment = %v, want %v", got, want)
	}
}
