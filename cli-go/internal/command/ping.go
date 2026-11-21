package command

import (
	"fmt"
	"os"
	"strconv"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

func newPing(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "ping", Short: "管理终端会话自动保活"}
	start := &cobra.Command{Use: "start", Short: "为当前终端或 Harness 会话启动自动保活", Args: positional(0)}
	start.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if _, err := cfg.RequireProfile(); err != nil {
			return err
		}
		if !cfg.PingEnabled() {
			_, err := fmt.Fprintln(cmd.ErrOrStderr(), "自动保活已在配置中关闭")
			return err
		}
		if !canStartPing(cmd, paths) {
			_, err := fmt.Fprintln(cmd.ErrOrStderr(), "当前不是交互式终端，未启动自动保活")
			return err
		}
		message, err := keepalive.Start(cmd.Context(), paths, cfg, options.Version, false)
		if err != nil {
			return err
		}
		if message != "" {
			fmt.Fprintln(cmd.ErrOrStderr(), message)
		}
		return nil
	}
	stop := &cobra.Command{Use: "stop", Short: "停止当前环境的自动保活", Args: positional(0)}
	stop.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		if err := keepalive.Stop(paths, profile.Name, false); err != nil {
			return err
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 当前环境的自动保活已停止")
		return err
	}
	status := &cobra.Command{Use: "status", Short: "只读查看自动保活状态", Args: positional(0)}
	status.Long = "查看当前环境的保活终端数、Harness 会话数和最近请求结果。查看状态不会刷新会话登记。"
	status.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		interval := time.Duration(cfg.Auth.PingMinutes) * time.Minute
		entry, running, err := keepalive.View(paths, profile.Name, interval)
		if err != nil {
			return err
		}
		state, pid, enabled, next := "未运行", "-", "启用", "-"
		if !cfg.PingEnabled() {
			enabled = "关闭"
		}
		if running {
			state, pid = entry.Status, strconv.Itoa(entry.WorkerPID)
			if state == "waiting" {
				state = "等待有效业务上下文"
			} else if state == "running" {
				next = pingTime(entry.LastActivity.Add(interval))
			}
		}
		fields := output.Fields{{Key: "环境", Value: profile.Name}, {Key: "自动保活", Value: enabled},
			{Key: "状态", Value: state}, {Key: "进程 ID", Value: pid}, {Key: "保活终端数", Value: strconv.Itoa(keepalive.TerminalCount(entry))},
			{Key: "保活会话数", Value: strconv.Itoa(keepalive.SessionCount(entry))},
			{Key: "间隔（分钟）", Value: strconv.Itoa(cfg.Auth.PingMinutes)}, {Key: "上次请求", Value: pingTime(entry.LastAttempt)},
			{Key: "上次平台确认成功", Value: pingTime(entry.LastConfirmed)}, {Key: "下次预计请求", Value: next},
			{Key: "上次请求 ID", Value: labelOrID(entry.RequestID, "-")}, {Key: "成功次数", Value: strconv.Itoa(entry.Success)},
			{Key: "失败次数", Value: strconv.Itoa(entry.Failure)}, {Key: "最近错误", Value: labelOrID(entry.Error, "-")}}
		return fields.Table(cmd.OutOrStdout())
	}
	group.AddCommand(start, stop, status)
	return group
}

func fromTerminal(cmd *cobra.Command) bool {
	file, ok := cmd.InOrStdin().(*os.File)
	return ok && term.IsTerminal(int(file.Fd()))
}

func canStartPing(cmd *cobra.Command, paths localstate.Paths) bool {
	return paths.Session.Mode == localstate.SessionModeDSH || fromTerminal(cmd)
}

func maintainSessionFiles(paths localstate.Paths, cfg localstate.Config) {
	if paths.IsSessionIsolated() {
		keepalive.MaintainSessions(paths, time.Duration(cfg.Auth.PingMinutes)*time.Minute)
	}
}

func pingTime(value time.Time) string {
	if value.IsZero() {
		return "-"
	}
	return value.In(beijing).Format("2006-01-02 15:04:05")
}

func startAutoPing(cmd *cobra.Command, paths localstate.Paths, cfg localstate.Config, version string, automatic bool) {
	if !cfg.PingEnabled() || !canStartPing(cmd, paths) {
		return
	}
	message, err := keepalive.Start(cmd.Context(), paths, cfg, version, automatic)
	if err != nil {
		fmt.Fprintln(cmd.ErrOrStderr(), "[警告] 自动保活启动失败：", err)
		return
	}
	if message != "" {
		fmt.Fprintln(cmd.ErrOrStderr(), message)
	}
}
