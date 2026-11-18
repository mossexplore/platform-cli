package localstate

import (
	"os"
	"testing"
)

const packageConfig = `{"current":"dev","profiles":[{"name":"dev","api_endpoint":"https://example.test"},{"name":"test","api_endpoint":"https://test.example.test"}],"access_control":{"url":"https://access.example.test","enable":true}}`

func TestLoadPackagedConfigMigratesOnlyCurrent(t *testing.T) {
	for _, test := range []struct {
		name, existing, current string
	}{
		{"missing", "", "dev"},
		{"legacy", `{"current":"test","profiles":[],"access_control":{"enable":false}}`, "test"},
		{"removed", `{"current":"retired","profiles":[{"name":"retired"}]}`, "dev"},
		{"corrupt", `{"current":`, "dev"},
		{"wrong type", `{"current":123}`, "dev"},
		{"duplicate", `{"current":"dev","current":"test"}`, "test"},
	} {
		t.Run(test.name, func(t *testing.T) {
			paths := configTestPaths(t)
			if test.existing != "" {
				if err := os.WriteFile(paths.Config(), []byte(test.existing), 0600); err != nil {
					t.Fatal(err)
				}
			}
			cfg, err := LoadConfig(paths)
			if err != nil || cfg.Current != test.current || len(cfg.Profiles) != 2 || !cfg.Access.Active() ||
				cfg.Access.URL != "https://access.example.test" {
				t.Fatalf("unexpected config: %+v, %v", cfg, err)
			}
			if test.existing == "" {
				if _, err := os.Stat(paths.Config()); !os.IsNotExist(err) {
					t.Fatalf("read-only load changed the selection: %v", err)
				}
			}
			if _, err := paths.LoadOrInitializeConfig(); err != nil {
				t.Fatal(err)
			}
			assertSelection(t, paths, test.current)
		})
	}
}

func TestUseEnvironmentOnlyWritesPackagedSelection(t *testing.T) {
	paths := configTestPaths(t)
	if _, err := paths.UseEnvironment("test"); err != nil {
		t.Fatal(err)
	}
	assertSelection(t, paths, "test")
	if _, err := paths.UseEnvironment("missing"); err == nil {
		t.Fatal("unconfigured environment accepted")
	}
	assertSelection(t, paths, "test")
}

func configTestPaths(t *testing.T) Paths {
	t.Helper()
	paths, err := NewPaths(t.TempDir(), []byte(packageConfig))
	if err != nil {
		t.Fatal(err)
	}
	return paths
}

func assertSelection(t *testing.T, paths Paths, current string) {
	t.Helper()
	data, err := os.ReadFile(paths.Config())
	if err != nil || string(data) != `{"current":"`+current+`"}` {
		t.Fatalf("selection file: %s, %v", data, err)
	}
}
