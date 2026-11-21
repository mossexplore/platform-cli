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
	Title string
	Rows  []HelpRow
	Text  string
}

func WriteHelpList(out io.Writer, introduction string, sections []HelpBlock) error {
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

	var text strings.Builder
	text.WriteString(introduction)
	width := helpTerminalWidth(out)
	for _, section := range sections {
		if section.Text != "" {
			text.WriteString(section.Text)
		}
		if len(section.Rows) > 0 {
			writeHelpRows(&text, section, width, marker)
		}
	}
	_, err := io.WriteString(out, text.String())
	return err
}

func writeHelpRows(out *strings.Builder, section HelpBlock, width int, marker string) {
	fmt.Fprintf(out, "\n%s\n", section.Title)
	labelWidth := 0
	hasRequired := false
	for _, row := range section.Rows {
		labelWidth = max(labelWidth, cells.StringWidth(row.Label))
		hasRequired = hasRequired || row.Required
	}
	prefixWidth := 2
	if hasRequired {
		prefixWidth += 2
	}
	column := prefixWidth + labelWidth + 3
	stacked := width-column < 18
	for _, row := range section.Rows {
		prefix := "  "
		if row.Required {
			prefix += marker + " "
		} else if hasRequired {
			prefix += "  "
		}
		out.WriteString(prefix + row.Label)
		indent := column
		if stacked {
			out.WriteByte('\n')
			indent = prefixWidth + 2
			out.WriteString(strings.Repeat(" ", indent))
		} else {
			out.WriteString(strings.Repeat(" ", column-prefixWidth-cells.StringWidth(row.Label)))
		}
		separator := "\n" + strings.Repeat(" ", indent)
		out.WriteString(strings.ReplaceAll(wrapHelpDescription(row.Description, max(1, width-indent)), "\n", separator))
		out.WriteByte('\n')
	}
}

func wrapHelpDescription(description string, width int) string {
	for _, label := range []string{"（必填）", "（可选）"} {
		if body, ok := strings.CutSuffix(description, label); ok {
			body = cells.Wrap(body, width)
			lastLine := body[strings.LastIndexByte(body, '\n')+1:]
			if cells.StringWidth(lastLine+label) > width {
				body += "\n"
			}
			return body + label
		}
	}
	return cells.Wrap(description, width)
}
