package main

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"errors"
	"fmt"
	"io"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
)

//go:embed agent-resources.zip.in
var agentArchive []byte

func manageSkills(home string, install bool) error {
	agents, cac := filepath.Join(home, ".agents"), filepath.Join(home, ".cac")
	failures := manageAgentResources("skills/", []string{agents, cac}, install)
	if !install || failures != nil {
		return failures
	}
	for _, root := range []string{agents, cac, openCodeRoot(home)} {
		failures = errors.Join(failures,
			removeAgentFile(filepath.Join(root, "skills", "wiserec-platform-detailed", "SKILL.md")))
	}
	// The shared Skill supersedes the old entry in the default OpenCode directory.
	return errors.Join(failures,
		removeAgentFile(filepath.Join(openCodeRoot(home), "skills", "wiserec-platform", "SKILL.md")))
}

func manageShortcuts(home string, install bool) error {
	agents, cac, openCode := filepath.Join(home, ".agents"), filepath.Join(home, ".cac"), openCodeRoot(home)
	failures := manageAgentResources("commands/", []string{openCode, cac}, install)
	if !install || failures != nil {
		return failures
	}
	for _, root := range []string{agents, cac, openCode} {
		failures = errors.Join(failures, removeAgentFile(filepath.Join(root, "commands", "ml-lab.md")))
	}
	return failures
}

func openCodeRoot(home string) string {
	return filepath.Join(home, ".config", "opencode")
}

func manageAgentResources(prefix string, roots []string, install bool) error {
	archive, err := zip.NewReader(bytes.NewReader(agentArchive), int64(len(agentArchive)))
	if err != nil {
		return err
	}
	var failures error
	for _, resource := range archive.File {
		if !strings.HasPrefix(resource.Name, prefix) {
			continue
		}
		if !fs.ValidPath(resource.Name) || strings.Contains(resource.Name, `\`) || resource.FileInfo().IsDir() {
			failures = errors.Join(failures, fmt.Errorf("无效的安装资源路径 %q", resource.Name))
			continue
		}
		for _, root := range roots {
			path := filepath.Join(root, filepath.FromSlash(resource.Name))
			if install {
				if err := installAgentFile(resource, path); err != nil {
					failures = errors.Join(failures, fmt.Errorf("无法写入 %s：%w", filepath.Dir(path), err))
				}
				continue
			}
			failures = errors.Join(failures, removeAgentFile(path))
			// Only remove empty directories in the managed Skill, never the shared roots.
			skillDir := filepath.Join(root, "skills", "wiserec-platform")
			for dir := filepath.Dir(path); dir == skillDir || strings.HasPrefix(dir, skillDir+`\`); dir = filepath.Dir(dir) {
				_ = os.Remove(dir)
			}
		}
	}
	return failures
}

func installAgentFile(resource *zip.File, target string) error {
	if err := os.MkdirAll(filepath.Dir(target), 0755); err != nil {
		return err
	}
	source, err := resource.Open()
	if err != nil {
		return err
	}
	defer source.Close()
	file, err := os.CreateTemp(filepath.Dir(target), ".wiserec-skill-*")
	if err != nil {
		return err
	}
	defer os.Remove(file.Name())
	_, writeErr := io.Copy(file, source)
	if err := errors.Join(writeErr, file.Close()); err != nil {
		return err
	}
	return os.Rename(file.Name(), target)
}

func removeAgentFile(path string) error {
	info, err := os.Lstat(path)
	if errors.Is(err, os.ErrNotExist) {
		return nil
	}
	if err != nil {
		return err
	}
	if info.IsDir() {
		return fmt.Errorf("文件路径被目录占用：%s", path)
	}
	return os.Remove(path)
}
