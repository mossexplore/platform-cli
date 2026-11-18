//go:build !windows

package command

import (
	"os"
	"os/exec"
	"strconv"
	"strings"
)

func parentShell() string {
	value, err := exec.Command("/bin/ps", "-p", strconv.Itoa(os.Getppid()), "-o", "comm=").Output()
	if err != nil {
		return ""
	}
	return strings.TrimPrefix(strings.TrimSpace(string(value)), "-")
}
