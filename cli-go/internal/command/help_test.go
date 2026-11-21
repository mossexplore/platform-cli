package command

import (
	"bytes"
	"context"
	"slices"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func TestRegisteredCommandHelp(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "100")
	root := newRoot(Options{Version: "test"})
	root.InitDefaultHelpCmd()
	var check func(*cobra.Command)
	check = func(cmd *cobra.Command) {
		t.Run(cmd.CommandPath(), func(t *testing.T) {
			var out, stderr bytes.Buffer
			args := strings.Fields(cmd.CommandPath())[1:]
			code := Run(context.Background(), Options{
				Args: append(args, "--help"), Version: "test", Stdout: &out, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) {
					t.Fatal("help tried to read local state")
					return localstate.Paths{}, nil
				},
			})
			help := out.String()
			if code != 0 || stderr.Len() != 0 || !strings.Contains(help, cmd.CommandPath()) ||
				!strings.Contains(help, "-h, --help") {
				t.Fatalf("help: exit %d, stderr %q\n%s", code, &stderr, help)
			}
			_, arguments, _ := strings.Cut(cmd.Use, " ")
			expected := []string{"用途", "示例"}
			if arguments != "" {
				expected = append(expected, "位置参数")
			}
			expected = append(expected, "选项")
			var sections []string
			for _, line := range strings.Split(strings.TrimSuffix(help, "\n"), "\n") {
				switch {
				case strings.HasPrefix(line, "╭  "), strings.HasPrefix(line, "├  "):
					title, _, _ := strings.Cut(strings.TrimSpace(line[len("╭"):]), " ")
					sections = append(sections, title)
				case strings.HasPrefix(line, "│") && strings.HasSuffix(line, "│"):
				case strings.HasPrefix(line, "╰") && strings.HasSuffix(line, "╯"):
				default:
					t.Errorf("content outside the table: %q", line)
				}
			}
			if !slices.Equal(sections, expected) || strings.Count(help, "╰") != 1 {
				t.Fatalf("help sections %v, want %v:\n%s", sections, expected, help)
			}
			for _, row := range helpArguments(cmd, arguments) {
				if strings.HasPrefix(row[1], "（") || !strings.Contains(help, row[0]) {
					t.Errorf("missing position argument or description: %v", row)
				}
			}
			cmd.Flags().VisitAll(func(flag *pflag.Flag) {
				listed := strings.Contains(help, "--"+flag.Name+" ")
				if !flag.Hidden && (!listed || flag.Usage == "" || flag.Usage == flag.Name) {
					t.Errorf("flag --%s missing from help or lacks a description", flag.Name)
				}
			})
		})
		for _, child := range cmd.Commands() {
			if child.IsAvailableCommand() || child.Name() == "help" {
				check(child)
			}
		}
	}
	check(root)
}

func TestHelpSectionsAndDefaults(t *testing.T) {
	for _, tc := range []struct {
		command, width string
		want           []string
	}{
		{"jupyter exec", "100", []string{"[选项] -- PROGRAM [ARG...]", "--startup-timeout <秒数>", "默认 60"}},
		{"jupyter exec", "34", []string{"├  位置参数 ", "--startup-timeout <秒数>", "默认 60"}},
		{"algorithm clone", "100", []string{"--name <算法仓名称>", "--version <版本号>", "* --version", "（必填）", "--version 1.0.0"}},
		{"jupyter files write", "100", []string{"(--from-file <本地文件> | --stdin)", "必须在 --from-file 与 --stdin 中选择一项"}},
		{"offline experiment list", "100", []string{"--project-name", "按离线实验描述筛选"}},
	} {
		t.Run(tc.command, func(t *testing.T) {
			t.Setenv("TERMINAL_WIDTH", tc.width)
			code, out, stderr := run(t, localstate.Paths{}, append(strings.Fields(tc.command), "--help")...)
			if code != 0 || stderr != "" {
				t.Fatalf("help: %d %s", code, stderr)
			}
			for _, want := range tc.want {
				if !strings.Contains(out, want) {
					t.Errorf("missing %q in help:\n%s", want, out)
				}
			}
		})
	}
}
