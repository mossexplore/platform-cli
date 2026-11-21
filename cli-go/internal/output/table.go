package output

import (
	"io"
	"os"
	"strconv"
	"strings"
	"unicode"

	"github.com/mattn/go-runewidth"
	"golang.org/x/term"
)

var cells = runewidth.NewCondition()

func Table(out io.Writer, headers []string, rows [][]string) error {
	_, err := io.WriteString(out, tableText(headers, rows, terminalWidth(out), tableStyle{}))
	return err
}

// HighlightedTable colors the header and the selected row on a color-capable terminal.
func HighlightedTable(out io.Writer, headers []string, rows [][]string, selected int) error {
	color, restore := terminalColor(out)
	if restore != nil {
		defer restore()
	}
	style := tableStyle{selected: selected}
	if color {
		style.header, style.highlight = boldCyan, boldGreen
	}
	_, err := io.WriteString(out, tableText(headers, rows, terminalWidth(out), style))
	return err
}

type tableStyle struct {
	header, highlight string
	selected          int
}

func terminalWidth(out io.Writer) int {
	limit := 80
	if file, ok := out.(*os.File); ok {
		if width, _, err := term.GetSize(int(file.Fd())); err == nil && width > 0 {
			limit = width
		}
	}
	if columns, err := strconv.Atoi(os.Getenv("COLUMNS")); err == nil && columns > 0 {
		limit = columns
	}
	return limit
}

func tableText(headers []string, rows [][]string, limit int, style tableStyle) string {
	if len(headers) == 0 {
		return "\n"
	}
	table := textTable{widths: tableWidths(headers, rows, limit), keepFirst: idColumn(headers[0]), wrap: cells.Wrap}
	table.border("┏", "┳", "┓", "━")
	table.row(headers, "┃", style.header)
	table.border("┡", "╇", "┩", "━")
	for index, row := range rows {
		color := ""
		if index == style.selected {
			color = style.highlight
		}
		table.row(row, "│", color)
	}
	table.border("└", "┴", "┘", "─")
	return table.text.String()
}

type textTable struct {
	text      strings.Builder
	widths    []int
	keepFirst bool
	wrap      func(string, int) string
}

func (t *textTable) border(start, join, end, line string) {
	t.text.WriteString(start)
	for i, width := range t.widths {
		if i > 0 {
			t.text.WriteString(join)
		}
		t.text.WriteString(strings.Repeat(line, width+2))
	}
	t.text.WriteString(end + "\n")
}

func (t *textTable) row(row []string, bar, color string) {
	columns := make([][]string, len(t.widths))
	height := 1
	for i, value := range row {
		lines := cleanCell(value)
		if i != 0 || !t.keepFirst {
			lines = t.wrap(lines, t.widths[i])
		}
		columns[i] = strings.Split(lines, "\n")
		height = max(height, len(columns[i]))
	}
	for line := 0; line < height; line++ {
		t.text.WriteString(bar)
		for i, column := range columns {
			value := ""
			if line < len(column) {
				value = column[line]
			}
			padding := strings.Repeat(" ", max(0, t.widths[i]-cells.StringWidth(value)))
			t.text.WriteString(paintANSI(" "+value+padding+" ", color))
			t.text.WriteString(bar)
		}
		t.text.WriteByte('\n')
	}
}

func tableWidths(headers []string, rows [][]string, limit int) []int {
	widths := make([]int, len(headers))
	minimums := make([]int, len(headers))
	for i, header := range headers {
		minimums[i] = max(2, cells.StringWidth(cleanCell(header)))
		widths[i] = minimums[i]
	}
	for _, row := range rows {
		for i, value := range row {
			for _, line := range strings.Split(cleanCell(value), "\n") {
				widths[i] = max(widths[i], cells.StringWidth(line))
			}
		}
	}
	if idColumn(headers[0]) {
		// Platform IDs fit in 36 cells and must stay intact for copying.
		widths[0] = 36
		minimums[0] = widths[0]
	}
	remaining := 1 + 3*len(widths) - limit
	for _, width := range widths {
		remaining += width
	}
	for remaining > 0 {
		largest, space := 0, 0
		for i, width := range widths {
			if width-minimums[i] > space {
				largest, space = i, width-minimums[i]
			}
		}
		if space == 0 {
			break
		}
		reduce := min(space, max(1, remaining/len(widths)))
		widths[largest] -= reduce
		remaining -= reduce
	}
	return widths
}

func idColumn(header string) bool {
	return strings.HasSuffix(strings.ToLower(strings.ReplaceAll(header, " ", "")), "id")
}

func cleanCell(value string) string {
	return strings.Map(func(char rune) rune {
		if unicode.IsControl(char) && char != '\n' {
			return ' '
		}
		return char
	}, value)
}
