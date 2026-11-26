package weknora

import (
	"strings"
	"testing"
)

func TestWildcardIdentityGrants(t *testing.T) {
	for _, tc := range []struct {
		name, selector string
		want           [4]bool
	}{
		{"empty", "", [4]bool{}},
		{"exact", "test:alice", [4]bool{true}},
		{"all users in test", "test:*", [4]bool{true, true}},
		{"alice in all environments", "*:alice", [4]bool{true, false, true}},
		{"all", "*:*", [4]bool{true, true, true, true}},
		{"case sensitive", "Test:alice,*:ALICE", [4]bool{}},
		{"union", "test:*,*:alice", [4]bool{true, true, true}},
	} {
		t.Run(tc.name, func(t *testing.T) {
			preview, err := ParseVisibility("public", "preview", tc.selector)
			if err != nil {
				t.Fatal(err)
			}
			var entries []string
			for _, selector := range strings.Split(tc.selector, ",") {
				if selector != "" {
					entries = append(entries, selector+":preview")
				}
			}
			files, err := ParseFileGrants(strings.Join(entries, ","))
			if err != nil {
				t.Fatal(err)
			}
			for i, subject := range [][2]string{{"test", "alice"}, {"test", "bob"}, {"prod", "alice"}, {"prod", "bob"}} {
				env, user := subject[0], subject[1]
				if preview.allows("preview", env, user) != tc.want[i] || files.allows("preview", env, user) != tc.want[i] {
					t.Errorf("%s:%s should match = %t", env, user, tc.want[i])
				}
				if !preview.allows("public", env, user) || preview.allows("other", env, user) || files.allows("other", env, user) {
					t.Errorf("unexpected library scope for %s:%s", env, user)
				}
			}
		})
	}
}

func TestRejectInvalidIdentityWildcards(t *testing.T) {
	for _, selector := range []string{"test*:alice", "test:ali*", "**:alice", "test:?", ":alice", "test:"} {
		if _, err := ParseVisibility("", "preview", selector); err == nil {
			t.Errorf("accepted invalid preview selector %q", selector)
		}
		if _, err := ParseFileGrants(selector + ":preview"); err == nil {
			t.Errorf("accepted invalid file grant selector %q", selector)
		}
	}
	if _, err := ParseFileGrants("*:*:*"); err == nil {
		t.Error("accepted wildcard library ID")
	}
}
