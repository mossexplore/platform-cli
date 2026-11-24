package localstate

import (
	"encoding/json"
	"os"
	"testing"
	"time"
)

func TestRefreshKeepsCurrentBusinessAndRejectsMismatchedState(t *testing.T) {
	paths := Paths{Dir: t.TempDir()}
	profile := Profile{Name: "preview", Endpoint: "https://preview.example.test"}
	expiry, err := json.Marshal(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	creds := Credentials{
		Origin: profile.Origin(), Profile: profile.Name, Username: "fixture-user",
		Cookie: "fixture=local", CSRFToken: "fixture-value", ExpiresAt: expiry,
	}
	catalog := []Department{{ID: "department", Tenants: []Tenant{
		{ID: "tenant-a"}, {ID: "tenant-b"},
	}}}
	if got, err := paths.SaveLogin(creds, catalog, "tenant-a", ""); err != nil || got != "tenant-a" {
		t.Fatalf("initial business: %q %v", got, err)
	}
	var file businessFile
	if err := readJSON(paths.Business(), &file); err != nil {
		t.Fatal(err)
	}
	entry := file.Profiles[profile.Name]
	entry.Origin = ""
	file.Profiles[profile.Name] = entry
	if err := writeState(paths.Business(), file); err != nil {
		t.Fatal(err)
	}
	oldFile, err := os.ReadFile(paths.Credentials())
	if err != nil {
		t.Fatal(err)
	}
	if got, err := paths.SaveBusinessRefresh(creds, catalog, "tenant-b"); err != nil || got != "tenant-a" {
		t.Fatalf("restored saved business: %q %v", got, err)
	}
	current, err := paths.LoadCredentials(profile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if got, err := paths.SelectedBusiness(current); err != nil || got != "tenant-a" {
		t.Fatalf("current business: %q %v", got, err)
	}
	if entry, err := paths.BusinessEntry(current); err != nil || entry.Origin != creds.Origin {
		t.Fatalf("saved business origin = %q, want %q, error %v", entry.Origin, creds.Origin, err)
	}
	if err := WritePrivate(paths.Credentials(), oldFile); err != nil {
		t.Fatal(err)
	}
	partial, err := paths.LoadCredentials(profile, time.Now())
	if err != nil {
		t.Fatal(err)
	}
	if got, err := paths.SelectedBusiness(partial); err == nil || got != "" {
		t.Fatalf("accepted a partially replaced login: %q %v", got, err)
	}
}

func TestLoginBusinessSelectionPriority(t *testing.T) {
	creds := Credentials{Profile: "preview", Origin: "https://example.test", Username: "fixture-user"}
	catalog := []Department{{ID: "department", Tenants: []Tenant{
		{ID: "tenant-a", Teams: []Team{{ID: "team-a", Key: "pps", Status: "available", BusinessID: "team-business"}}},
		{ID: "pps"},
	}}}
	for _, tc := range []struct{ savedID, browserID, scopeID, want string }{
		{"pps", "tenant-a", "tenant-a", "pps"},
		{"revoked", "tenant-a", "pps", "tenant-a"},
		{"revoked", "", "pps", "pps"},
		{"", "tenant-a", "pps", "tenant-a"},
		{"", "", "pps", "pps"},
		{"", " ", "pps", "pps"},
		{"", "team-a", "pps", "team-business"},
		{"", "unknown", "pps", ""},
		{"", "", "team-a", ""},
		{"", "", "", ""},
	} {
		paths := Paths{Dir: t.TempDir()}
		if tc.savedID != "" {
			previousCatalog := []Department{{ID: "department", Tenants: []Tenant{{ID: tc.savedID}}}}
			if got, err := paths.SaveLogin(creds, previousCatalog, tc.savedID, ""); err != nil || got != tc.savedID {
				t.Fatalf("seed business %q: got %q, error %v", tc.savedID, got, err)
			}
		}
		if got, err := paths.SaveLogin(creds, catalog, tc.browserID, tc.scopeID); err != nil || got != tc.want {
			t.Fatalf("browser business %q, scope %q: got %q, want %q, error %v", tc.browserID, tc.scopeID, got, tc.want, err)
		}
	}
}

func TestLoginRestoresSavedBusinessAfterLogout(t *testing.T) {
	profile := Profile{Name: "dev", Endpoint: "https://example.test"}
	expiry, err := json.Marshal(time.Now().Add(time.Hour))
	if err != nil {
		t.Fatal(err)
	}
	creds := Credentials{
		Origin: profile.Origin(), Profile: profile.Name, Username: "fixture-user",
		Cookie: "fixture=local", CSRFToken: "fixture-value", ExpiresAt: expiry,
	}
	for _, mode := range []SessionMode{SessionModeGlobal, SessionModeDSH} {
		t.Run(string(mode), func(t *testing.T) {
			for _, tc := range []struct {
				name, want string
				apply      func(*Credentials, *Department)
			}{
				{name: "same account and platform", want: "saved"},
				{name: "different account", want: "browser", apply: func(c *Credentials, _ *Department) { c.Username = "other-user" }},
				{name: "different platform", want: "browser", apply: func(c *Credentials, _ *Department) { c.Origin = "https://other.example.test" }},
				{name: "revoked tenant", want: "browser", apply: func(_ *Credentials, d *Department) { d.Tenants = d.Tenants[:1] }},
			} {
				t.Run(tc.name, func(t *testing.T) {
					paths := configTestPaths(t)
					if mode == SessionModeDSH {
						paths = paths.WithSession(SessionScope{Mode: mode, ID: "test-session"})
					}
					if _, err := paths.UseEnvironment(profile.Name); err != nil {
						t.Fatal(err)
					}
					catalog := []Department{{ID: "department", Tenants: []Tenant{{ID: "browser"}, {ID: "saved"}}}}
					if got, err := paths.SaveLogin(creds, catalog, "browser", ""); err != nil || got != "browser" {
						t.Fatalf("initial login: %q %v", got, err)
					}
					current, err := paths.LoadCredentials(profile, time.Now())
					if err != nil {
						t.Fatal(err)
					}
					if _, err := paths.SelectBusiness(profile, current, "department", "saved", ""); err != nil {
						t.Fatal(err)
					}
					if err := paths.Logout(profile, false, false); err != nil {
						t.Fatal(err)
					}
					if _, err := paths.LoadCredentials(profile, time.Now()); err == nil {
						t.Fatal("logout left credentials available")
					}
					next := creds
					if tc.apply != nil {
						tc.apply(&next, &catalog[0])
					}
					if got, err := paths.SaveLogin(next, catalog, "browser", ""); err != nil || got != tc.want {
						t.Fatalf("re-login business = %q, want %q, error %v", got, tc.want, err)
					}
				})
			}
		})
	}
}

func TestBrowserBusinessSelectionMustBeUnique(t *testing.T) {
	catalog := []Department{{ID: "department", Tenants: []Tenant{
		{ID: "tenant-a", Teams: []Team{{ID: "team", Key: "tenant-b", Status: "available", BusinessID: "another-business"}}},
		{ID: "tenant-b"},
	}}}
	if selected := selectionFromBrowser(catalog, "tenant-b", false); selected != (Selection{}) {
		t.Fatalf("accepted ambiguous browser selection: %+v", selected)
	}
}
