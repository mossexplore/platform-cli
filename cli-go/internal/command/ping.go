package command

import (
	"encoding/json"
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

const workerStandbyLabel = "DSH 托管，终端待命"

func newPing(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "ping", Short: "管理终端与 Harness 自动保活"}
	start := &cobra.Command{Use: "start", Short: "启动终端保活或恢复 Harness 插件调度", Args: positional(0)}
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
		if paths.Session.Mode != localstate.SessionModeDSH && !canStartPing(cmd, paths) {
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
		if err := keepalive.Stop(paths, profile.Name); err != nil {
			return err
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 当前环境的自动保活已停止")
		return err
	}
	status := &cobra.Command{Use: "status", Short: "只读查看自动保活状态", Args: positional(0)}
	status.Long = "查看终端 worker 或当前 Harness 会话的插件调度状态以及最近请求结果。"
	status.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if paths.Session.Mode == localstate.SessionModeDSH {
			host, err := keepalive.ViewHost(paths, cfg, time.Now())
			if err != nil {
				return err
			}
			entry := host.Entry
			return (output.Fields{{Key: "环境", Value: labelOrID(cfg.Current, "未绑定")},
				{Key: "状态", Value: host.State}, {Key: "进程 ID", Value: "-"},
				{Key: "插件最近报到", Value: pingTime(host.Seen)},
				{Key: "上次平台确认成功", Value: pingTime(entry.LastConfirmed)},
				{Key: "下次可探活时间", Value: pingTime(host.Next)},
				{Key: "上次请求 ID", Value: labelOrID(entry.RequestID, "-")},
				{Key: "最近错误", Value: labelOrID(entry.Error, "-")}}).Table(cmd.OutOrStdout())
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		interval := time.Duration(cfg.Auth.PingMinutes) * time.Minute
		entry, running, err := keepalive.View(paths, profile.Name)
		if err != nil {
			return err
		}
		state, pid, enabled, next := "未运行", "-", "启用", "-"
		if !cfg.PingEnabled() {
			enabled = "关闭"
		}
		if running {
			state, pid = entry.Status, strconv.Itoa(entry.WorkerPID)
			switch state {
			case keepalive.WorkerStandby:
				state = workerStandbyLabel
			case "waiting":
				state = "等待有效业务上下文"
			}
			next = pingTime(nextPingTime(entry, interval))
		}
		fields := output.Fields{{Key: "环境", Value: profile.Name}, {Key: "自动保活", Value: enabled},
			{Key: "状态", Value: state}, {Key: "进程 ID", Value: pid}, {Key: "保活终端数", Value: strconv.Itoa(len(entry.Owner))},
			{Key: "间隔（分钟）", Value: strconv.Itoa(cfg.Auth.PingMinutes)}, {Key: "上次请求", Value: pingTime(entry.LastAttempt)},
			{Key: "上次平台确认成功", Value: pingTime(entry.LastConfirmed)}, {Key: "下次预计请求", Value: next},
			{Key: "上次请求 ID", Value: labelOrID(entry.RequestID, "-")}, {Key: "成功次数", Value: strconv.Itoa(entry.Success)},
			{Key: "失败次数", Value: strconv.Itoa(entry.Failure)}, {Key: "最近错误", Value: labelOrID(entry.Error, "-")}}
		return fields.Table(cmd.OutOrStdout())
	}
	group.AddCommand(start, stop, status, newPingTick(options))
	return group
}

func fromTerminal(cmd *cobra.Command) bool {
	file, ok := cmd.InOrStdin().(*os.File)
	return ok && term.IsTerminal(int(file.Fd()))
}

func canStartPing(cmd *cobra.Command, paths localstate.Paths) bool {
	return paths.Session.Mode != localstate.SessionModeDSH && fromTerminal(cmd)
}

func maintainSessionFiles(paths localstate.Paths) {
	if paths.IsSessionIsolated() {
		keepalive.MaintainSessions(paths)
	}
}

func pingTime(value time.Time) string {
	if value.IsZero() {
		return "-"
	}
	return value.In(beijing).Format("2006-01-02 15:04:05")
}

func nextPingTime(entry keepalive.Entry, interval time.Duration) time.Time {
	if entry.Status != "running" || entry.LastActivity.IsZero() {
		return time.Time{}
	}
	return entry.LastActivity.Add(interval)
}

func startAutoPing(cmd *cobra.Command, paths localstate.Paths, cfg localstate.Config, version string, automatic bool) {
	if !cfg.PingEnabled() || !canStartPing(cmd, paths) {
		return
	}
	message, err := keepalive.Start(cmd.Context(), paths, cfg, version, automatic)
	if err != nil {
		fmt.Fprintln(cmd.ErrOrStderr(), "[警告]", err)
		return
	}
	if message != "" {
		fmt.Fprintln(cmd.ErrOrStderr(), message)
	}
}

func newPingTick(options Options) *cobra.Command {
	tick := &cobra.Command{Use: "tick", Short: "供 Harness 插件执行单次保活检查", Args: positional(0)}
	capabilities := tick.Flags().Bool("capabilities", false, "查看插件调度协议和调用预算")
	tick.Flags().Bool("json", false, "从标准输入读取宿主请求并输出 JSON")
	tick.MarkFlagsMutuallyExclusive("capabilities", "json")
	tick.MarkFlagsOneRequired("capabilities", "json")
	tick.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, err := options.Paths()
		if err != nil {
			return err
		}
		encoder := json.NewEncoder(cmd.OutOrStdout())
		if *capabilities {
			return encoder.Encode(struct {
				Protocol string `json:"protocol"`
				Version  string `json:"cli_version"`
				BudgetMS int64  `json:"budget_ms"`
			}{keepalive.HostProtocol, options.Version, keepalive.HostBudgetMS(paths)})
		}
		request, err := keepalive.DecodeHostRequest(cmd.InOrStdin())
		if err != nil {
			if writeErr := encoder.Encode(keepalive.TickResult{Protocol: keepalive.HostProtocol, State: "invalid_request"}); writeErr != nil {
				return writeErr
			}
			return silentExit(2)
		}
		result, err := keepalive.Tick(cmd.Context(), paths, request, options.Version)
		if err != nil {
			result.State = "local_error"
			result.RequestID = ""
			result.NextAttempt = ""
			if writeErr := encoder.Encode(result); writeErr != nil {
				return writeErr
			}
			return silentExit(1)
		}
		if err := encoder.Encode(result); err != nil {
			return err
		}
		if result.State == "invalid_request" {
			return silentExit(2)
		}
		return nil
	}
	return tick
}
