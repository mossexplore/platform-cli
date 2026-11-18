//go:build !windows

package command

import (
	"os"

	"golang.org/x/term"
)

func enableHelpColor(file *os.File) (bool, func()) {
	return os.Getenv("TERM") != "dumb" && term.IsTerminal(int(file.Fd())), nil
}
