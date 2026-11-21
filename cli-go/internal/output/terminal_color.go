package output

import (
	"io"
	"os"
)

const (
	boldCyan  = "\x1b[1;36m"
	boldGreen = "\x1b[1;32m"
)

func terminalColor(out io.Writer) (bool, func()) {
	if file, ok := out.(*os.File); ok && os.Getenv("NO_COLOR") == "" {
		return enableTerminalColor(file)
	}
	return false, nil
}

func paintANSI(text, color string) string {
	if color == "" || text == "" {
		return text
	}
	return color + text + "\x1b[0m"
}
