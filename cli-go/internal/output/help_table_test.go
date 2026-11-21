package output

import (
	"strings"
	"testing"
)

func TestHelpPanelsAndRequiredMarker(t *testing.T) {
	arguments := []HelpRow{{Label: "service_id", Value: "TEXT", Required: true, Description: []string{"服务 ID", "[required]"}}}
	options := []HelpRow{
		{Label: "--pod-ip", Value: "TEXT", Required: true, Description: []string{"Pod IP", "[required]"}},
		{Label: "--help", Description: []string{"Show this message and exit."}},
	}
	const redMarker = "\x1b[31m*\x1b[0m"
	for _, width := range []int{24, 34, 48, 80, 120} {
		text := renderHelp("ml service host mock", "[OPTIONS] SERVICE_ID", "使用样例报文测试指定主机", arguments, options, nil, width, width, helpStyle{marker: "\x1b[31m"})
		if !strings.Contains(text, "\n╭─ Arguments ") || !strings.Contains(text, "\n╭─ Options ") ||
			strings.Count(text, "╰") != 2 || strings.Count(text, redMarker) != 2 ||
			strings.Contains(text, "╭─ Commands ") {
			t.Fatalf("unexpected %d-column help:\n%s", width, text)
		}
		lines := strings.Split(strings.TrimSuffix(text, "\n\n"), "\n")
		for _, line := range lines {
			if helpLineWidth(line) != width {
				t.Fatalf("misaligned %d-column line: %q", width, line)
			}
		}
	}
}
