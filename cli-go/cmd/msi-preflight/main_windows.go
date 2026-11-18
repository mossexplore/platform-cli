// This executable is embedded in the MSI and runs before it makes changes.
package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"unsafe"

	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
)

func main() {
	if len(os.Args) != 3 {
		os.Exit(1)
	}
	conflict, err := findConflict(os.Args[1])
	if conflict == "" && err == nil {
		return
	}

	message := "Cannot check the Windows PATH. Check where.exe ml before running this installer again."
	if conflict != "" {
		message = "Another ml command is registered on PATH:\n" + conflict +
			"\n\nRemove that entry from PATH and rerun the installer. Keep the previous client's configuration and login files."
	}
	fmt.Fprintln(os.Stderr, message)
	level, _ := strconv.Atoi(os.Args[2])
	if level >= 4 {
		showMessage(message)
	}
	os.Exit(1)
}

func findConflict(installDir string) (string, error) {
	for _, location := range []struct {
		root registry.Key
		key  string
	}{
		{registry.LOCAL_MACHINE, `SYSTEM\CurrentControlSet\Control\Session Manager\Environment`},
		{registry.CURRENT_USER, "Environment"},
	} {
		path, err := readPath(location.root, location.key)
		if err != nil {
			return "", err
		}
		for _, entry := range strings.Split(path, ";") {
			dir := strings.Trim(strings.TrimSpace(entry), `"`)
			if dir == "" || strings.EqualFold(filepath.Clean(dir), filepath.Clean(installDir)) {
				continue
			}
			for _, name := range []string{"ml.com", "ml.exe", "ml.bat", "ml.cmd"} {
				candidate := filepath.Join(dir, name)
				info, err := os.Stat(candidate)
				if err == nil && !info.IsDir() {
					return candidate, nil
				}
			}
		}
	}
	return "", nil
}

func readPath(root registry.Key, subkey string) (string, error) {
	key, err := registry.OpenKey(root, subkey, registry.QUERY_VALUE)
	if errors.Is(err, registry.ErrNotExist) {
		return "", nil
	}
	if err != nil {
		return "", err
	}
	defer key.Close()
	value, kind, err := key.GetStringValue("Path")
	if errors.Is(err, registry.ErrNotExist) {
		return "", nil
	}
	if err == nil && kind == registry.EXPAND_SZ {
		return registry.ExpandString(value)
	}
	return value, err
}

func showMessage(message string) {
	box := windows.NewLazySystemDLL("user32.dll").NewProc("MessageBoxW")
	content, err := windows.UTF16PtrFromString(message)
	if err != nil {
		return
	}
	title, _ := windows.UTF16PtrFromString("WiseRec CLI (Go)")
	const mbIconError = 0x10
	_, _, _ = box.Call(0, uintptr(unsafe.Pointer(content)), uintptr(unsafe.Pointer(title)), mbIconError)
}
