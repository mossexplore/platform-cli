package output

import (
	"fmt"
	"strings"
	"testing"
)

func TestHelpTableBordersAndRequiredMarker(t *testing.T) {
	sections := []HelpBlock{
		{Title: "用法", PreserveWords: true, Lines: []string{"ml service host mock SERVICE_ID --pod-ip <Pod IP> [选项]"}},
		{Title: "示例", PreserveWords: true, Lines: []string{"ml service host mock 7b8f2a16-3d9c-4e51-8a72-6f04b9d1c305 --pod-ip 192.0.2.14"}},
		{Title: "目标", Rows: []HelpRow{
			{Label: "--pod-ip <Pod IP>", Description: "用于匹配目标主机的 Pod IP（必填）", Required: true},
			{Label: "--name <服务名称>", Description: "按服务名称筛选"},
		}},
		{Title: "空分组"},
	}
	const redMarker = "\x1b[31m*\x1b[0m"
	for _, width := range []int{34, 44, 80, 100} {
		t.Run(fmt.Sprint(width), func(t *testing.T) {
			text := renderHelpTable("用途", "使用样例报文测试指定主机。", sections, width, redMarker)
			if !strings.HasPrefix(text, "┌  用途 ") || !strings.Contains(text, "\n├  用法 ") ||
				!strings.Contains(text, "\n├  示例 ") || !strings.Contains(text, "\n├  目标 ") ||
				!strings.Contains(text, redMarker+" --pod-ip <Pod IP>") || !strings.Contains(text, "（必填）") ||
				strings.Count(text, redMarker) != 1 || strings.Contains(text, "空分组") {
				t.Fatalf("unexpected help:\n%s", text)
			}
			plain := strings.ReplaceAll(text, redMarker, "*")
			lines := strings.Split(strings.TrimSuffix(plain, "\n"), "\n")
			for _, line := range lines {
				characters := []rune(line)
				if cells.StringWidth(line) != width || len(characters) == 0 ||
					!strings.ContainsRune("┌├│└", characters[0]) ||
					!strings.ContainsRune("┐┤│┘", characters[len(characters)-1]) {
					t.Fatalf("line escaped the table or did not align: %q", line)
				}
			}
			if !strings.HasPrefix(lines[len(lines)-1], "└") {
				t.Fatalf("missing bottom border: %s", text)
			}
			if width >= 44 && !strings.Contains(text, "7b8f2a16-3d9c-4e51-8a72-6f04b9d1c305") {
				t.Fatalf("example split a service ID that fits on one line:\n%s", text)
			}
			twoColumns := strings.Contains(text, "<服务名称> │ 按服务名称筛选")
			if twoColumns != (width >= 44) {
				t.Fatalf("unexpected column layout:\n%s", text)
			}
		})
	}

	var out strings.Builder
	t.Setenv("NO_COLOR", "1")
	if err := WriteHelpTable(&out, "用途", "", sections); err != nil || strings.Contains(out.String(), "\x1b") ||
		!strings.Contains(out.String(), "* --pod-ip <Pod IP>") {
		t.Fatalf("unexpected plain help: %v\n%s", err, out.String())
	}
}
