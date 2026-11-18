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
	default:
		err = errors.New("Invalid MSI PATH action arguments.")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		if level >= 4 {
			showError(err.Error())
		}
		os.Exit(1)
	}
}

func showError(message string) {
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI")
	_, _ = windows.MessageBox(0, content, title, windows.MB_ICONERROR|windows.MB_SETFOREGROUND)
}
