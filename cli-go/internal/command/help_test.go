package command

import (
	"bytes"
	"context"
	"os"
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func TestRegisteredCommandHelp(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "160")
	root := newRoot(Options{Version: "test"})
	root.InitDefaultHelpCmd()
	var check func(*cobra.Command)
	check = func(cmd *cobra.Command) {
		t.Run(cmd.CommandPath(), func(t *testing.T) {
			var stdout, stderr bytes.Buffer
			args := strings.Fields(cmd.CommandPath())[1:]
			code := Run(context.Background(), Options{
				Args: append(args, "--help"), Version: "test", Stdout: &stdout, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) {
					t.Fatal("help tried to read local state")
					return localstate.Paths{}, nil
				},
			})
			help := stdout.String()
			if code != 0 || stderr.Len() != 0 || !strings.Contains(help, " Usage: "+cmd.CommandPath()) ||
				!strings.Contains(help, "╭─ Options ") || !strings.Contains(help, helpDescription) ||
				strings.Contains(help, "├") || strings.Contains(help, "╭─ 示例") {
				t.Fatalf("help: exit %d, stderr %q\n%s", code, &stderr, help)
			}

			cmd.InitDefaultHelpFlag()
			cmd.InitDefaultVersionFlag()
			cmd.InheritedFlags()
			cmd.Flags().VisitAll(func(flag *pflag.Flag) {
				if !flag.Hidden && !strings.Contains(help, "--"+flag.Name) {
					t.Errorf("flag --%s missing from help", flag.Name)
				}
			})
			for _, child := range cmd.Commands() {
				if child.IsAvailableCommand() && !strings.Contains(help, "│ "+child.Name()+" ") {
					t.Errorf("child %q missing from Commands", child.Name())
				}
			}
		})
		for _, child := range cmd.Commands() {
			if child.IsAvailableCommand() || child.Name() == "help" {
				check(child)
			}
		}
	}
	check(root)
}

func TestPythonHelpLayout(t *testing.T) {
	t.Setenv("NO_COLOR", "1")
	t.Setenv("COLUMNS", "80")
	for _, tc := range []struct {
		path, width, fixture string
	}{
		{"train", "80", "train-help.txt"},
		{"algorithm clone", "80", "algorithm-clone-help.txt"},
		{"jupyter exec", "48", "jupyter-exec-help.txt"},
	} {
		t.Run(tc.path, func(t *testing.T) {
			t.Setenv("TERMINAL_WIDTH", tc.width)
			want, err := os.ReadFile("testdata/" + tc.fixture)
			if err != nil {
				t.Fatal(err)
			}
			fixture := strings.ReplaceAll(string(want), "\r\n", "\n")
			code, out, stderr := run(t, localstate.Paths{}, append(strings.Fields(tc.path), "--help")...)
			if code != 0 || stderr != "" || trimHelpPadding(out) != fixture+"\n" {
				t.Fatalf("help differs from Python: exit %d, stderr %q\n%s", code, stderr, out)
			}
		})
	}
}

func trimHelpPadding(help string) string {
	lines := strings.Split(help, "\n")
	for i, line := range lines {
		lines[i] = strings.TrimRight(line, " ")
	}
	return strings.Join(lines, "\n")
}

func TestBusinessHelpAdvertisesDirectTenantSelection(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "100")
	for _, args := range [][]string{{"business"}, {"business", "--help"}} {
		var stdout, stderr bytes.Buffer
		code := Run(context.Background(), Options{
			Args: args, Stdout: &stdout, Stderr: &stderr,
			Paths: func() (localstate.Paths, error) {
				t.Fatal("business help tried to read local state")
				return localstate.Paths{}, nil
			},
		})
		if code != 0 || stderr.Len() != 0 || !strings.Contains(stdout.String(), "[TENANT_ID | COMMAND [ARGS]...]") ||
			!strings.Contains(stdout.String(), "│ use ") {
			t.Fatalf("business help: exit %d, stderr %q\n%s", code, &stderr, &stdout)
		}
	}
}
