package keepalive

import (
	"fmt"
	"os/exec"
	"syscall"

	"golang.org/x/sys/unix"
)

func identity(pid int) string {
	if pid <= 0 {
		return ""
	}
	value, err := unix.SysctlKinfoProc("kern.proc.pid", pid)
	if err != nil || int(value.Proc.P_pid) != pid {
		return ""
	}
	return fmt.Sprintf("%d:%d:%d", pid, value.Proc.P_starttime.Sec, value.Proc.P_starttime.Usec)
}
func detachProcess(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }
