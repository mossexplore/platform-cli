package main

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"golang.org/x/sys/windows/registry"
)

func TestRemoveOnlyRecognizedLegacyLaunchers(t *testing.T) {
	root := t.TempDir()
	t.Setenv("LOCALAPPDATA", root)
	defaultBin := filepath.Join(root, "Programs", "WiseRecCLI", "bin")
	customBin := filepath.Join(root, "Custom WiseRec", "bin")
	newBin := filepath.Join(root, "Programs", "WiseRecCLIGo")
	otherBin := filepath.Join(root, "Other tools", "bin")
	createTestLauncher(t, defaultBin, "ml.cmd", "@echo off")
	createTestLauncher(t, customBin, "ml.cmd", "@echo off\r\n"+`"%~dp0..\venv\Scripts\ml.exe" %*`+"\r\n")
	createTestLauncher(t, newBin, "ml.exe", "")
	createTestLauncher(t, otherBin, "other.cmd", "")
	keep := `"%LOCALAPPDATA%\Other tools\bin"`
	value := pathValue{
		Text: strings.Join([]string{keep, `%LOCALAPPDATA%\Programs\WiseRecCLI\bin`, "", customBin + `\`, newBin}, ";"),
		Kind: registry.EXPAND_SZ,
	}

	updated, removed, err := value.removeLegacyLaunchers(newBin)
	if err != nil || updated.Text != keep+";;"+newBin || updated.Kind != value.Kind ||
		len(removed) != 2 || removed[0] != defaultBin || removed[1] != customBin {
		t.Fatalf("PATH migration: %#v, %v, %v", updated, removed, err)
	}

	createTestLauncher(t, otherBin, "ml.cmd", "@echo off")
	if updated, _, err := value.removeLegacyLaunchers(newBin); err == nil || updated != value {
		t.Fatalf("unexpected PATH modification for unrelated ml: %#v, %v", updated, err)
	}
}

func createTestLauncher(t *testing.T, dir, name, data string) {
	t.Helper()
	if err := os.MkdirAll(dir, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, name), []byte(data), 0600); err != nil {
		t.Fatal(err)
	}
}
