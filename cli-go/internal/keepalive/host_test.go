package keepalive

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func hostPaths(f keepaliveFixture, id string) localstate.Paths {
	return f.base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: id})
}

func mustTick(t *testing.T, f keepaliveFixture, host, session, action, want string) TickResult {
	t.Helper()
	result, err := Tick(context.Background(), f.base, HostRequest{HostProtocol, action, host, session}, "1.1.1")
	if err != nil || result.Protocol != HostProtocol || result.State != want {
		t.Fatalf("tick = %+v, %v, want %s", result, err, want)
	}
	return result
}

func TestHostUsesExplicitSessionAndSharesTerminalThrottle(t *testing.T) {
	businesses := make(chan string, 4)
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		businesses <- r.Header.Get("businessid")
		acceptProbe(w)
	}))
	defer server.Close()
	f := newKeepaliveFixture(t, server.URL, "global-tenant")
	f.bind(t, hostPaths(f, "dsh-b"), "tenant-b")

	if result := mustTick(t, f, "host-a", "unknown-session", "tick", "unknown_session"); result.Environment != "" {
		t.Fatalf("unknown session returned an environment: %+v", result)
	}
	if result := mustTick(t, f, "host-a", "dsh-b", "tick", "confirmed"); result.Environment != "dev" || result.RequestID == "" {
		t.Fatalf("confirmed result missing the resolved environment or request ID: %+v", result)
	}
	if business := <-businesses; business != "tenant-b" {
		t.Fatalf("wanted selected Harness tenant, got %q", business)
	}
	mustTick(t, f, "host-b", "dsh-b", "tick", "not_due")
	if entry := f.poll(t, false); entry.Success != 1 {
		t.Fatalf("terminal repeated host probe: %+v", entry)
	}
}

func TestHostStopBeforeRegistrationAndDiscardInflightResult(t *testing.T) {
	started, release := make(chan struct{}), make(chan struct{})
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		close(started)
		<-release
		acceptProbe(w)
	}))
	defer server.Close()
	defer close(release)
	f := newKeepaliveFixture(t, server.URL, "global-tenant")
	paths := hostPaths(f, "dsh-a")
	f.bind(t, paths, "tenant-a")
	if err := update(f.base, func(entries map[string]Entry) error {
		delete(entries, f.profile.Name)
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	if err := Stop(f.base, f.profile.Name); err != nil {
		t.Fatal(err)
	}
	mustTick(t, f, "host-a", "dsh-a", "tick", "stopped")
	cfg, err := localstate.LoadConfig(paths)
	if err != nil {
		t.Fatal(err)
	}
	if message, err := ResumeHost(paths, cfg); err != nil || !strings.Contains(message, "等待") {
		t.Fatalf("resume: %q %v", message, err)
	}

	done := make(chan TickResult, 1)
	go func() {
		result, err := Tick(context.Background(), f.base, HostRequest{HostProtocol, "tick", "host-a", "dsh-a"}, "1.1.1")
		if err != nil {
			t.Error(err)
		}
		done <- result
	}()
	select {
	case <-started:
	case <-time.After(5 * time.Second):
		t.Fatal("host probe did not reach server")
	}
	mustTick(t, f, "host-b", "dsh-a", "tick", "in_flight")
	mustTick(t, f, "host-a", "dsh-a", "release", "released")
	mustTick(t, f, "host-b", "dsh-a", "tick", "in_flight")
	if err := Stop(f.base, f.profile.Name); err != nil {
		t.Fatal(err)
	}
	select {
	case release <- struct{}{}:
	case <-done:
		t.Fatal("probe finished before the handler was released")
	}
	if result := <-done; result.State != "superseded" {
		t.Fatalf("stopped probe result = %+v", result)
	}
	creds, err := f.base.CredentialsFor(f.profile)
	if err != nil || creds.Cookie != "fixture=original" {
		t.Fatalf("stopped probe changed credentials: %v", err)
	}
}

func TestHostDoesNotRetryPlatformRejectionForTheSameLogin(t *testing.T) {
	var requests atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if requests.Add(1) == 1 {
			w.WriteHeader(http.StatusUnauthorized)
		} else {
			acceptProbe(w)
		}
	}))
	defer server.Close()
	f := newKeepaliveFixture(t, server.URL, "global-tenant")
	paths := hostPaths(f, "dsh-a")
	f.bind(t, paths, "tenant-a")
	mustTick(t, f, "host-a", "dsh-a", "tick", "expired")
	mustTick(t, f, "host-a", "dsh-a", "tick", "expired")
	if requests.Load() != 1 {
		t.Fatal("authentication failure was retried")
	}
	f.saveLogin(t, "fixture=new-login", "global-tenant")
	f.bind(t, paths, "tenant-a")
	mustTick(t, f, "host-a", "dsh-a", "tick", "confirmed")
}
