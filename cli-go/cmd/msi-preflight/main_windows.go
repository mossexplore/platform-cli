// The MSI runs this helper with the installing user's permissions.
package main

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
)

func main() {
	level := 0
	var err error
	switch {
	case len(os.Args) == 7 && os.Args[1] == "prepare":
		level, _ = strconv.Atoi(os.Args[4])
		err = preparePathSwitch(os.Args[2], os.Args[3], level >= 4, os.Args[5] == "1", os.Args[6] == "1")
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
		if level >= 4 && !errors.Is(err, errDeclined) {
			messageBox(err.Error(), 0x10) // MB_ICONERROR
		}
		os.Exit(1)
	}
}

var errDeclined = errors.New("The user declined to remove the previous ml PATH entry.")

func confirmRemoval(entries []string) bool {
	message := "Windows 用户 PATH 中已有旧版 WiseRec CLI 的入口：\n\n" + strings.Join(entries, "\n") +
		"\n\n是否移除这些 PATH 条目并继续安装？旧版程序、配置和登录数据会保留。"
	const yesNo = 0x4 | 0x20 | 0x100       // MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2
	return messageBox(message, yesNo) == 6 // IDYES
}

func messageBox(message string, flags uintptr) uintptr {
	box := windows.NewLazySystemDLL("user32.dll").NewProc("MessageBoxW")
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return 0
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI")
	const setForeground = 0x10000
	result, _, _ := box.Call(0, uintptr(unsafe.Pointer(content)), uintptr(unsafe.Pointer(title)), flags|setForeground)
	return result
}
