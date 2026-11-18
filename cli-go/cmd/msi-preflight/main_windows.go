// The MSI runs this helper with the installing user's permissions.
package main

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"unsafe"

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
	case len(os.Args) == 2 && os.Args[1] == "success":
		messageBox("WiseRec CLI 安装成功。\n\n请重新打开终端，运行 ml --version 验证。", 0x40) // MB_ICONINFORMATION
	default:
		err = errors.New("Invalid MSI PATH action arguments.")
	}
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		if level >= 4 {
			messageBox(err.Error(), 0x10) // MB_ICONERROR
		}
		os.Exit(1)
	}
}

func messageBox(message string, flags uintptr) {
	box := windows.NewLazySystemDLL("user32.dll").NewProc("MessageBoxW")
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI")
	const setForeground = 0x10000
	_, _, _ = box.Call(0, uintptr(unsafe.Pointer(content)), uintptr(unsafe.Pointer(title)), flags|setForeground)
}
