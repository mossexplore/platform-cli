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
	width = max(width, 24)
	contentWidth := width - 4
	border := func(left, title, right string) {
		label := ""
		if title != "" {
			label = "  " + title + " "
		}
		line := left + label + strings.Repeat("─", width-2-cells.StringWidth(label)) + right
		text.WriteString(paintHelp(line, style.dim) + "\n")
	}
	panel := helpPanel{text: &text, style: style, contentWidth: contentWidth}
	border("╭", "用途", "╮")
	for index, line := range usage {
		const indent = 6
		prefix := strings.Repeat(" ", indent)
		if index == 0 {
			prefix = paintHelp("用法：", style.yellow)
		}
		for _, wrapped := range strings.Split(wrapHelpText(line, contentWidth-indent, true), "\n") {
			panel.line(prefix+paintHelp(wrapped, style.bold), indent+cells.StringWidth(wrapped))
			prefix = strings.Repeat(" ", indent)
		}
	}
	if intro != "" {
		if len(usage) > 0 {
			panel.line("", 0)
		}
		panel.lines(strings.Split(intro, "\n"), false)
	}
	for _, section := range sections {
		if len(section.Rows)+len(section.Lines) == 0 {
			continue
		}
		if section.Title == "" {
			panel.line("", 0)
		} else {
			border("├", section.Title, "┤")
		}
		block := helpPanel{text: &text, style: style, contentWidth: contentWidth}
		block.write(section)
	}
	border("╰", "", "╯")
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
	p.lines(section.Lines, section.PreserveWords)
	for _, row := range section.Rows {
		p.row(row)
	}
}

func (p *helpPanel) lines(lines []string, preserveWords bool) {
	for _, line := range lines {
		for _, wrapped := range strings.Split(wrapHelpText(line, p.contentWidth, preserveWords), "\n") {
			p.line(wrapped, cells.StringWidth(wrapped))
		}
	}
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
			inValue = (inValue || strings.Contains(line, "<")) && !strings.Contains(line, ">")
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
