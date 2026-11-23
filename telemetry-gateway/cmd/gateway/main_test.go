package main

import (
	"os"
	"path/filepath"
	"testing"
)

func TestOpenLogFileUsesOptionalMountedDirectory(t *testing.T) {
	directory := filepath.Join(t.TempDir(), "logs")
	if file, err := openLogFile(directory); file != nil || err != nil {
		t.Fatalf("unmounted directory: file=%v err=%v", file, err)
	}
	if err := os.Mkdir(directory, 0o750); err != nil {
		t.Fatal(err)
	}
	path := filepath.Join(directory, "gateway.log")
	if err := os.WriteFile(path, []byte("old entry\n"), 0o640); err != nil {
		t.Fatal(err)
	}
	file, err := openLogFile(directory)
	if err != nil {
		t.Fatal(err)
	}
	_, err = file.WriteString("new entry\n")
	closeErr := file.Close()
	if err != nil || closeErr != nil {
		t.Fatalf("write=%v close=%v", err, closeErr)
	}
	if data, err := os.ReadFile(path); err != nil || string(data) != "old entry\nnew entry\n" {
		t.Fatalf("file=%q err=%v", data, err)
	}
	if err := os.Remove(path); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(path, 0o750); err != nil {
		t.Fatal(err)
	}
	if file, err := openLogFile(directory); file != nil || err == nil {
		t.Fatalf("invalid log destination: file=%v err=%v", file, err)
	}
}
