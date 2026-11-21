package output

import (
	"io"
	"math"
	"os"
	"regexp"
	"strconv"
	"strings"
	"unicode/utf8"

	"github.com/mattn/go-runewidth"
)

// Rich treats East Asian ambiguous characters, including panel borders, as one cell.
var helpCells = runewidth.Condition{StrictEmojiNeutral: true}

type HelpRow struct {
	Label, Short, Value string
	Description         []string
	Required            bool
}

type helpStyle struct {
	dim, bold, label, toggle, marker, required, yellow, usage string
}

func WriteHelp(out io.Writer, path, syntax, intro string, arguments, options, commands []HelpRow) error {
	style := helpStyle{}
	color, restore := terminalColor(out)
	if restore != nil {
		defer restore()
	}
	if color {
		style = helpStyle{
			dim: "\x1b[2m", bold: "\x1b[1m", label: boldCyan, toggle: boldGreen,
			marker: "\x1b[31m", required: "\x1b[2;31m", yellow: "\x1b[1;33m", usage: "\x1b[1;33m",
		}
	}
	terminal := terminalWidth(out)
	width := terminal
	if explicit, err := strconv.Atoi(os.Getenv("TERMINAL_WIDTH")); err == nil && explicit > 0 {
		width = explicit
	}
	_, err := io.WriteString(out, renderHelp(path, syntax, intro, arguments, options, commands, width, terminal, style))
	return err
}

type helpText struct {
	strings.Builder
	width int
	style helpStyle
}

func renderHelp(path, syntax, intro string, arguments, options, commands []HelpRow, width, terminal int, style helpStyle) string {
	h := helpText{width: max(width, 24), style: style}
	h.line("", 0)
	for i, line := range wrapHelp(helpUsage(path, syntax, terminal), h.width-2, true) {
		colored := paintANSI(line, style.bold)
		if i == 0 {
			colored = paintANSI("Usage: ", style.usage) + paintANSI(strings.TrimPrefix(line, "Usage: "), style.bold)
		}
		h.line(" "+colored, helpCells.StringWidth(line)+1)
	}
	h.line("", 0)
	if intro != "" {
		for _, line := range wrapHelp(intro, h.width-2, true) {
			h.line(" "+line, helpCells.StringWidth(line)+1)
		}
		h.line("", 0)
	}
	h.panel("Arguments", arguments)
	h.panel("Options", options)
	h.panel("Commands", commands)
	h.WriteByte('\n')
	return h.String()
}

func (h *helpText) line(line string, width int) {
	h.WriteString(line)
	h.WriteString(strings.Repeat(" ", max(0, h.width-width)))
	h.WriteByte('\n')
}

func (h *helpText) panel(title string, rows []HelpRow) {
	if len(rows) == 0 {
		return
	}
	inner := h.width - 4
	commands := title == "Commands"
	columns := make([][]helpCell, 0, len(rows))
	hasMarker := false
	for _, row := range rows {
		hasMarker = hasMarker || row.Required
	}
	for _, row := range rows {
		columns = append(columns, h.cells(row, title, hasMarker))
	}
	widths := helpColumnWidths(columns, inner, commands)
	top := "╭─ " + title + " "
	h.WriteString(paintANSI(top+strings.Repeat("─", h.width-1-helpCells.StringWidth(top))+"╮", h.style.dim) + "\n")
	border := paintANSI("│", h.style.dim)
	for _, row := range columns {
		wrapped := make([][]string, len(row))
		height := 1
		for i, cell := range row {
			left, right := cellPadding(i, len(row))
			width := max(1, widths[i]-left-right)
			wrapped[i] = cell.wrap(width, h.style)
			height = max(height, len(wrapped[i]))
		}
		for line := range height {
			h.WriteString(border + " ")
			for i, lines := range wrapped {
				part := ""
				if line < len(lines) {
					part = lines[line]
				}
				left, _ := cellPadding(i, len(row))
				h.WriteString(strings.Repeat(" ", left) + part)
				h.WriteString(strings.Repeat(" ", max(0, widths[i]-left-helpLineWidth(part))))
			}
			h.WriteString(" " + border + "\n")
		}
	}
	h.WriteString(paintANSI("╰"+strings.Repeat("─", h.width-2)+"╯", h.style.dim) + "\n")
}

type helpCell struct {
	text, color string
	fold        bool
	description []string
}

func (h *helpText) cells(row HelpRow, title string, marker bool) []helpCell {
	commands := title == "Commands"
	label := helpCell{text: row.Label, color: h.style.label}
	description := helpCell{description: row.Description}
	if commands {
		return []helpCell{label, description}
	}
	short := helpCell{text: row.Short, color: h.style.toggle}
	if title == "Arguments" {
		label, short = helpCell{}, helpCell{text: row.Label}
	}
	columns := []helpCell{label, short, {}, {}, {text: row.Value, color: h.style.yellow, fold: true}, description}
	if marker {
		star := helpCell{color: h.style.marker}
		if row.Required {
			star.text = "*"
		}
		columns = append([]helpCell{star}, columns...)
	}
	return columns
}

func cellPadding(index, count int) (left, right int) {
	if index > 0 {
		left = 1
	}
	if index < count-1 {
		right = 1
	}
	return
}

func helpColumnWidths(rows [][]helpCell, width int, commands bool) []int {
	count := len(rows[0])
	widths := make([]int, count)
	for _, row := range rows {
		for i, cell := range row {
			left, right := cellPadding(i, count)
			widths[i] = max(widths[i], min(width, helpCells.StringWidth(cell.text)+left+right))
		}
	}
	// Like Typer's Rich tables, the description column fills the available
	// space. When it reaches the width of its neighbors, they wrap as well.
	if commands {
		widths[0] = min(widths[0], width-2)
		widths[1] = width - widths[0]
		return widths
	}
	widths[count-1] = width
	total := sumHelpWidths(widths)
	for total > width {
		largest, second := 0, 0
		for _, current := range widths {
			if current > largest {
				largest, second = current, largest
			} else if current < largest {
				second = max(second, current)
			}
		}
		equal := 0
		for _, current := range widths {
			if current == largest {
				equal++
			}
		}
		excess := total - width
		for i, current := range widths {
			if current == largest {
				reduce := min(current-3, largest-second, int(math.RoundToEven(float64(excess)/float64(equal))))
				widths[i] -= reduce
				excess -= reduce
				equal--
			}
		}
		next := sumHelpWidths(widths)
		if next == total {
			break
		}
		total = next
	}
	return widths
}

func sumHelpWidths(widths []int) int {
	total := 0
	for _, width := range widths {
		total += width
	}
	return total
}

func (c helpCell) wrap(width int, style helpStyle) []string {
	if c.description == nil {
		lines := wrapHelp(c.text, width, c.fold)
		for i, line := range lines {
			lines[i] = paintANSI(line, c.color)
		}
		return lines
	}

	var lines []string
	row := ""
	rowWidth := 0
	for _, part := range c.description {
		color := ""
		switch {
		case part == "[required]":
			color = style.required
		case strings.HasPrefix(part, "[default: "):
			color = style.dim
		case strings.HasPrefix(part, "[env var: "):
			color = style.yellow
		}
		partWidth := helpCells.StringWidth(part)
		if rowWidth > 0 && rowWidth+1+partWidth <= width {
			row += " " + paintANSI(part, color)
			rowWidth += 1 + partWidth
			continue
		}
		if rowWidth > 0 {
			lines = append(lines, row)
		}
		wrapped := wrapHelp(part, width, false)
		for _, line := range wrapped[:len(wrapped)-1] {
			lines = append(lines, paintANSI(line, color))
		}
		last := wrapped[len(wrapped)-1]
		row = paintANSI(last, color)
		rowWidth = helpCells.StringWidth(last)
		// Rich puts a wrapped description and its annotations in separate rows.
		if len(wrapped) > 1 {
			lines = append(lines, row)
			row, rowWidth = "", 0
		}
	}
	if rowWidth > 0 {
		lines = append(lines, row)
	}
	return lines
}

var helpWords = regexp.MustCompile(`\s*\S+\s*`)
var helpEscape = regexp.MustCompile("\\x1b\\[[0-9;]*m")

func helpLineWidth(line string) int {
	return helpCells.StringWidth(helpEscape.ReplaceAllString(line, ""))
}

func helpUsage(path, syntax string, terminal int) string {
	width := max(50, min(terminal, 80)-2)
	prefix := "Usage: " + path + " "
	indent := len(prefix)
	first := prefix
	if width < indent+20 {
		indent = len("Usage: ") + 4
		first = prefix + "\n" + strings.Repeat(" ", indent)
	}
	lines := wrapHelp(syntax, width-indent, true)
	return first + strings.Join(lines, "\n"+strings.Repeat(" ", indent))
}

func wrapHelp(text string, width int, fold bool) []string {
	var lines []string
	for _, paragraph := range strings.Split(text, "\n") {
		current, used := "", 0
		for _, word := range helpWords.FindAllString(paragraph, -1) {
			visible := helpCells.StringWidth(strings.TrimRight(word, " \t"))
			if used+visible > width && current != "" {
				lines = append(lines, helpFit(current, width, fold))
				current, used = "", 0
			}
			if visible > width && fold {
				pieces := strings.Split(helpCells.Wrap(word, max(2, width)), "\n")
				lines = append(lines, pieces[:len(pieces)-1]...)
				word = pieces[len(pieces)-1]
			}
			current += word
			used += helpCells.StringWidth(word)
		}
		lines = append(lines, helpFit(current, width, fold))
	}
	return lines
}

func helpFit(text string, width int, fold bool) string {
	trimmed := strings.TrimRight(text, " \t")
	if excess := utf8.RuneCountInString(text) - width; excess > 0 {
		text = text[:len(text)-min(excess, len(text)-len(trimmed))]
	}
	if helpCells.StringWidth(text) <= width {
		return strings.TrimRight(text, " \t")
	}
	if fold {
		return helpCells.Truncate(text, width, "")
	}
	head := helpCells.Truncate(text, width-1, "")
	return head + strings.Repeat(" ", max(0, width-1-helpCells.StringWidth(head))) + "…"
}
