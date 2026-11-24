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

func TestBrowserBusinessSelectionMustBeUnique(t *testing.T) {
	catalog := []Department{{ID: "department", Tenants: []Tenant{
		{ID: "tenant-a", Teams: []Team{{ID: "team", Key: "tenant-b", Status: "available", BusinessID: "another-business"}}},
		{ID: "tenant-b"},
	}}}
	if selected := selectionFromBrowser(catalog, "tenant-b", false); selected != (Selection{}) {
		t.Fatalf("accepted ambiguous browser selection: %+v", selected)
	}
}
