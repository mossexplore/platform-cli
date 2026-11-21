package output

import (
	"fmt"
	"io"
	"os"
	"strings"
)

type HelpRow struct {
	Label, Description string
	Required           bool
}

type HelpBlock struct {
	Title         string
	Lines         []string
	Rows          []HelpRow
	PreserveWords bool
}

func WriteHelpTable(out io.Writer, title, intro string, sections []HelpBlock) error {
	marker := "*"
	if file, ok := out.(*os.File); ok {
		if _, noColor := os.LookupEnv("NO_COLOR"); !noColor {
			color, restore := enableHelpColor(file)
			if restore != nil {
				defer restore()
			}
			if color {
				marker = "\x1b[31m*\x1b[0m"
			}
		}
	}
	table := renderHelpTable(title, intro, sections, helpTerminalWidth(out), marker)
	_, err := io.WriteString(out, table)
	return err
}

func renderHelpTable(title, intro string, sections []HelpBlock, width int, marker string) string {
	labelWidth, markerWidth := 0, 0
	width = max(width, cells.StringWidth(title)+6)
	for _, section := range sections {
		width = max(width, cells.StringWidth(section.Title)+6)
		for _, row := range section.Rows {
			labelWidth = max(labelWidth, cells.StringWidth(row.Label))
			if row.Required {
				markerWidth = 2
			}
		}
	}
	labelWidth += markerWidth
	const padding = 4 // Two borders and one space inside each border.
	width = max(width, labelWidth+padding)
	table := helpTable{
		contentWidth: width - padding,
		labelWidth:   labelWidth,
		markerWidth:  markerWidth,
		marker:       marker,
	}
	table.header("┌", title, "┐")
	table.fullRow(intro, false)
	for _, section := range sections {
		if len(section.Rows)+len(section.Lines) == 0 {
			continue
		}
		table.header("├", section.Title, "┤")
		for _, line := range section.Lines {
			table.fullRow(line, section.PreserveWords)
		}
		for _, row := range section.Rows {
			table.row(row)
		}
	}
	fmt.Fprintf(&table.text, "└%s┘\n", strings.Repeat("─", width-2))
	return table.text.String()
}

type helpTable struct {
	text                                  strings.Builder
	contentWidth, labelWidth, markerWidth int
	marker                                string
}

func (t *helpTable) header(left, title, right string) {
	fill := t.contentWidth - cells.StringWidth(title) - 1
	fmt.Fprintf(&t.text, "%s  %s %s%s\n", left, title, strings.Repeat("─", fill), right)
}

func (t *helpTable) fullRow(line string, preserveWords bool) {
	for _, wrapped := range strings.Split(wrapHelpText(line, t.contentWidth, preserveWords), "\n") {
		fmt.Fprintf(&t.text, "│ %s │\n", padHelpText(wrapped, t.contentWidth))
	}
}

func (t *helpTable) row(row HelpRow) {
	prefix := strings.Repeat(" ", t.markerWidth)
	if row.Required {
		prefix = t.marker + " "
	}
	label := prefix + padHelpText(row.Label, t.labelWidth-t.markerWidth)
	descriptionWidth := t.contentWidth - t.labelWidth - 3 // Space, divider, space.
	if descriptionWidth < 18 {
		fmt.Fprintf(&t.text, "│ %s%s │\n", label, strings.Repeat(" ", t.contentWidth-t.labelWidth))
		indent := "  "
		for _, line := range strings.Split(wrapHelpDescription(row.Description, t.contentWidth-len(indent)), "\n") {
			fmt.Fprintf(&t.text, "│ %s │\n", padHelpText(indent+line, t.contentWidth))
		}
		return
	}
	for _, line := range strings.Split(wrapHelpDescription(row.Description, descriptionWidth), "\n") {
		fmt.Fprintf(&t.text, "│ %s │ %s │\n", label, padHelpText(line, descriptionWidth))
		label = strings.Repeat(" ", t.labelWidth)
	}
}

func padHelpText(text string, width int) string {
	return text + strings.Repeat(" ", max(0, width-cells.StringWidth(text)))
}

func wrapHelpText(text string, width int, preserveWords bool) string {
	var lines []string
	for _, paragraph := range strings.Split(text, "\n") {
		for cells.StringWidth(paragraph) > width {
			line, _, _ := strings.Cut(cells.Wrap(paragraph, width), "\n")
			// Keep command arguments together when they fit on the next line.
			if space := strings.LastIndexByte(line, ' '); space > 0 &&
				(preserveWords || cells.StringWidth(line[:space]) >= width*2/3) {
				line = line[:space]
			}
			lines = append(lines, line)
			paragraph = strings.TrimLeft(paragraph[len(line):], " ")
		}
		lines = append(lines, paragraph)
	}
	return strings.Join(lines, "\n")
}

func wrapHelpDescription(description string, width int) string {
	for _, label := range []string{"（必填）", "（可选）"} {
		if body, ok := strings.CutSuffix(description, label); ok {
			body = wrapHelpText(body, width, false)
			lastLine := body[strings.LastIndexByte(body, '\n')+1:]
			if cells.StringWidth(lastLine+label) > width {
				body += "\n"
			}
			return body + label
		}
	}
	return wrapHelpText(description, width, false)
}
