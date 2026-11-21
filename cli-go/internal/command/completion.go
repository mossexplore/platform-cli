package command

import (
	"bytes"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/spf13/cobra"
)

func addCompletionOptions(root *cobra.Command) {
	install := root.Flags().Bool("install-completion", false, "为当前用户的 Shell 安装命令补全")
	show := root.Flags().Bool("show-completion", false, "输出当前 Shell 的补全脚本")
	root.Args = cobra.NoArgs
	root.RunE = func(cmd *cobra.Command, _ []string) error {
		if !*install && !*show {
			return cmd.Help()
		}
		shell := currentCompletionShell()
		if !*install {
			return writeCompletion(cmd, shell, cmd.OutOrStdout())
		}
		var script bytes.Buffer
		if err := writeCompletion(cmd, shell, &script); err != nil {
			return err
		}
		path, err := installCompletion(cmd.Context(), shell, script.Bytes())
		if err != nil {
			return err
		}
		_, err = fmt.Fprintf(cmd.OutOrStdout(), "%s completion installed in %s\nCompletion will take effect once you restart the terminal\n", shell, path)
		return err
	}
}

func currentCompletionShell() string {
	for _, candidate := range []string{parentShell(), os.Getenv("SHELL")} {
		switch shell := strings.TrimSuffix(strings.ToLower(filepath.Base(candidate)), ".exe"); shell {
		case "bash", "zsh", "fish", "powershell", "pwsh":
			return shell
		}
	}
	return ""
}

func writeCompletion(root *cobra.Command, shell string, out io.Writer) error {
	switch shell {
	case "bash":
		return root.GenBashCompletionV2(out, true)
	case "zsh":
		return root.GenZshCompletion(out)
	case "fish":
		return root.GenFishCompletion(out, true)
	case "powershell", "pwsh":
		return root.GenPowerShellCompletionWithDesc(out)
	default:
		return errors.New("无法识别支持的 shell，请在 Bash、Zsh、Fish 或 PowerShell 中运行")
	}
}

func installCompletion(ctx context.Context, shell string, script []byte) (string, error) {
	home, err := os.UserHomeDir()
	if err != nil {
		return "", err
	}
	switch shell {
	case "fish":
		// Fish uses XDG_CONFIG_HOME on macOS too.
		config := os.Getenv("XDG_CONFIG_HOME")
		if !filepath.IsAbs(config) {
			config = filepath.Join(home, ".config")
		}
		path := filepath.Join(config, "fish", "completions", "ml.fish")
		return path, localstate.WritePrivate(path, script)
	case "powershell", "pwsh":
		config, err := os.UserConfigDir()
		if err != nil {
			return "", err
		}
		path := filepath.Join(config, "ml-go-preview", "completion.ps1")
		if err := localstate.WritePrivate(path, script); err != nil {
			return "", err
		}
		return installPowerShellCompletion(ctx, shell, path)
	case "zsh":
		path := filepath.Join(home, ".ml-go", "zsh", "_ml")
		if err := localstate.WritePrivate(path, script); err != nil {
			return "", err
		}
		// Autoload the Cobra script as a completion function.
		return path, appendShellLine(filepath.Join(home, ".zshrc"), `fpath=("$HOME/.ml-go/zsh" "${fpath[@]}"); autoload -Uz compinit; compinit`)
	default:
		path := filepath.Join(home, ".ml-go", "completion.bash")
		if err := localstate.WritePrivate(path, script); err != nil {
			return "", err
		}
		return path, appendShellLine(filepath.Join(home, ".bashrc"), `. "$HOME/.ml-go/completion.bash"`)
	}
}

func appendShellLine(path, entry string) error {
	contents, err := os.ReadFile(path)
	if err != nil && !os.IsNotExist(err) {
		return err
	}
	for _, line := range strings.Split(string(contents), "\n") {
		if strings.TrimSpace(line) == entry {
			return nil
		}
	}
	file, err := os.OpenFile(path, os.O_WRONLY|os.O_CREATE|os.O_APPEND, 0600)
	if err != nil {
		return err
	}
	_, writeErr := fmt.Fprintln(file, "\n"+entry)
	return errors.Join(writeErr, file.Close())
}

func installPowerShellCompletion(ctx context.Context, shell, path string) (string, error) {
	// Let PowerShell resolve its own profile path and preserve its encoding.
	process := exec.CommandContext(ctx, shell, "-NoProfile", "-NonInteractive", "-Command", `
$ErrorActionPreference = 'Stop'
$line = ". '" + $env:ML_GO_COMPLETION_PATH.Replace("'", "''") + "'"
if (!(Test-Path -LiteralPath $PROFILE)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $PROFILE) | Out-Null
}
if (!(Test-Path -LiteralPath $PROFILE) -or $line -notin (Get-Content -LiteralPath $PROFILE)) {
    Add-Content -LiteralPath $PROFILE -Value ([Environment]::NewLine + $line)
}
`)
	process.Env = append(os.Environ(), "ML_GO_COMPLETION_PATH="+path)
	if details, err := process.CombinedOutput(); err != nil {
		return "", fmt.Errorf("无法更新 PowerShell 用户配置: %w %s", err, strings.TrimSpace(string(details)))
	}
	return path, nil
}
