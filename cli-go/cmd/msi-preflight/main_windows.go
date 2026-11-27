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
	case len(os.Args) == 3 && os.Args[1] == "install-skills":
		err = runOptionalInstall("Skill 安装失败", os.Args[2], manageSkills)
	case len(os.Args) == 3 && os.Args[1] == "install-shortcuts":
		err = runOptionalInstall("/ml 命令注册失败", os.Args[2], manageShortcuts)
	case len(os.Args) == 2 && os.Args[1] == "remove-skills":
		err = runAgentAction(manageSkills, false)
	case len(os.Args) == 2 && os.Args[1] == "remove-shortcuts":
		err = runAgentAction(manageShortcuts, false)
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

func runAgentAction(manage func(string, bool) error, install bool) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	return manage(home, install)
}

func runOptionalInstall(label, ui string, manage func(string, bool) error) error {
	err := runAgentAction(manage, true)
	if err == nil {
		return nil
	}
	err = fmt.Errorf("%s：%w", label, err)
	if level, _ := strconv.Atoi(ui); level >= 4 {
		showMessage(fmt.Sprintf("%v\n\nCLI 已安装，可继续使用。", err), windows.MB_ICONWARNING)
	}
	return err
}

func showMessage(message string, icon uint32) {
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI")
	_, _ = windows.MessageBox(0, content, title, icon|windows.MB_SETFOREGROUND)
}
