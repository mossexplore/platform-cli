package keepalive

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

const testInterval = time.Minute

type keepaliveFixture struct {
	base    localstate.Paths
	a       localstate.Paths
	b       localstate.Paths
	profile localstate.Profile
	worker  worker
	catalog []localstate.Department
}

func newKeepaliveFixture(t *testing.T, endpoint, globalTenant string) keepaliveFixture {
	t.Helper()
	config, err := json.Marshal(map[string]any{
		"current": "uat",
		"profiles": []map[string]string{
			{"name": "dev", "api_endpoint": endpoint},
			{"name": "uat", "api_endpoint": endpoint},
		},
		"auth": map[string]int{"ping_interval_minutes": 1},
	})
	if err != nil {
		t.Fatal(err)
	}
	base, err := localstate.NewPaths(t.TempDir(), config)
	if err != nil {
		t.Fatal(err)
	}
	cfg, err := base.LoadOrInitializeConfig()
	if err != nil {
		t.Fatal(err)
	}
	cfg.Current = "dev"
	profile := cfg.Profile()
	catalog := []localstate.Department{{ID: "dept", Tenants: []localstate.Tenant{
		{ID: "tenant-a"}, {ID: "tenant-b"}, {ID: "global-tenant"},
	}}}
	fixture := keepaliveFixture{
		base:    base,
		a:       base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "a"}),
		b:       base.WithSession(localstate.SessionScope{Mode: localstate.SessionModeDSH, ID: "b"}),
		profile: profile, catalog: catalog,
		worker: worker{paths: base, name: profile.Name, token: "fixture-worker", version: "1.0.0"},
	}
	fixture.saveLogin(t, "fixture=original", globalTenant)
	fixture.bind(t, fixture.a, "tenant-a")
	fixture.bind(t, fixture.b, "tenant-b")
	now := time.Now()
	if err := update(base, func(entries map[string]Entry) error {
		entries[profile.Name] = Entry{
			Owner:    []owner{currentOwner(fixture.a.Session, now), currentOwner(fixture.b.Session, now)},
			Endpoint: profile.Origin(), Username: "fixture-user", WorkerToken: fixture.worker.token,
			WorkerPID: os.Getpid(), WorkerIdentity: identity(os.Getpid()),
			Version: fixture.worker.version, Protocol: workerProtocol, Status: "running",
		}
		return nil
	}); err != nil {
		t.Fatal(err)
	}
	return fixture
}

func (f keepaliveFixture) saveLogin(t *testing.T, cookie, globalTenant string) {
	t.Helper()
	expiry, err := json.Marshal(time.Now().Add(15 * time.Minute))
	if err != nil {
		t.Fatal(err)
	}
	_, err = f.base.SaveLogin(localstate.Credentials{
		Origin: f.profile.Origin(), Profile: f.profile.Name, Username: "fixture-user",
		Cookie: cookie, CSRFToken: "fixture-csrf", ExpiresAt: expiry,
	}, f.catalog, globalTenant)
	if err != nil {
		t.Fatal(err)
	}
}

func (f keepaliveFixture) bind(t *testing.T, paths localstate.Paths, tenant string) {
	t.Helper()
	if _, err := paths.UseEnvironment(f.profile.Name); err != nil {
		t.Fatal(err)
	}
	creds, err := paths.CredentialsFor(f.profile)
	if err != nil {
		t.Fatal(err)
	}
	if _, err := paths.SelectBusiness(f.profile, creds, "", tenant, ""); err != nil {
		t.Fatal(err)
	}
}

func (f *keepaliveFixture) poll(t *testing.T, wantStop bool) Entry {
	t.Helper()
	if stop, err := f.worker.poll(context.Background()); err != nil || stop != wantStop {
		t.Fatalf("poll stop = %v, err = %v, want stop = %v", stop, err, wantStop)
	}
	entry, _, err := View(f.base, f.profile.Name, testInterval)
	if err != nil {
		t.Fatal(err)
	}
	return entry
}

func acceptProbe(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{Name: "fixture", Value: "renewed"})
	_, _ = io.WriteString(w, `{"result":{"code":0,"data":[]}}`)
}

func TestWorkerUsesSessionBusinessAndKeepsOtherSessions(t *testing.T) {
	for _, globalTenant := range []string{"", "global-tenant"} {
		t.Run("global="+globalTenant, func(t *testing.T) {
			requests := make(chan [3]string, 4)
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				var body map[string]string
				if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
					t.Error(err)
				}
				requests <- [3]string{r.Header.Get("businessid"), r.Header.Get("ai-businessId"), body["businessId"]}
				acceptProbe(w)
			}))
			defer server.Close()
			f := newKeepaliveFixture(t, server.URL, globalTenant)
			verify := func(tenant string, successes, sessions int) {
				t.Helper()
				entry := f.poll(t, false)
				if entry.Success != successes || entry.Status != "running" || SessionCount(entry) != sessions {
					t.Fatalf("unexpected registry entry: %+v", entry)
				}
				select {
				case request := <-requests:
					if request != [3]string{tenant, tenant, tenant} {
						t.Fatalf("probe business = %q, want %s", request, tenant)
					}
				default:
					t.Fatal("no probe request")
				}
			}
			verify("tenant-a", 1, 2)
			if _, err := f.a.UseEnvironment("uat"); err != nil {
				t.Fatal(err)
			}
			if err := Detach(f.a, f.profile.Name); err != nil {
				t.Fatal(err)
			}
			if err := f.worker.update(func(entry *Entry) error {
				entry.LastActivity = time.Time{}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			verify("tenant-b", 2, 1)
			creds, err := f.base.CredentialsFor(f.profile)
			if err != nil || creds.Cookie != "fixture=renewed" {
				t.Fatalf("renewed credential missing: %v", err)
			}
			if err := f.worker.update(func(entry *Entry) error {
				entry.Owner[0].Seen = time.Now().Add(-3 * testInterval)
				entry.LastActivity = time.Time{}
				return nil
			}); err != nil {
				t.Fatal(err)
			}
			entry := f.poll(t, true)
			if entry.Status != "stopped" || SessionCount(entry) != 0 || len(requests) != 0 {
				t.Fatalf("expired session kept the worker active: %+v", entry)
			}
		})
	}
}

func TestWorkerDiscardsSupersededProbeResponse(t *testing.T) {
	tests := []struct {
		name   string
		change func(*testing.T, keepaliveFixture)
		cookie string
	}{
		{"switch business", func(t *testing.T, f keepaliveFixture) { f.bind(t, f.a, "tenant-b") }, "fixture=original"},
		{"switch environment", func(t *testing.T, f keepaliveFixture) {
			if _, err := f.a.UseEnvironment("uat"); err != nil {
				t.Fatal(err)
			}
		}, "fixture=original"},
		{"switch away and back", func(t *testing.T, f keepaliveFixture) {
			if _, err := f.a.UseEnvironment("uat"); err != nil {
				t.Fatal(err)
			}
			f.bind(t, f.a, "tenant-a")
		}, "fixture=original"},
		{"replace login", func(t *testing.T, f keepaliveFixture) { f.saveLogin(t, "fixture=new-login", "") }, "fixture=new-login"},
		{"manual stop", func(t *testing.T, f keepaliveFixture) {
			if err := Stop(f.base, f.profile.Name, false); err != nil {
				t.Fatal(err)
			}
		}, "fixture=original"},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			seen := make(chan struct{}, 1)
			var f keepaliveFixture
			server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				defer func() { seen <- struct{}{} }()
				tt.change(t, f)
				acceptProbe(w)
			}))
			defer server.Close()
			f = newKeepaliveFixture(t, server.URL, "global-tenant")
			entry := f.poll(t, false)
			if len(seen) != 1 {
				t.Fatal("probe did not exercise the response path")
			}
			if entry.Success != 0 || !entry.LastConfirmed.IsZero() {
				t.Fatalf("obsolete response counted as a success: %+v", entry)
			}
			creds, err := f.base.CredentialsFor(f.profile)
			if err != nil || creds.Cookie != tt.cookie {
				t.Fatalf("obsolete response replaced the credential: %v", err)
			}
		})
	}
}
