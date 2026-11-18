package keepalive

import (
	"fmt"
	"os"
	"os/exec"
	"strings"
	"syscall"
)

func identity(pid int) string {
	if pid <= 0 {
		return ""
	}
	data, err := os.ReadFile(fmt.Sprintf("/proc/%d/stat", pid))
	if err != nil {
		return ""
	}
	_, raw, found := strings.Cut(string(data), ") ")
	if !found {
		return ""
	}
	values := strings.Fields(raw)
	if len(values) < 20 || values[0] == "Z" {
		return ""
	}
	return fmt.Sprintf("%d:%s", pid, values[19])
}
func detachProcess(cmd *exec.Cmd) { cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true} }
