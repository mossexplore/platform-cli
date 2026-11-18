package keepalive

import (
	"fmt"
	"os/exec"
	"syscall"

	"golang.org/x/sys/windows"
)

func identity(pid int) string {
	if pid <= 0 {
		return ""
	}
	h, err := windows.OpenProcess(windows.PROCESS_QUERY_LIMITED_INFORMATION, false, uint32(pid))
	if err != nil {
		return ""
	}
	defer windows.CloseHandle(h)
	var start, exit, kernel, user windows.Filetime
	var code uint32
	if windows.GetExitCodeProcess(h, &code) != nil || code != 259 ||
		windows.GetProcessTimes(h, &start, &exit, &kernel, &user) != nil {
		return ""
	}
	return fmt.Sprintf("%d:%d:%d", pid, start.HighDateTime, start.LowDateTime)
}
func detachProcess(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NO_WINDOW | windows.CREATE_NEW_PROCESS_GROUP, HideWindow: true}
}
