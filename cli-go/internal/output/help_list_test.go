package output

import (
	"strings"
	"testing"
)

func TestHelpListRequiredMarkerAndNarrowLayout(t *testing.T) {
	section := HelpBlock{Title: "目标", Rows: []HelpRow{
		{Label: "--pod-ip <Pod IP>", Description: "用于匹配目标主机的 Pod IP（必填）", Required: true},
		{Label: "--name <服务名称>", Description: "按服务名称筛选"},
	}}
	var out strings.Builder
	const redMarker = "\x1b[31m*\x1b[0m"
	writeHelpRows(&out, section, 34, redMarker)
	text := out.String()
	if !strings.Contains(text, redMarker+" --pod-ip <Pod IP>\n") || !strings.Contains(text, "（必填）") ||
		strings.Count(text, redMarker) != 1 || !strings.Contains(text, "    --name <服务名称>\n") {
		t.Fatalf("unexpected narrow help:\n%s", text)
	}
	out.Reset()
	t.Setenv("NO_COLOR", "1")
	if err := WriteHelpList(&out, "", []HelpBlock{section}); err != nil || strings.Contains(out.String(), "\x1b") ||
		!strings.Contains(out.String(), "* --pod-ip <Pod IP>") {
		t.Fatalf("unexpected plain help: %v\n%s", err, out.String())
	}
}
