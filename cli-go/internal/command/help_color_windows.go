package command

import (
	"os"

	"golang.org/x/sys/windows"
)

func enableHelpColor(file *os.File) (bool, func()) {
	handle := windows.Handle(file.Fd())
	var mode uint32
	if windows.GetConsoleMode(handle, &mode) != nil {
		return false, nil
	}
	if mode&windows.ENABLE_VIRTUAL_TERMINAL_PROCESSING != 0 {
		return true, nil
	}
	if windows.SetConsoleMode(handle, mode|windows.ENABLE_VIRTUAL_TERMINAL_PROCESSING) != nil {
		return false, nil
	}
	return true, func() { _ = windows.SetConsoleMode(handle, mode) }
}
