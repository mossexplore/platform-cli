package command

import (
	"strings"
	"testing"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestHelpUsesGoCommandSurface(t *testing.T) {
	t.Setenv("TERMINAL_WIDTH", "120")
	for _, tc := range []struct {
		path string
		want []string
		omit string
	}{
		{"", []string{"WiseRec平台命令行客户端", "╭─ Commands "}, "--no-history"},
		{"service", []string{"╭─ Commands ", "│ host ", "│ deployment "}, "│ logs "},
		{"service host", []string{"│ pod-event ", "│ log-stdout ", "│ log-search "}, "示例 ID"},
		{"service host pod-event", []string{"[OPTIONS] [SERVICE_ID]", "╭─ Arguments ", "--pod", "--cluster-name"}, "示例 ID"},
		{"service host log-search", []string{"╭─ Options ", "--list", "--grep-line"}, "示例 ID"},
		{"service list", []string{"--name,--service-name", "--all-business", "-A"}, "示例 ID"},
	} {
		t.Run(tc.path, func(t *testing.T) {
			code, out, stderr := run(t, localstate.Paths{}, append(strings.Fields(tc.path), "--help")...)
			if code != 0 || stderr != "" || strings.Contains(out, tc.omit) {
				t.Fatalf("unexpected help: %d %s\n%s", code, stderr, out)
			}
			for _, part := range tc.want {
				if !strings.Contains(out, part) {
					t.Errorf("missing %q in:\n%s", part, out)
				}
			}
		})
	}
}
