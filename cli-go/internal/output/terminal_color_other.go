//go:build !windows

package output

import (
	"os"

	"golang.org/x/term"
)

func enableTerminalColor(file *os.File) (bool, func()) {
	return os.Getenv("TERM") != "dumb" && term.IsTerminal(int(file.Fd())), nil
}
