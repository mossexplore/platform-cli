package localstate

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestDetectSessionScope(t *testing.T) {
	lookup := func(values map[string]string) func(string) (string, bool) {
		return func(key string) (string, bool) {
			v, ok := values[key]
			return v, ok
		}
	}

	t.Run("global default", func(t *testing.T) {
		scope := DetectSessionScope(lookup(map[string]string{}))
		if scope.EffectiveMode() != SessionModeGlobal || scope.Isolated() || scope.Err != nil || scope.Label() != "全局默认" {
			t.Fatalf("unexpected global scope: %+v", scope)
		}
	})

	t.Run("dsh session", func(t *testing.T) {
		scope := DetectSessionScope(lookup(map[string]string{"DSH_SHELL": "1", "DSH_SESSION_ID": "sess-alpha"}))
		if scope.Mode != SessionModeDSH || !scope.Isolated() || scope.ID != "sess-alpha" || scope.Err != nil {
			t.Fatalf("unexpected dsh scope: %+v", scope)
		}
	})

	t.Run("dsh shell missing session id fails closed", func(t *testing.T) {
		for _, values := range []map[string]string{
			{"DSH_SHELL": "1"},
			{"DSH_SHELL": "1", "DSH_SESSION_ID": ""},
			{"DSH_SHELL": "1", "DSH_SESSION_ID": "   "},
			{"DSH_SHELL": "1", "DSH_SESSION_ID": "bad\nid"},
		} {
			scope := DetectSessionScope(lookup(values))
			if scope.Mode != SessionModeInvalid || !errors.Is(scope.Err, ErrDSHSessionMissing) {
				t.Fatalf("expected ErrDSHSessionMissing for %v, got %+v", values, scope)
			}
		}
	})

	t.Run("ml session id overrides dsh", func(t *testing.T) {
		scope := DetectSessionScope(lookup(map[string]string{
			"ML_SESSION_ID":  "custom-1",
			"DSH_SHELL":      "1",
			"DSH_SESSION_ID": "dsh-1",
		}))
		if scope.Mode != SessionModeEnv || scope.ID != "custom-1" || scope.Err != nil {
			t.Fatalf("unexpected env scope: %+v", scope)
		}
	})

	t.Run("invalid ml session id fails closed", func(t *testing.T) {
		for _, raw := range []string{"", "  ", " lead", "a\x00b", strings.Repeat("x", maxSessionIDRunes+1)} {
			scope := DetectSessionScope(lookup(map[string]string{"ML_SESSION_ID": raw}))
			if scope.Mode != SessionModeInvalid || !errors.Is(scope.Err, ErrSessionInvalid) {
				t.Fatalf("expected ErrSessionInvalid for %q, got %+v", raw, scope)
			}
		}
	})
}

func TestSessionFileSanitizationAndUniqueness(t *testing.T) {
	base := configTestPaths(t)
	dshA := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "../escape:win\\path/id"})
	envA := base.WithSession(SessionScope{Mode: SessionModeEnv, ID: "../escape:win\\path/id"})
	dshB := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "other-session"})

	for _, p := range []Paths{dshA, envA, dshB} {
		file := p.SessionFile()
		if filepath.Dir(file) != base.SessionsDir() {
			t.Fatalf("session file escaped sessions dir: %s", file)
		}
		if !strings.HasSuffix(file, ".json") || len(filepath.Base(file)) != 32+len(".json") {
			t.Fatalf("unexpected hashed filename: %s", file)
		}
	}
	if dshA.SessionFile() == envA.SessionFile() || dshA.SessionFile() == dshB.SessionFile() {
		t.Fatalf("session files collided: %s %s %s", dshA.SessionFile(), envA.SessionFile(), dshB.SessionFile())
	}
}

func TestMultiSessionEnvironmentAndBusinessIsolation(t *testing.T) {
	globalPaths := configTestPaths(t)
	if _, err := globalPaths.LoadOrInitializeConfig(); err != nil {
		t.Fatal(err)
	}
	devProfile := Profile{Name: "dev", Endpoint: "https://example.test"}
	testProfile := Profile{Name: "test", Endpoint: "https://test.example.test"}
	expiry, _ := json.Marshal(time.Now().Add(time.Hour))
	catalog := []Department{{ID: "dept-1", Tenants: []Tenant{
		{ID: "tenant-global"},
		{ID: "tenant-a"},
		{ID: "tenant-b"},
	}}}
	devCreds := Credentials{
		Origin: devProfile.Origin(), Profile: "dev", Username: "alice",
		Cookie: "c=1", CSRFToken: "t1", ExpiresAt: expiry,
	}
	if _, err := globalPaths.SaveLogin(devCreds, catalog, "tenant-global"); err != nil {
		t.Fatal(err)
	}
	testCreds := Credentials{
		Origin: testProfile.Origin(), Profile: "test", Username: "alice",
		Cookie: "c=2", CSRFToken: "t2", ExpiresAt: expiry,
	}
	if _, err := globalPaths.SaveLogin(testCreds, catalog, "tenant-global"); err != nil {
		t.Fatal(err)
	}

	sessA := globalPaths.WithSession(SessionScope{Mode: SessionModeDSH, ID: "conv-a"})
	sessB := globalPaths.WithSession(SessionScope{Mode: SessionModeDSH, ID: "conv-b"})

	// Fresh sessions fail closed without inheriting global current/selected.
	cfgA, err := sessA.LoadOrInitializeConfig()
	if err != nil || cfgA.Current != "" {
		t.Fatalf("fresh session should be unbound: %+v, %v", cfgA, err)
	}
	if _, err := cfgA.RequireProfile(); !errors.Is(err, ErrSessionEnvUnbound) {
		t.Fatalf("expected ErrSessionEnvUnbound, got %v", err)
	}
	if env := sessA.CurrentEnvironment(); env != nil {
		t.Fatalf("expected nil CurrentEnvironment for unbound session, got %q", *env)
	}

	// Bind session A to dev and verify business is still fail-closed.
	if _, err := sessA.UseEnvironment("dev"); err != nil {
		t.Fatal(err)
	}
	liveDev, err := sessA.LoadCredentials(devProfile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sessA.SelectedBusiness(liveDev); !errors.Is(err, ErrSessionBusinessUnbound) {
		t.Fatalf("expected ErrSessionBusinessUnbound, got %v", err)
	}

	// Bind session A -> dev/tenant-a and session B -> dev/tenant-b.
	if _, err := sessA.SelectBusiness(devProfile, liveDev, "dept-1", "tenant-a", ""); err != nil {
		t.Fatal(err)
	}
	if _, err := sessB.UseEnvironment("dev"); err != nil {
		t.Fatal(err)
	}
	if _, err := sessB.SelectBusiness(devProfile, liveDev, "dept-1", "tenant-b", ""); err != nil {
		t.Fatal(err)
	}

	// Verify complete isolation across session A, session B, and global state.
	if got, err := sessA.SelectedBusiness(liveDev); err != nil || got != "tenant-a" {
		t.Fatalf("session A business: %q %v", got, err)
	}
	if got, err := sessB.SelectedBusiness(liveDev); err != nil || got != "tenant-b" {
		t.Fatalf("session B business: %q %v", got, err)
	}
	if got, err := globalPaths.SelectedBusiness(liveDev); err != nil || got != "tenant-global" {
		t.Fatalf("global business polluted: %q %v", got, err)
	}

	// Switch session A to test and back to dev; dev selection should be remembered,
	// while global config.json remains untouched ("dev").
	if _, err := sessA.UseEnvironment("test"); err != nil {
		t.Fatal(err)
	}
	assertSelection(t, globalPaths, "dev")
	if env := sessA.CurrentEnvironment(); env == nil || *env != "test" {
		t.Fatalf("session A current env: %v", env)
	}
	if _, err := sessA.UseEnvironment("dev"); err != nil {
		t.Fatal(err)
	}
	if got, err := sessA.SelectedBusiness(liveDev); err != nil || got != "tenant-a" {
		t.Fatalf("session A dev business lost after env roundtrip: %q %v", got, err)
	}
}

func TestSessionSaveLoginPolicy(t *testing.T) {
	globalPaths := configTestPaths(t)
	devProfile := Profile{Name: "dev", Endpoint: "https://example.test"}
	expiry, _ := json.Marshal(time.Now().Add(time.Hour))
	catalog := []Department{{ID: "dept-1", Tenants: []Tenant{
		{ID: "tenant-a"}, {ID: "tenant-b"}, {ID: "tenant-c"},
	}}}
	aliceCreds := Credentials{
		Origin: devProfile.Origin(), Profile: "dev", Username: "alice",
		Cookie: "c=1", CSRFToken: "t1", ExpiresAt: expiry,
	}

	sessA := globalPaths.WithSession(SessionScope{Mode: SessionModeDSH, ID: "conv-a"})
	sessB := globalPaths.WithSession(SessionScope{Mode: SessionModeDSH, ID: "conv-b"})
	if _, err := sessA.UseEnvironment("dev"); err != nil {
		t.Fatal(err)
	}
	if _, err := sessB.UseEnvironment("dev"); err != nil {
		t.Fatal(err)
	}

	// Unbound session A logs in with unique browser business -> binds tenant-a.
	got, err := sessA.SaveLogin(aliceCreds, catalog, "tenant-a")
	if err != nil || got != "tenant-a" {
		t.Fatalf("initial session login: %q %v", got, err)
	}
	liveCreds, err := sessA.LoadCredentials(devProfile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sessB.SelectBusiness(devProfile, liveCreds, "dept-1", "tenant-b", ""); err != nil {
		t.Fatal(err)
	}

	// Session A re-logs in as same user with different browser business -> keeps tenant-a;
	// Session B's tenant-b also remains valid seamlessly after shared StateID renewal.
	got, err = sessA.SaveLogin(aliceCreds, catalog, "tenant-c")
	if err != nil || got != "tenant-a" {
		t.Fatalf("re-login should keep existing session selection: %q %v", got, err)
	}
	renewedCreds, err := sessB.LoadCredentials(devProfile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if gotB, err := sessB.SelectedBusiness(renewedCreds); err != nil || gotB != "tenant-b" {
		t.Fatalf("session B should stay valid across same-user renewal: %q %v", gotB, err)
	}

	// Different user logs in on session A -> session B's old binding must fail closed.
	bobCreds := aliceCreds
	bobCreds.Username = "bob"
	if got, err := sessA.SaveLogin(bobCreds, catalog, "tenant-c"); err != nil || got != "tenant-c" {
		t.Fatalf("different user login should bind new browser business: %q %v", got, err)
	}
	bobLive, err := sessB.LoadCredentials(devProfile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sessB.SelectedBusiness(bobLive); !errors.Is(err, ErrSessionBusinessInvalid) {
		t.Fatalf("expected ErrSessionBusinessInvalid after user change, got %v", err)
	}

	// Same user login where previous tenant was revoked and browser has no unique selection -> cleared.
	shrunkCatalog := []Department{{ID: "dept-1", Tenants: []Tenant{{ID: "tenant-a"}}}}
	if got, err := sessA.SaveLogin(bobCreds, shrunkCatalog, ""); err != nil || got != "" {
		t.Fatalf("revoked business with empty browser business should clear: %q %v", got, err)
	}
	shrunkLive, err := sessA.LoadCredentials(devProfile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if _, err := sessA.SelectedBusiness(shrunkLive); !errors.Is(err, ErrSessionBusinessUnbound) {
		t.Fatalf("expected ErrSessionBusinessUnbound after clearing revoked selection, got %v", err)
	}
}

func TestSessionDamagedFileFailClosedAndRecovery(t *testing.T) {
	base := configTestPaths(t)
	sess := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "conv-damaged"})
	if err := WritePrivate(sess.SessionFile(), []byte("{broken-json")); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadConfig(sess); err == nil {
		t.Fatal("damaged session file should fail closed on LoadConfig")
	}
	if _, err := sess.UseEnvironment("test"); err != nil {
		t.Fatalf("UseEnvironment should recover damaged session file: %v", err)
	}
	cfg, err := LoadConfig(sess)
	if err != nil || cfg.Current != "test" {
		t.Fatalf("recovered session config: %+v, %v", cfg, err)
	}
}

func TestSessionTTLCleanup(t *testing.T) {
	base := configTestPaths(t)
	oldSess := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "old-session"})
	recentSess := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "recent-session"})
	activeSess := base.WithSession(SessionScope{Mode: SessionModeDSH, ID: "active-session"})

	now := time.Now().UTC()
	oldData, _ := json.Marshal(SessionState{
		Version: sessionStateVersion, Source: "dsh", SessionID: "old-session",
		Current: "dev", UpdatedAt: now.Add(-8 * 24 * time.Hour),
	})
	recentData, _ := json.Marshal(SessionState{
		Version: sessionStateVersion, Source: "dsh", SessionID: "recent-session",
		Current: "dev", UpdatedAt: now.Add(-2 * 24 * time.Hour),
	})
	if err := WritePrivate(oldSess.SessionFile(), oldData); err != nil {
		t.Fatal(err)
	}
	if err := WritePrivate(recentSess.SessionFile(), recentData); err != nil {
		t.Fatal(err)
	}

	if _, err := activeSess.UseEnvironment("test"); err != nil {
		t.Fatal(err)
	}
	if _, err := os.Stat(oldSess.SessionFile()); !os.IsNotExist(err) {
		t.Fatalf("expired session file was not cleaned up: %v", err)
	}
	if _, err := os.Stat(recentSess.SessionFile()); err != nil {
		t.Fatalf("recent session file should remain: %v", err)
	}
	if _, err := os.Stat(activeSess.SessionFile()); err != nil {
		t.Fatalf("active session file should remain: %v", err)
	}
}
