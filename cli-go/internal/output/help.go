package output

import (
	"io"
	"os"
	"strconv"
)

func helpTerminalWidth(out io.Writer) int {
	if width, err := strconv.Atoi(os.Getenv("TERMINAL_WIDTH")); err == nil && width > 0 {
		return width
	}
	return terminalWidth(out)
}
