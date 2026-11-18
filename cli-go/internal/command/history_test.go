package command

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestHistoryRecordsNewArgumentsAndKeepsExistingRows(t *testing.T) {
	paths := localstate.Paths{Dir: t.TempDir()}
	for i := 1; i <= 21; i++ {
		if err := paths.AppendHistory(localstate.HistoryEntry{
			Time: "2026-01-01 00:00:00", Started: float64(i), Status: "success", Command: "ml train list [REDACTED]",
		}); err != nil {
			t.Fatal(err)
		}
	}
	run(t, paths, "train", "list", "--name", "demo task", "--page", "3")
	code, out, stderr := run(t, paths, "history", "list", "-o", "json")
	var rows []localstate.HistoryEntry
	if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &rows) != nil || len(rows) != 20 {
		t.Fatalf("unexpected history: %d %s %s", code, out, stderr)
	}
	want := "ml train list --name " + quoteHistoryArg("demo task") + " --page 3"
	if rows[0].Command != want || rows[0].Redacted || rows[1].Command != "ml train list [REDACTED]" {
		t.Fatalf("unexpected command history: %+v", rows[:2])
	}
	code, out, stderr = run(t, paths, "history", "list", "--search", "demo task", "--limit", "1", "-o", "json")
	if code != 0 || stderr != "" || json.Unmarshal([]byte(out), &rows) != nil || len(rows) != 1 || rows[0].Command != want {
		t.Fatalf("unexpected filtered history: %d %s %s", code, out, stderr)
	}
}

func TestHistoryPagination(t *testing.T) {
	rows := make([]localstate.HistoryEntry, 21)
	for i := range rows {
		rows[i] = localstate.HistoryEntry{Time: "2026-01-01 00:00:00", Status: "success", Command: fmt.Sprintf("ml row-%02d", i+1)}
	}
	var out, prompts bytes.Buffer
	if err := browseHistory(context.Background(), strings.NewReader("p\nx\nn\nn\np\nq\n"), &out, &prompts, rows); err != nil {
		t.Fatal(err)
	}
	if strings.Count(out.String(), "第 1 / 2 页") != 2 || strings.Count(out.String(), "第 2 / 2 页") != 1 ||
		strings.Count(out.String(), "ml row-20") != 2 || strings.Count(out.String(), "ml row-21") != 1 ||
		!strings.Contains(prompts.String(), "已经是第一页") || !strings.Contains(prompts.String(), "已经是最后一页") ||
		!strings.Contains(prompts.String(), "请输入 n、p 或 q") {
		t.Fatalf("unexpected pagination: %s %s", &out, &prompts)
	}
}

func TestHistoryCommandRedaction(t *testing.T) {
	for _, test := range []struct {
		path string
		args []string
	}{
		{"ml train config update", []string{"train", "config", "update", "TASK_ID", "--customize-config", "sensitive-fixture"}},
		{"ml jupyter exec", []string{"jupyter", "exec", "--", "python", "-c", "sensitive-fixture"}},
		{"ml train list", []string{"train", "list", "--name=https://example.test/log?X-Obs-Signature=sensitive-fixture"}},
		{"ml train list", []string{"train", "list", "--name", `{"password":"sensitive-fixture"}`}},
		{"ml train list", []string{"train", "list", "--token=sensitive-fixture"}},
	} {
		command, redacted, truncated := formatHistoryCommand(test.path, test.args)
		if !redacted || truncated || strings.Contains(command, "sensitive-fixture") {
			t.Errorf("command was not redacted: %s", command)
		}
	}
	command, redacted, truncated := formatHistoryCommand("ml train list", []string{"train", "list", "--name", strings.Repeat("测", 9000)})
	if redacted || !truncated || len([]rune(command)) != maxHistoryCommand {
		t.Fatal("unexpected truncation of long history command")
	}
}
