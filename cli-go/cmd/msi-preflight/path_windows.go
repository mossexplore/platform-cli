package main

import (
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"slices"
	"strings"

	"golang.org/x/sys/windows/registry"
)

const machineEnvironment = `SYSTEM\CurrentControlSet\Control\Session Manager\Environment`

type pathValue struct {
	Text string
	Kind uint32
}

func preparePathSwitch(installDir, journal string, interactive, approved, rollbackDisabled bool) error {
	if err := removePathJournal(journal); err != nil {
		return err
	}
	machine, err := readPath(registry.LOCAL_MACHINE, machineEnvironment)
	if err != nil {
		return err
	}
	for _, entry := range strings.Split(machine.Text, ";") {
		conflict, err := machine.launcher(entry, installDir)
		if err != nil {
			return err
		}
		if conflict != "" {
			return fmt.Errorf("系统 PATH 中已有 ml：\n%s\n\n请由管理员调整系统 PATH，再运行安装。", conflict)
		}
	}

	user, err := readUserPath()
	if err != nil {
		return err
	}
	_, conflicts, err := user.removeLegacyLaunchers(installDir)
	if err != nil || len(conflicts) == 0 {
		return err
	}
	if rollbackDisabled {
		return errors.New("Windows Installer 回滚已禁用。请先手动清理旧版 ml 的用户 PATH，再运行安装。")
	}
	if !approved {
		if !interactive {
			return errors.New("发现旧版 ml。静默安装需显式传入 REMOVEOLDMLPATH=1。")
		}
		if !confirmRemoval(conflicts) {
			return errDeclined
		}
	}

	return savePathJournal(journal, pathJournal{Approved: conflicts})
}

func applyPathSwitch(installDir, filename string) error {
	journal, err := readPathJournal(filename)
	if err != nil {
		return err
	}
	current, err := readUserPath()
	if err != nil {
		return err
	}
	updated, conflicts, err := current.removeLegacyLaunchers(installDir)
	if err != nil || len(conflicts) == 0 {
		return err
	}
	// Recheck the directories authorized before the MSI added its own PATH entry.
	if !slices.Equal(conflicts, journal.Approved) {
		return errors.New("用户 PATH 在安装过程中发生变化。请重新运行安装。")
	}
	journal.Change = &pathChange{Before: current, After: updated}
	if err := savePathJournal(filename, journal); err != nil {
		return err
	}
	return writeUserPath(updated)
}

func (value pathValue) removeLegacyLaunchers(installDir string) (pathValue, []string, error) {
	var kept, removed []string
	for _, entry := range strings.Split(value.Text, ";") {
		conflict, err := value.launcher(entry, installDir)
		if err != nil {
			return value, nil, err
		}
		if conflict == "" {
			kept = append(kept, entry)
			continue
		}
		if !isPythonLauncher(conflict) {
			return value, nil, fmt.Errorf("用户 PATH 中有其他程序提供 ml：\n%s\n\n请核对该目录后手动调整 PATH。", conflict)
		}
		removed = append(removed, filepath.Dir(conflict))
	}
	value.Text = strings.Join(kept, ";")
	return value, removed, nil
}

func (value pathValue) launcher(entry, installDir string) (string, error) {
	dir := strings.Trim(strings.TrimSpace(entry), `"`)
	if value.Kind == registry.EXPAND_SZ {
		expanded, err := registry.ExpandString(dir)
		if err != nil {
			return "", err
		}
		dir = expanded
	}
	if !filepath.IsAbs(dir) || strings.EqualFold(filepath.Clean(dir), filepath.Clean(installDir)) {
		return "", nil
	}
	for _, name := range []string{"ml.com", "ml.exe", "ml.bat", "ml.cmd"} {
		candidate := filepath.Join(dir, name)
		info, err := os.Stat(candidate)
		if err == nil && !info.IsDir() {
			return candidate, nil
		}
	}
	return "", nil
}

func isPythonLauncher(path string) bool {
	dir := filepath.Dir(path)
	if !strings.EqualFold(filepath.Base(path), "ml.cmd") || !strings.EqualFold(filepath.Base(dir), "bin") {
		return false
	}
	defaultBin := filepath.Join(os.Getenv("LOCALAPPDATA"), "Programs", "WiseRecCLI", "bin")
	if strings.EqualFold(dir, defaultBin) {
		return true
	}

	// Custom Python installation directories use the same dedicated launcher.
	file, err := os.Open(path)
	if err != nil {
		return false
	}
	defer file.Close()
	data, err := io.ReadAll(io.LimitReader(file, 513))
	if err != nil || len(data) > 512 {
		return false
	}
	launcher := strings.TrimSpace(strings.ReplaceAll(string(data), "\r\n", "\n"))
	return strings.EqualFold(launcher, "@echo off\n"+`"%~dp0..\venv\Scripts\ml.exe" %*`)
}

func readUserPath() (pathValue, error) {
	return readPath(registry.CURRENT_USER, "Environment")
}

func readPath(root registry.Key, subkey string) (pathValue, error) {
	key, err := registry.OpenKey(root, subkey, registry.QUERY_VALUE)
	if errors.Is(err, registry.ErrNotExist) {
		return pathValue{}, nil
	}
	if err != nil {
		return pathValue{}, err
	}
	defer key.Close()
	value, kind, err := key.GetStringValue("Path")
	if errors.Is(err, registry.ErrNotExist) {
		return pathValue{}, nil
	}
	return pathValue{Text: value, Kind: kind}, err
}

func writeUserPath(value pathValue) error {
	key, err := registry.OpenKey(registry.CURRENT_USER, "Environment", registry.SET_VALUE)
	if err != nil {
		return err
	}
	defer key.Close()
	if value.Kind == registry.EXPAND_SZ {
		return key.SetExpandStringValue("Path", value.Text)
	}
	return key.SetStringValue("Path", value.Text)
}
