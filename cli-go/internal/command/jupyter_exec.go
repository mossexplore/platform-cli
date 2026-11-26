package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/jupyter"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

func newJupyterExec(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "exec -- PROGRAM [ARG...]", Short: "在独立 Python Kernel 中执行非交互子进程",
		Annotations: map[string]string{"text_output": "true"},
		Args: func(_ *cobra.Command, values []string) error {
			if len(values) == 0 || values[0] == "" {
				return usageError{errors.New("请指定要执行的程序和参数")}
			}
			return nil
		},
	}
	cwd := cmd.Flags().String("cwd", "", "相对 Jupyter 根目录的远端目录")
	kernel := cmd.Flags().String("kernel", "", "远端 Python Kernel 名称")
	timeout := cmd.Flags().Float64("timeout", 60, "执行时限秒数")
	startup := cmd.Flags().Float64("startup-timeout", 60, "Kernel 等待秒数")
	limit := cmd.Flags().Int("max-output", 1048576, "stdout 和 stderr 各自保留的最大字节数")
	format := cmd.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
	cmd.Flags().String("studio-id", "", "Web Studio 实例 ID")
	run := withJupyter(options, load, func(cmd *cobra.Command, args []string, client *jupyter.Client, format string) error {
		if !validSeconds(*timeout) || !validSeconds(*startup) || *limit < 1 || *limit > 10485760 {
			return usageError{errors.New("timeout、startup-timeout 或 max-output 超出范围")}
		}
		settings := jupyter.ExecutionOptions{Kernel: *kernel, Directory: *cwd,
			Startup: seconds(*startup), Timeout: seconds(*timeout), OutputLimit: *limit}
		result, err := client.Execute(cmd.Context(), args, settings)
		if err != nil {
			return err
		}
		value := any(result)
		if format == "json" && !agentMode(cmd) {
			value = client.Result(result)
		}
		if err := output.JSON(cmd.OutOrStdout(), value); err != nil {
			return err
		}
		maxExitCode := 123
		if agentMode(cmd) {
			maxExitCode = 255
		}
		return executionStatus(result, maxExitCode)
	})
	cmd.RunE = func(cmd *cobra.Command, args []string) error {
		err := run(cmd, args)
		var usage usageError
		var exit silentExit
		if err == nil || !strings.EqualFold(*format, "json") || errors.As(err, &usage) || errors.As(err, &exit) || cmd.Context().Err() != nil {
			return err
		}
		if writeErr := output.JSON(cmd.OutOrStdout(), map[string]string{"status": "FAILED", "error": terminalControl.ReplaceAllString(err.Error(), "")}); writeErr != nil {
			return writeErr
		}
		return silentExit(1)
	}
	return cmd
}

func validSeconds(value float64) bool {
	return value >= 0.1 && value <= float64(math.MaxInt64/int64(time.Second)-60)
}

func seconds(value float64) time.Duration { return time.Duration(value * float64(time.Second)) }

func executionStatus(summary map[string]any, maxExitCode int) error {
	status, _ := summary["status"].(string)
	if raw, ok := summary["status"].(json.RawMessage); ok {
		_ = json.Unmarshal(raw, &status)
	}
	switch status {
	case "SUCCEEDED":
		return nil
	case "TIMED_OUT":
		return silentExit(124)
	case "INTERRUPTED":
		return silentExit(130)
	case "LOST":
		return silentExit(2)
	case "FAILED":
		var code int
		if raw, ok := summary["exit_code"].(json.RawMessage); ok && json.Unmarshal(raw, &code) == nil && code > 0 && code <= maxExitCode {
			return silentExit(code)
		}
	}
	return silentExit(1)
}

func newTerminalConnect(options Options, load loadConfig, create bool) *cobra.Command {
	name, short, size := "attach NAME", "连接已有终端", 1
	if create {
		name, short, size = "open", "创建并连接远程终端", 0
	}
	cmd := &cobra.Command{Use: name, Short: short, Args: positional(size)}
	cmd.Flags().String("studio-id", "", "Web Studio 实例 ID")
	cmd.RunE = func(cmd *cobra.Command, args []string) error {
		in, inOK := cmd.InOrStdin().(*os.File)
		out, outOK := cmd.OutOrStdout().(*os.File)
		if !inOK || !outOK || !term.IsTerminal(int(in.Fd())) || !term.IsTerminal(int(out.Fd())) {
			return errors.New("远程交互终端需要本地交互式终端")
		}
		return withJupyter(options, load, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) error {
			var id string
			var err error
			if create {
				id, err = client.CreateTerminal(cmd.Context())
				if err != nil {
					return err
				}
			} else {
				id = args[0]
			}
			fmt.Fprintf(cmd.ErrOrStderr(), "终端名称：%s；按 Ctrl+] 断开，exit 关闭远程 Shell。\n", id)
			err = client.Attach(cmd.Context(), id, in, out)
			fmt.Fprintln(cmd.ErrOrStderr(), "已结束本地连接；远程终端是否存续请用 ml jupyter terminal list 查看")
			return err
		})(cmd, args)
	}
	return cmd
}

func newJupyterNotebook(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "notebook", Short: "执行 Jupyter Notebook"}
	run := &cobra.Command{Use: "run SOURCE", Short: "上传并按顺序执行 Notebook，保存部分结果",
		Args: positional(1), Annotations: map[string]string{"text_output": "true"}}
	download := run.Flags().String("download", "results", "本地结果根目录")
	kernel := run.Flags().String("kernel", "", "远端 Kernel 名称")
	cwd := run.Flags().String("cwd", "", "远端工作目录")
	timeout := run.Flags().Float64("timeout", 600, "全部单元格执行时限秒数")
	startup := run.Flags().Float64("startup-timeout", 60, "Kernel 等待秒数")
	run.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
	run.Flags().String("studio-id", "", "Web Studio 实例 ID")
	run.RunE = withJupyter(options, load, func(cmd *cobra.Command, args []string, client *jupyter.Client, format string) error {
		if !strings.EqualFold(filepath.Ext(args[0]), ".ipynb") {
			return usageError{errors.New("输入必须为 .ipynb 文件")}
		}
		if !validSeconds(*timeout) || !validSeconds(*startup) {
			return usageError{errors.New("timeout 或 startup-timeout 超出范围")}
		}
		settings := jupyter.ExecutionOptions{Kernel: *kernel, Directory: *cwd, Timeout: seconds(*timeout), Startup: seconds(*startup)}
		result, err := client.RunNotebook(cmd.Context(), args[0], *download, settings, func(message string) {
			fmt.Fprint(cmd.ErrOrStderr(), terminalControl.ReplaceAllString(message, ""))
		})
		if err != nil {
			return err
		}
		if format == "json" {
			if err := output.JSON(cmd.OutOrStdout(), result); err != nil {
				return err
			}
		} else {
			fmt.Fprintf(cmd.OutOrStdout(), "执行 ID：%s\n状态：%s\n完成时间：%s\n结果：%s\n",
				result["id"], result["status"], result["finished_at"], result["notebook"])
			if message, ok := result["error"].(string); ok && message != "" {
				fmt.Fprintln(cmd.ErrOrStderr(), "[错误]", terminalControl.ReplaceAllString(message, ""))
			}
			warnings, _ := result["cleanup_errors"].([]string)
			for _, warning := range warnings {
				fmt.Fprintln(cmd.ErrOrStderr(), "[警告]", warning)
			}
		}
		return executionStatus(result, 0)
	})
	group.AddCommand(run)
	return group
}
