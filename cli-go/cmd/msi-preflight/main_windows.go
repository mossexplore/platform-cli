// The MSI runs this helper with the installing user's permissions.
package main

import (
	"errors"
	"fmt"
	"os"
	"strconv"

	"golang.org/x/sys/windows"
)

func main() {
	level := 0
	var err error
	switch {
	case len(os.Args) == 6 && os.Args[1] == "prepare":
		level, _ = strconv.Atoi(os.Args[4])
		err = preparePathSwitch(os.Args[2], os.Args[3], os.Args[5] == "1")
	case len(os.Args) == 4 && os.Args[1] == "apply":
		err = applyPathSwitch(os.Args[2], os.Args[3])
	case len(os.Args) == 3 && os.Args[1] == "rollback":
		err = restorePath(os.Args[2])
	case len(os.Args) == 3 && os.Args[1] == "commit":
		err = removePathJournal(os.Args[2])
	case len(os.Args) == 4 && os.Args[1] == "install-agent":
		if err := manageAgentResources(os.Args[2], true); err != nil {
			fmt.Fprintln(os.Stderr, err)
			uiLevel, _ := strconv.Atoi(os.Args[3])
			if uiLevel >= 4 {
				showMessage("Skill 未安装成功，请手动安装。CLI 已安装，可继续使用。", windows.MB_ICONWARNING)
			}
			os.Exit(1)
		}
	case len(os.Args) == 3 && os.Args[1] == "remove-agent":
		err = manageAgentResources(os.Args[2], false)
	default:
		err = errors.New("Invalid MSI helper arguments.")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		if level >= 4 {
			showMessage(err.Error(), windows.MB_ICONERROR)
		}
		os.Exit(1)
	}
}

func showMessage(message string, icon uint32) {
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI")
	_, _ = windows.MessageBox(0, content, title, icon|windows.MB_SETFOREGROUND)
}
