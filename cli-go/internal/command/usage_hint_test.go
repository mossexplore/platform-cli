package command

import (
	"bytes"
	"context"
	"strings"
	"testing"
)

func TestUsageHintOnUnknownFlagAndSuggestion(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args:    []string{"feature-task", "list", "--creator", "alice"},
		Version: "1.0.0",
		Stdout:  &stdout,
		Stderr:  &stderr,
	})
	if code != 2 {
		t.Fatalf("expected exit code 2, got %d; stderr=%s", code, stderr.String())
	}
	if stdout.Len() != 0 {
		t.Fatalf("expected empty stdout, got %q", stdout.String())
	}
	errText := stderr.String()
	for _, want := range []string{
		"[提示] 是否指：--create-user",
		"[用法] ml feature-task list [OPTIONS]",
		"[选项]",
		"--category=dpp-all",
		"--create-user STRING",
		"--agent",
	} {
		if !strings.Contains(errText, want) {
			t.Errorf("stderr missing %q\nfull stderr:\n%s", want, errText)
		}
	}
}

func TestUsageHintOnMissingPositionalArg(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args:    []string{"train", "history", "list"},
		Version: "1.0.0",
		Stdout:  &stdout,
		Stderr:  &stderr,
	})
	if code != 2 {
		t.Fatalf("expected exit code 2, got %d; stderr=%s", code, stderr.String())
	}
	errText := stderr.String()
	for _, want := range []string{
		"[用法] ml train history list TASK_ID [OPTIONS]",
		"--latest-flag=true",
		"--page=1",
		"--page-size=10",
	} {
		if !strings.Contains(errText, want) {
			t.Errorf("stderr missing %q\nfull stderr:\n%s", want, errText)
		}
	}
}

func TestUsageHintOnUnknownSubcommand(t *testing.T) {
	var stdout, stderr bytes.Buffer
	code := Run(context.Background(), Options{
		Args:    []string{"service", "hots"},
		Version: "1.0.0",
		Stdout:  &stdout,
		Stderr:  &stderr,
	})
	if code != 2 {
		t.Fatalf("expected exit code 2, got %d; stderr=%s", code, stderr.String())
	}
	errText := stderr.String()
	for _, want := range []string{
		"[提示] 是否指：host",
		"[子命令]",
		"host",
		"list",
	} {
		if !strings.Contains(errText, want) {
			t.Errorf("stderr missing %q\nfull stderr:\n%s", want, errText)
		}
	}
}
