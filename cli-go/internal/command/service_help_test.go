package command

import (
	"slices"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestServiceHelpLayout(t *testing.T) {
	t.Setenv("NO_COLOR", "1")
	t.Setenv("TERMINAL_WIDTH", "100")
	for _, tc := range []struct {
		path  string
		order []string
	}{
		{"service", []string{"用途", "用法", "deployment", "示例", "选项"}},
		{"service list", []string{"用法", "示例", "ml service list --name demo", "选项", "-A, --all-business", "--name <服务名称>", "默认 10"}},
		{"service mock", []string{"实际调用", "示例", exampleServiceID, "位置参数", "* SERVICE_ID", "选项"}},
		{"service host", []string{"用途", "log-search", "示例", "选项"}},
		{"service host list", []string{"第 1 页的 10 条", "示例", "位置参数", "* SERVICE_ID", "选项", "--pod-ip <Pod IP>"}},
		{"service host mock", []string{"SERVICE_ID --pod-ip <Pod IP> [选项]", "示例", "位置参数", "* SERVICE_ID", "选项", "* --pod-ip <Pod IP>", "（必填）"}},
		{"service host pod-event", []string{"pod-event SERVICE_ID [选项]", "pod-event --pod <Pod 名称> --cluster-name <集群名称> [选项]", "示例", "[SERVICE_ID]", "（可选）"}},
		{"service host log-stdout", []string{"log-stdout SERVICE_ID [选项]", "log-stdout --pod <Pod 名称> [选项]", "示例", "默认 appcontainer", "默认 text"}},
		{"service host log-search", []string{"--list 不能与正文检索选项同时使用", "示例", "位置参数", "选项", "默认 200", "须与 --cluster-name 一起传入"}},
		{"service deployment", []string{"<子命令>", "list", "示例", "选项"}},
		{"service deployment list", []string{"第 1 页的 10 条", "示例", "位置参数", "* SERVICE_ID", "选项"}},
	} {
		t.Run(tc.path, func(t *testing.T) {
			code, out, stderr := run(t, localstate.Paths{}, append(strings.Fields(tc.path), "--help")...)
			if code != 0 || stderr != "" || !strings.HasPrefix(out, "╭     用途 ") ||
				!strings.Contains(out, "\n│ 用法：ml "+tc.path) ||
				!strings.Contains(out, "\n├     示例 ") || strings.Contains(out, "\x1b") {
				t.Fatalf("unexpected help: %d %s\n%s", code, stderr, out)
			}
			rest := out
			for _, part := range tc.order {
				_, tail, found := strings.Cut(rest, part)
				if !found {
					t.Fatalf("missing or out of order %q in:\n%s", part, out)
				}
				rest = tail
			}
		})
	}
}

func TestHelpExamplesUseRegisteredCommands(t *testing.T) {
	for _, pages := range []map[string]helpPage{helpPages, serviceHelpPages} {
		for path, page := range pages {
			for _, example := range page.examples {
				if strings.HasPrefix(example, "#") {
					continue
				}
				t.Run(example, func(t *testing.T) {
					words := strings.Fields(example)
					root := newRoot(Options{Version: "test"})
					root.InitDefaultHelpCmd()
					cmd, rest, err := root.Find(words[1:])
					isHelp := slices.Contains(rest, "--help")
					if err != nil || !cmd.Runnable() && !isHelp {
						t.Fatalf("unrecognized command: %v", err)
					}
					expected := strings.TrimSpace("ml " + path)
					if cmd.CommandPath() != expected && !strings.HasPrefix(cmd.CommandPath(), expected+" ") {
						t.Fatalf("example targets another command: %s", cmd.CommandPath())
					}
					cmd.InitDefaultHelpFlag()
					if err := cmd.ParseFlags(rest); err != nil {
						t.Fatal(err)
					}
					if !isHelp {
						if err := cmd.ValidateArgs(cmd.Flags().Args()); err != nil {
							t.Fatal(err)
						}
						if err := cmd.ValidateRequiredFlags(); err != nil {
							t.Fatal(err)
						}
					}
				})
			}
		}
	}
}
