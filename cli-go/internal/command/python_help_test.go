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

func TestPythonHelpParity(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "80")
	var pythonOptions map[string][]string
	if err := loadHelpFile("options.json", &pythonOptions); err != nil {
		t.Fatal(err)
	}
	removedPythonHelpPaths := map[string]bool{
		"ml service logs": true,
	}
	for path, expected := range pythonOptions {
		if goNativeHelpPaths[path] || removedPythonHelpPaths[path] {
			continue
		}
		t.Run(path, func(t *testing.T) {
			var out, stderr bytes.Buffer
			args := strings.Fields(path)[1:]
			options := Options{
				Args: append(slices.Clone(args), "--help"), Version: "test",
				Stdout: &out, Stderr: &stderr,
				Paths: func() (localstate.Paths, error) {
					t.Fatal("help read the local state")
					return localstate.Paths{}, nil
				},
			}
			root := newRoot(options)
			cmd, rest, err := root.Find(args)
			if err != nil || len(rest) != 0 || cmd.CommandPath() != path {
				t.Fatalf("missing command: %v %v", rest, err)
			}
			cmd.InitDefaultHelpFlag()
			cmd.InitDefaultVersionFlag()
			var flags []string
			cmd.LocalFlags().VisitAll(func(flag *pflag.Flag) {
				if !flag.Hidden {
					flags = append(flags, "--"+flag.Name)
					if flag.Shorthand != "" {
						flags = append(flags, "-"+flag.Shorthand)
					}
				}
			})
			for _, flag := range expected {
				if !slices.Contains(flags, flag) {
					t.Errorf("Python help advertises an option Go does not support: %s", flag)
				}
			}
			for _, flag := range flags {
				if flag != "-h" && !(path == "ml" && flag == "-v") && !slices.Contains(expected, flag) {
					t.Errorf("Go has an option missing from the Python help: %s", flag)
				}
			}
			page, err := pythonHelpPage(path, 80)
			if err != nil {
				t.Fatal(err)
			}
			if code := Run(context.Background(), options); code != 0 || stderr.Len() != 0 ||
				out.String() != helpSGR.ReplaceAllString(page, "") {
				t.Fatalf("Go help differs from Python: code=%d stderr=%q\n%s", code, &stderr, &out)
			}
		})
	}
	var check func(*cobra.Command)
	check = func(cmd *cobra.Command) {
		if !goNativeHelpPaths[cmd.CommandPath()] {
			if _, ok := pythonOptions[cmd.CommandPath()]; !ok {
				t.Errorf("public Go command is missing Python help: %s", cmd.CommandPath())
			}
		}
		for _, child := range cmd.Commands() {
			if !child.Hidden {
				check(child)
			}
		}
	}
	check(newRoot(Options{Version: "test"}))
}
