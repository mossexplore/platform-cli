package command

import (
	"os"

	"golang.org/x/sys/windows"
)

func parentShell() string {
	process, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, uint32(os.Getppid()))
	if err != nil {
		return ""
	}
	defer windows.CloseHandle(process)
	var path [32768]uint16
	size := uint32(len(path))
	if windows.QueryFullProcessImageName(process, 0, &path[0], &size) != nil {
		return ""
	}
	return windows.UTF16ToString(path[:size])
}
