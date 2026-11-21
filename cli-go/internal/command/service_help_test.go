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
		{"service", []string{"用法", "查询", "deployment", "测试", "示例", "帮助"}},
		{"service list", []string{"用法", "示例", "ml service list --name demo", "筛选", "--name <服务名称>", "查询范围", "-A, --all-business", "分页与输出", "默认 10", "帮助"}},
		{"service mock", []string{"示例", exampleServiceID, "实际调用", "位置参数", "* SERVICE_ID", "样例与调用", "帮助"}},
		{"service host", []string{"主机查询", "事件与日志", "log-search", "测试", "示例", "帮助"}},
		{"service host list", []string{"第 1 页的 10 条", "示例", "位置参数", "* SERVICE_ID", "筛选", "--pod-ip <Pod IP>"}},
		{"service host mock", []string{"SERVICE_ID --pod-ip <Pod IP> [选项]", "示例", "位置参数", "* SERVICE_ID", "* --pod-ip <Pod IP>", "（必填）", "样例与调用", "帮助"}},
		{"service host pod-event", []string{"pod-event SERVICE_ID [选项]", "pod-event --pod <Pod 名称> --cluster-name <集群名称> [选项]", "示例", "[SERVICE_ID]", "（可选）"}},
		{"service host log-stdout", []string{"log-stdout SERVICE_ID [选项]", "log-stdout --pod <Pod 名称> [选项]", "示例", "默认 appcontainer", "默认 text"}},
		{"service host log-search", []string{"示例", "--list 不能与正文检索选项同时使用", "位置参数", "目标与日志文件", "须与 --cluster-name 一起传入", "正文检索", "默认 200"}},
		{"service deployment", []string{"子命令", "list", "示例", "帮助"}},
		{"service deployment list", []string{"第 1 页的 10 条", "示例", "位置参数", "* SERVICE_ID", "输出", "帮助"}},
	} {
		t.Run(tc.path, func(t *testing.T) {
			code, out, stderr := run(t, localstate.Paths{}, append(strings.Fields(tc.path), "--help")...)
			if code != 0 || stderr != "" || !strings.HasPrefix(out, " 用法："+"ml "+tc.path) ||
				!strings.Contains(out, "\n╭─ 示例 ") ||
				!strings.Contains(out, "\n╭─ 帮助 ") || strings.Contains(out, "\x1b") {
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

func TestServiceHelpExamplesUseRegisteredCommands(t *testing.T) {
	for path, page := range serviceHelpPages {
		for _, example := range page.examples {
			if strings.HasPrefix(example, "#") {
				continue
			}
			t.Run(example, func(t *testing.T) {
				words := strings.Fields(example)
				root := newRoot(Options{Version: "test"})
				cmd, rest, err := root.Find(words[1:])
				if err != nil || !cmd.Runnable() && !slices.Contains(rest, "--help") {
					t.Fatalf("unrecognized command: %v", err)
				}
				if !strings.HasPrefix(cmd.CommandPath(), "ml "+path) {
					t.Fatalf("example targets another command: %s", cmd.CommandPath())
				}
				cmd.InitDefaultHelpFlag()
				if err := cmd.ParseFlags(rest); err != nil {
					t.Fatal(err)
				}
				if !slices.Contains(rest, "--help") {
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
