package updater

import (
	"bufio"
	"context"
	_ "embed"
	"encoding/base64"
	"encoding/binary"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unicode/utf16"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"golang.org/x/sys/windows"
	"golang.org/x/sys/windows/registry"
	"golang.org/x/term"
)

//go:embed upgrade.ps1
var installerScript string

var upgradePackageName = regexp.MustCompile(`^wiserec-cli-[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?-windows-x64\.msi$`)

func Offer(ctx context.Context, in io.Reader, out, stderr io.Writer, paths func() (localstate.Paths, error), format string, denial *platform.VersionDenial) {
	if denial.UpgradeURL == "" || !terminal(in) || !terminal(out) || !terminal(stderr) {
		return
	}
	state, err := paths()
	if err != nil {
		fmt.Fprintln(stderr, "[提示] 无法读取 Go CLI 本地状态，请联系管理员获取 MSI 安装包。")
		return
	}
	if format == "" {
		cfg, err := localstate.LoadConfig(state)
		if err != nil {
			fmt.Fprintln(stderr, "[提示] 无法读取 Go CLI 配置，请联系管理员获取 MSI 安装包。")
			return
		}
		if strings.EqualFold(cfg.Profile().Output, "json") {
			return
		}
	}

	downloadURL, err := denial.MSIUpgradeURL()
	if err != nil {
		fmt.Fprintln(stderr, "[提示] 无法自动升级：", err)
		return
	}
	executable, err := installedExecutable()
	if err != nil {
		fmt.Fprintln(stderr, "[提示] 无法自动升级：", err)
		return
	}
	prompt := "是否下载并安装升级包？"
	if denial.Recommended != "" {
		prompt = "是否下载并安装推荐版本？"
	}
	fmt.Fprintf(stderr, "\n%s[y/N] ", prompt)
	answer, _ := bufio.NewReader(in).ReadString('\n')
	if answer = strings.ToLower(strings.TrimSpace(answer)); answer != "y" && answer != "yes" {
		return
	}
	if err := stageUpgrade(ctx, state, executable, stderr, denial, downloadURL); err != nil {
		fmt.Fprintln(stderr, "[错误] 自动升级未完成：", err)
	}
}

func terminal(value any) bool {
	file, ok := value.(*os.File)
	return ok && term.IsTerminal(int(file.Fd()))
}

func installedExecutable() (string, error) {
	key, err := registry.OpenKey(registry.CURRENT_USER, `Software\WiseRec\CLIGo`, registry.QUERY_VALUE|registry.WOW64_64KEY)
	if err != nil {
		return "", errors.New("未找到当前用户的 Go CLI MSI 安装记录，请通过 MSI 手动升级")
	}
	defer key.Close()
	dir, _, err := key.GetStringValue("Path")
	if err != nil || !filepath.IsAbs(dir) {
		return "", errors.New("无法确认 Go CLI 的 MSI 安装路径")
	}
	installed := filepath.Join(dir, "ml.exe")
	executable, err := os.Executable()
	if err != nil || !strings.EqualFold(filepath.Clean(installed), filepath.Clean(executable)) {
		return "", errors.New("当前 ml.exe 路径与 MSI 安装记录不一致，请从 MSI 安装路径运行 ml.exe")
	}
	return installed, nil
}

func stageUpgrade(ctx context.Context, paths localstate.Paths, executable string, stderr io.Writer, denial *platform.VersionDenial, downloadURL string) error {
	systemDir, err := windows.GetSystemDirectory()
	if err != nil {
		return errors.New("无法定位 Windows PowerShell")
	}
	shell := filepath.Join(systemDir, "WindowsPowerShell", "v1.0", "powershell.exe")
	temp, err := os.MkdirTemp("", "wiserec-upgrade-")
	if err != nil {
		return errors.New("无法创建升级临时目录")
	}
	handoff := false
	defer func() {
		if !handoff {
			_ = os.RemoveAll(temp)
		}
	}()
	packagePath := filepath.Join(temp, "download.msi")
	env := []string{
		"WISECLI_UPGRADE_EXE=" + executable,
		"WISECLI_UPGRADE_CURRENT=" + denial.Current,
		"WISECLI_UPGRADE_MINIMUM=" + denial.Minimum,
		"WISECLI_UPGRADE_RECOMMENDED=" + denial.Recommended,
		"WISECLI_UPGRADE_PARENT=" + strconv.Itoa(os.Getpid()),
		"WISECLI_UPGRADE_LOCK=" + filepath.Join(paths.Dir, "upgrade-go.lock"),
	}

	fmt.Fprintf(stderr, "[信息] 正在下载 MSI 安装包：%s\n", downloadURL)
	var lastProgress time.Time
	err = platform.DownloadUpgradeMSI(ctx, downloadURL, packagePath, func(received, total int64) {
		if time.Since(lastProgress) < 500*time.Millisecond && received != total {
			return
		}
		lastProgress = time.Now()
		if total > 0 {
			fmt.Fprintf(stderr, "\r[信息] 已下载 %.1f / %.1f MiB", float64(received)/(1<<20), float64(total)/(1<<20))
		} else {
			fmt.Fprintf(stderr, "\r[信息] 已下载 %.1f MiB", float64(received)/(1<<20))
		}
	})
	fmt.Fprintln(stderr)
	if err != nil {
		return err
	}
	fmt.Fprintln(stderr, "[信息] 下载完成，正在检查 MSI 产品、架构和版本")
	verifyCtx, cancelVerify := context.WithTimeout(ctx, time.Minute)
	defer cancelVerify()
	verify := installerCommand(verifyCtx, shell, "verify", append(env, "WISECLI_UPGRADE_PACKAGE="+packagePath), stderr)
	verified, err := verify.Output()
	if err != nil {
		return errors.New("安装包验证未通过")
	}
	filename := strings.TrimSpace(string(verified))
	if !upgradePackageName.MatchString(filename) {
		return errors.New("无法确认升级安装包文件名")
	}
	packagePath = filepath.Join(temp, filename)
	fmt.Fprintf(stderr, "[信息] 升级安装包：%s\n", filename)

	pauseCtx, cancelPause := context.WithTimeout(ctx, 35*time.Second)
	defer cancelPause()
	if err := keepalive.PauseForUpgrade(pauseCtx, paths); err != nil {
		return err
	}
	if err := ctx.Err(); err != nil {
		return err
	}
	worker := installerCommand(context.Background(), shell, "install", append(env, "WISECLI_UPGRADE_PACKAGE="+packagePath), stderr)
	worker.Stdout = stderr
	worker.SysProcAttr = &syscall.SysProcAttr{CreationFlags: windows.CREATE_NEW_PROCESS_GROUP}
	if err := worker.Start(); err != nil {
		return errors.New("无法启动 Windows 升级进程")
	}
	handoff = true
	// stderr is a console file, so the independent installer inherits the handle.
	_ = worker.Process.Release()
	fmt.Fprintln(stderr, "[信息] 当前命令退出后将开始安装")
	return nil
}

func installerCommand(ctx context.Context, shell, mode string, env []string, stderr io.Writer) *exec.Cmd {
	utf16Script := utf16.Encode([]rune(installerScript))
	data := make([]byte, 2*len(utf16Script))
	for index, unit := range utf16Script {
		binary.LittleEndian.PutUint16(data[index*2:], unit)
	}
	command := exec.CommandContext(ctx, shell, "-NoLogo", "-NoProfile", "-NonInteractive", "-OutputFormat", "Text", "-EncodedCommand",
		base64.StdEncoding.EncodeToString(data))
	command.Env = append(command.Environ(), append(env, "WISECLI_UPGRADE_MODE="+mode)...)
	command.Stderr = stderr
	return command
}
