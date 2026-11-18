package localstate

import (
	"os"
	"path/filepath"
	"testing"
)

func TestPackageConfigSeedsMissingUserConfigOnly(t *testing.T) {
	root := t.TempDir()
	paths := Paths{Dir: filepath.Join(root, "state"), configTemplate: filepath.Join(root, "config.template.json")}
	seed := []byte(`{"current":"dev","profiles":[{"name":"dev","api_endpoint":"https://example.test"},{"name":"test","api_endpoint":"https://test.example.test"}]}`)
	if err := os.WriteFile(paths.configTemplate, seed, 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := LoadConfig(paths); err == nil {
		t.Fatal("read-only config load seeded state")
	}
	if cfg, err := paths.LoadOrInitializeConfig(); err != nil || cfg.Current != "dev" {
		t.Fatalf("first load: %+v, %v", cfg, err)
	}
	if _, err := paths.UseEnvironment("test"); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(paths.configTemplate, []byte("broken replacement"), 0600); err != nil {
		t.Fatal(err)
	}
	if cfg, err := paths.LoadOrInitializeConfig(); err != nil || cfg.Current != "test" {
		t.Fatalf("existing config replaced: %+v, %v", cfg, err)
	}
	paths.Dir = filepath.Join(root, "other")
	if _, err := paths.LoadOrInitializeConfig(); err == nil {
		t.Fatal("invalid template accepted")
	}
	if _, err := os.Stat(paths.Config()); !os.IsNotExist(err) {
		t.Fatalf("invalid template was persisted: %v", err)
	}
}
