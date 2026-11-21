package output

import (
	"io"
	"os"
	"strconv"
	"strings"
)

func HelpSection(out io.Writer, title string, rows [][2]string) error {
	if len(rows) == 0 {
		return nil
	}
	limit := terminalWidth(out)
	if width, err := strconv.Atoi(os.Getenv("TERMINAL_WIDTH")); err == nil && width > 0 {
		limit = width
	}
	keyWidth, descriptionWidth := 0, 0
	for _, row := range rows {
		keyWidth = max(keyWidth, cells.StringWidth(row[0]))
		for _, line := range strings.Split(row[1], "\n") {
			descriptionWidth = max(descriptionWidth, cells.StringWidth(line))
		}
	}
	var text strings.Builder
	text.WriteString("\n" + title + "\n")
	const borderWidth = 7
	if limit-keyWidth-borderWidth < 16 {
		// Keep option spellings intact in narrow terminals.
		for _, row := range rows {
			text.WriteString("  " + row[0] + "\n")
			for _, line := range strings.Split(cells.Wrap(row[1], max(1, limit-4)), "\n") {
				text.WriteString("    " + line + "\n")
			}
		}
	} else {
		table := textTable{
			widths:    []int{keyWidth, max(1, min(descriptionWidth, limit-keyWidth-borderWidth))},
			keepFirst: true,
			wrap:      cells.Wrap,
		}
		table.border("╭", "┬", "╮", "─")
		for _, row := range rows {
			table.row(row[:], "│")
		}
		table.border("╰", "┴", "╯", "─")
		text.WriteString(table.text.String())
	}
	_, err := io.WriteString(out, text.String())
	return err
}
