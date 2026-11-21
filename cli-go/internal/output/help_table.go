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
	Switch             bool
}

type HelpBlock struct {
	Title         string
	Lines         []string
	Rows          []HelpRow
	PreserveWords bool
}

func WriteHelpTable(out io.Writer, usage []string, intro string, sections []HelpBlock) error {
	style := helpStyle{}
	if file, ok := out.(*os.File); ok {
		if _, noColor := os.LookupEnv("NO_COLOR"); !noColor {
			color, restore := enableHelpColor(file)
			if restore != nil {
				defer restore()
			}
			if color {
				style = helpStyle{
					dim: "\x1b[2m", bold: "\x1b[1m", label: "\x1b[1;36m", toggle: "\x1b[1;32m",
					marker: "\x1b[31m", required: "\x1b[2;31m", yellow: "\x1b[1;33m",
				}
			}
		}
	}
	table := renderHelpTable(usage, intro, sections, helpTerminalWidth(out), style)
	_, err := io.WriteString(out, table)
	return err
}

type helpStyle struct {
	dim, bold, label, toggle, marker, required, yellow string
}

func paintHelp(text, color string) string {
	if color == "" || text == "" {
		return text
	}
	return color + text + "\x1b[0m"
}

func renderHelpTable(usage []string, intro string, sections []HelpBlock, width int, style helpStyle) string {
	var text strings.Builder
	for index, line := range usage {
		prefix := "       "
		if index == 0 {
			prefix = paintHelp(" 用法：", style.yellow)
		}
		const usageIndent = 7
		for _, wrapped := range strings.Split(wrapHelpText(line, max(2, width-usageIndent), true), "\n") {
			text.WriteString(prefix + paintHelp(wrapped, style.bold) + "\n")
			prefix = strings.Repeat(" ", usageIndent)
		}
	}
	if intro != "" {
		text.WriteByte('\n')
		for _, line := range strings.Split(wrapHelpText(intro, max(2, width-1), false), "\n") {
			text.WriteString(" " + line + "\n")
		}
		text.WriteByte('\n')
	}
	for _, section := range sections {
		if len(section.Rows)+len(section.Lines) == 0 {
			continue
		}
		panel := helpPanel{
			text: &text, style: style,
			contentWidth: max(width-4, cells.StringWidth(section.Title)+2, 6),
		}
		panel.write(section)
	}
	return text.String()
}

type helpPanel struct {
	text                                  *strings.Builder
	contentWidth, labelWidth, markerWidth int
	style                                 helpStyle
}

func (p *helpPanel) write(section HelpBlock) {
	for _, row := range section.Rows {
		p.labelWidth = max(p.labelWidth, cells.StringWidth(row.Label))
		if row.Required {
			p.markerWidth = 2
		}
	}
	top := "╭─ " + section.Title + " " + strings.Repeat("─", p.contentWidth-cells.StringWidth(section.Title)-1) + "╮"
	p.text.WriteString(paintHelp(top, p.style.dim) + "\n")
	for _, line := range section.Lines {
		for _, wrapped := range strings.Split(wrapHelpText(line, p.contentWidth, section.PreserveWords), "\n") {
			p.line(wrapped, cells.StringWidth(wrapped))
		}
	}
	for _, row := range section.Rows {
		p.row(row)
	}
	bottom := "╰" + strings.Repeat("─", p.contentWidth+2) + "╯"
	p.text.WriteString(paintHelp(bottom, p.style.dim) + "\n")
}

func (p *helpPanel) line(content string, width int) {
	border := paintHelp("│", p.style.dim)
	fmt.Fprintf(p.text, "%s %s%s %s\n", border, content, strings.Repeat(" ", p.contentWidth-width), border)
}

func (p *helpPanel) row(row HelpRow) {
	prefix := strings.Repeat(" ", p.markerWidth)
	if row.Required {
		prefix = paintHelp("*", p.style.marker) + " "
	}
	labelColor := p.style.label
	if row.Switch {
		labelColor = p.style.toggle
	}
	const gap = 2
	keyWidth := p.markerWidth + p.labelWidth + gap
	descriptionWidth := p.contentWidth - keyWidth
	if descriptionWidth < 18 {
		labelLines := strings.Split(wrapHelpText(row.Label, p.contentWidth-p.markerWidth, true), "\n")
		inValue := false
		for _, line := range labelLines {
			p.line(prefix+p.style.paintLabel(line, labelColor, inValue), p.markerWidth+cells.StringWidth(line))
			inValue = inValue || strings.Contains(line, "<")
			prefix = strings.Repeat(" ", p.markerWidth)
		}
		for _, line := range strings.Split(wrapHelpDescription(row.Description, p.contentWidth-gap), "\n") {
			p.line(strings.Repeat(" ", gap)+p.style.paintDescription(line), gap+cells.StringWidth(line))
		}
		return
	}
	label := prefix + p.style.paintLabel(row.Label, labelColor, false) + strings.Repeat(" ", keyWidth-p.markerWidth-cells.StringWidth(row.Label))
	for _, line := range strings.Split(wrapHelpDescription(row.Description, descriptionWidth), "\n") {
		p.line(label+p.style.paintDescription(line), keyWidth+cells.StringWidth(line))
		label = strings.Repeat(" ", keyWidth)
	}
}

func (s helpStyle) paintLabel(line, color string, inValue bool) string {
	if inValue {
		return paintHelp(line, s.yellow)
	}
	if option, value, found := strings.Cut(line, "<"); found {
		name := strings.TrimRight(option, " ")
		return paintHelp(name, color) + option[len(name):] + paintHelp("<"+value, s.yellow)
	}
	return paintHelp(line, color)
}

func (s helpStyle) paintDescription(line string) string {
	if body, found := strings.CutSuffix(line, "（必填）"); found {
		return body + paintHelp("（必填）", s.required)
	}
	if body, value, found := strings.Cut(line, "默认"); found {
		return body + paintHelp("默认"+value, s.dim)
	}
	return line
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
			if cells.StringWidth(label) > width {
				return wrapHelpText(description, width, false)
			}
			if cells.StringWidth(lastLine+label) > width {
				body += "\n"
			}
			return body + label
		}
	}
	return wrapHelpText(description, width, false)
}
