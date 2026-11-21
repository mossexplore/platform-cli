package command

import (
	"bytes"
	"context"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func TestRegisteredCommandHelp(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "100")
	root := newRoot(Options{Version: "test"})
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
				!(strings.Contains(help, "\n选项\n") || strings.Contains(help, "\n帮助\n")) || !strings.Contains(help, "--help") {
				t.Fatalf("help: exit %d, stderr %q\n%s", code, &stderr, help)
			}
			_, arguments, _ := strings.Cut(cmd.Use, " ")
			for _, row := range helpArguments(cmd, arguments) {
				if strings.HasPrefix(row[1], "（") || !strings.Contains(help, row[0]) {
					t.Errorf("missing position argument or description: %v", row)
				}
			}
			cmd.Flags().VisitAll(func(flag *pflag.Flag) {
				listed := strings.Contains(help, "--"+flag.Name+" ") || strings.Contains(help, "--"+flag.Name+"\n")
				if !flag.Hidden && (!listed || flag.Usage == "" || flag.Usage == flag.Name) {
					t.Errorf("flag --%s missing from help or lacks a description", flag.Name)
				}
			})
		})
		for _, child := range cmd.Commands() {
			if child.IsAvailableCommand() {
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
		{"jupyter exec", "34", []string{"[选项] -- PROGRAM [ARG...]", "\n  --startup-timeout ", "（默认：60）"}},
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
