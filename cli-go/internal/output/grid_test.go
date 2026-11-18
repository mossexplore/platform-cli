package output

import (
	"bytes"
	"strings"
	"testing"
)

func TestGridWrapsWideTextWithinTerminalWidth(t *testing.T) {
	t.Setenv("COLUMNS", "36")
	var out bytes.Buffer
	if err := Grid(&out, []string{"1 20261017-000000 运行成功", "2 20261018-000000 执行失败"}, 4); err != nil {
		t.Fatal(err)
	}
	var first strings.Builder
	lines := strings.Split(strings.TrimSuffix(out.String(), "\n"), "\n")
	for _, line := range lines {
		if cells.StringWidth(line) != 36 {
			t.Fatalf("grid line overflows or is misaligned: %q\n%s", line, &out)
		}
		if strings.HasPrefix(line, "│") {
			parts := strings.Split(line, "│")
			if len(parts) != 6 {
				t.Fatalf("grid row lost a column: %q", line)
			}
			first.WriteString(strings.TrimSpace(parts[1]))
		}
	}
	if len(lines) <= 3 || first.String() != "120261017-000000运行成功" {
		t.Fatalf("expected folded period and status: %s", &out)
	}
}
