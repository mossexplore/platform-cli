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

func manageAgentResources(openCode string, install bool) error {
	home, err := os.UserHomeDir()
	if err != nil {
		return err
	}
	if !filepath.IsAbs(openCode) {
		return errors.New("OpenCode 配置目录无效")
	}
	archive, err := zip.NewReader(bytes.NewReader(agentArchive), int64(len(agentArchive)))
	if err != nil {
		return err
	}
	agents, cac := filepath.Join(home, ".agents"), filepath.Join(home, ".cac")
	var failures error
	for _, resource := range archive.File {
		if !fs.ValidPath(resource.Name) || strings.Contains(resource.Name, `\`) || resource.FileInfo().IsDir() {
			return fmt.Errorf("无效的 Skill 资源路径 %q", resource.Name)
		}
		roots := []string{agents, cac}
		if strings.HasPrefix(resource.Name, "commands/") {
			roots[0] = openCode
		}
		for _, root := range roots {
			path := filepath.Join(root, filepath.FromSlash(resource.Name))
			if install {
				err = installAgentFile(resource, path)
			} else {
				err = removeAgentFile(path)
				// Only remove empty directories under the managed Skill, never the shared roots.
				skillDir := filepath.Join(root, "skills", "wiserec-platform")
				for dir := filepath.Dir(path); dir == skillDir || strings.HasPrefix(dir, skillDir+`\`); dir = filepath.Dir(dir) {
					_ = os.Remove(dir)
				}
			}
			failures = errors.Join(failures, err)
		}
	}
	if !install || failures != nil {
		return failures
	}
	for _, root := range []string{agents, cac, openCode} {
		failures = errors.Join(failures,
			removeAgentFile(filepath.Join(root, "commands", "ml-lab.md")),
			removeAgentFile(filepath.Join(root, "skills", "wiserec-platform-detailed", "SKILL.md")))
	}
	return errors.Join(failures, removeAgentFile(filepath.Join(openCode, "skills", "wiserec-platform", "SKILL.md")))
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
		return fmt.Errorf("Skill 文件路径被目录占用：%s", path)
	}
	return os.Remove(path)
}
