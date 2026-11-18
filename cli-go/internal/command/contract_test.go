package command

import (
	"os"
	"strings"
	"testing"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func TestPythonCommandContract(t *testing.T) {
	raw, err := os.ReadFile("testdata/python-cli.tsv")
	if err != nil {
		t.Fatal(err)
	}
	expected := make(map[string]bool)
	root := newRoot(Options{Version: "test"})
	for _, line := range strings.Split(strings.TrimSuffix(string(raw), "\n"), "\n") {
		path, metadata, ok := strings.Cut(line, "\t")
		if !ok {
			t.Fatalf("invalid Python command fixture row %q", line)
		}
		manager, options, _ := strings.Cut(metadata, "\t")
		expected[path] = true
		pieces := strings.Fields(path)
		cmd, rest, err := root.Find(pieces)
		if err != nil || len(rest) != 0 || !cmd.Runnable() {
			t.Errorf("missing command %q", path)
			continue
		}
		if wiseRecOnly(cmd) != (manager == "wiserec") {
			t.Errorf("incorrect MLOps support for %q", path)
		}
		flags := map[string]bool{}
		cmd.LocalNonPersistentFlags().VisitAll(func(flag *pflag.Flag) {
			flags["--"+flag.Name] = true
			if flag.Shorthand != "" {
				flags["-"+flag.Shorthand] = true
			}
		})
		for _, flag := range strings.Fields(options) {
			if !flags[flag] {
				t.Errorf("%q is missing flag %q", path, flag)
			}
		}
	}
	var check func(*cobra.Command)
	check = func(cmd *cobra.Command) {
		path := strings.TrimPrefix(cmd.CommandPath(), root.Name()+" ")
		if cmd != root && len(cmd.Commands()) == 0 && cmd.Runnable() && !cmd.Hidden && !expected[path] {
			t.Errorf("extra public command %q", path)
		}
		for _, child := range cmd.Commands() {
			check(child)
		}
	}
	check(root)
}
