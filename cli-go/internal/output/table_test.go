package output

import (
	"bytes"
	"strings"
	"testing"
)

func TestTableHighlightColorsWrappedCellsAndLeavesBordersPlain(t *testing.T) {
	headers := []string{"环境", "地址"}
	rows := [][]string{
		{"其他", "test"},
		{"当前", "https://preview.example.test/path"},
	}
	style := tableStyle{header: boldCyan, highlight: boldGreen, selected: 1}
	colored := tableText(headers, rows, 24, style)
	lines := strings.Split(colored, "\n")
	if len(lines) < 7 {
		t.Fatalf("expected the active row to wrap:\n%s", colored)
	}
	if !strings.HasPrefix(lines[1], "┃"+boldCyan) || strings.Count(lines[1], boldCyan) != len(headers) {
		t.Fatalf("header cells should be cyan with plain dividers:\n%s", colored)
	}
	if strings.Contains(lines[3], "\x1b[") || !strings.Contains(lines[3], "其他") {
		t.Fatalf("the other environment should have plain cells: %q", lines[3])
	}
	for _, line := range lines[4 : len(lines)-2] {
		if !strings.HasPrefix(line, "│"+boldGreen) || strings.Count(line, boldGreen) != len(headers) {
			t.Fatalf("each line of the active environment should be green: %q", line)
		}
	}
	stripColor := strings.NewReplacer(boldCyan, "", boldGreen, "", "\x1b[0m", "")
	if stripColor.Replace(colored) != tableText(headers, rows, 24, tableStyle{}) {
		t.Fatalf("color changed the text or wrapping:\n%s", colored)
	}

	t.Setenv("COLUMNS", "24")
	var redirected bytes.Buffer
	if err := HighlightedTable(&redirected, headers, rows, 1); err != nil {
		t.Fatal(err)
	}
	if redirected.String() != tableText(headers, rows, 24, tableStyle{}) {
		t.Fatalf("redirected table should be plain text:\n%s", &redirected)
	}
}
