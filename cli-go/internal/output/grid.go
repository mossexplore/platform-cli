package output

import (
	"errors"
	"io"
	"strings"
)

// Grid lays out entries left to right in equal-width columns without a header.
func Grid(out io.Writer, entries []string, columns int) error {
	if columns < 1 {
		return errors.New("网格列数须为正整数")
	}
	if len(entries) == 0 {
		return nil
	}
	// Leave room for borders, padding and at least one wide character per cell.
	contentWidth := max(columns*2, terminalWidth(out)-(columns*3+1))
	widths := make([]int, columns)
	for index := range widths {
		widths[index] = contentWidth / columns
		if index < contentWidth%columns {
			widths[index]++
		}
	}
	grid := textTable{widths: widths, wrap: wrapGridCell}
	grid.border("┌", "┬", "┐", "─")
	for offset := 0; offset < len(entries); offset += columns {
		if offset > 0 {
			grid.border("├", "┼", "┤", "─")
		}
		grid.row(entries[offset:min(offset+columns, len(entries))], "│", "")
	}
	grid.border("└", "┴", "┘", "─")
	_, err := io.WriteString(out, grid.text.String())
	return err
}

func wrapGridCell(value string, width int) string {
	var lines []string
	for _, line := range strings.Split(value, "\n") {
		if cells.StringWidth(line) <= width {
			lines = append(lines, line)
			continue
		}
		current := ""
		for _, word := range strings.Fields(line) {
			if current != "" {
				if cells.StringWidth(current)+1+cells.StringWidth(word) <= width {
					current += " " + word
					continue
				}
				lines = append(lines, current)
			}
			folded := strings.Split(cells.Wrap(word, width), "\n")
			lines = append(lines, folded[:len(folded)-1]...)
			current = folded[len(folded)-1]
		}
		lines = append(lines, current)
	}
	return strings.Join(lines, "\n")
}
