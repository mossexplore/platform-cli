package command

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newTrain(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "train", Short: "训练任务查询与执行管理"}
	instance := &cobra.Command{Use: "instance", Short: "训练任务执行实例查询与日志下载"}
	history := &cobra.Command{Use: "history", Short: "训练任务执行记录查询"}
	config := &cobra.Command{Use: "config", Short: "训练任务自定义参数管理"}

	list := trainListCommand("list", "分页查询当前业务下的训练任务", 0, options, load,
		func(ctx context.Context, api *platform.API, cmd *cobra.Command, _ []string, page, size int) (platform.Page, string, error) {
			name, _ := cmd.Flags().GetString("name")
			name, err := applyExactName(cmd, name)
			if err != nil {
				return platform.Page{}, "", err
			}
			value, err := api.TrainList(ctx, page, size, name, allBusinessRequested(cmd))
			return value, "", err
		}, trainTaskColumns, "暂无训练任务")
	addAllBusinessFlag(list)
	addExactFlag(list)
	list.Flags().Lookup("page-size").Usage += "，MLOps 最多 200 条"
	list.Flags().String("name", "", "按任务名称查询；配合 --exact 可精确查询")
	instanceList := trainListCommand("list TASK_ID", "分页查询训练任务执行实例", 1, options, load,
		func(ctx context.Context, api *platform.API, _ *cobra.Command, args []string, page, size int) (platform.Page, string, error) {
			task, err := api.TrainTask(ctx, args[0])
			if err != nil {
				return platform.Page{}, "", err
			}
			value, err := api.TrainInstances(ctx, task, page, size, "periodDate")
			return value, fmt.Sprintf("任务：%s · %s", task.Text("taskName"), args[0]), err
		}, trainInstanceColumns, "暂无执行实例")
	var latestFlag string
	historyList := trainListCommand("list TASK_ID", "分页查询训练任务执行记录并可包含历史实例", 1, options, load,
		func(ctx context.Context, api *platform.API, _ *cobra.Command, args []string, page, size int) (platform.Page, string, error) {
			value, err := api.TrainHistory(ctx, args[0], page, size, latestFlag)
			return value, "任务 ID：" + args[0], err
		}, trainHistoryColumns, "暂无执行记录")
	historyList.Flags().StringVar(&latestFlag, "latest-flag", "true", "true 仅查看最新实例，all 同时查看历史实例")
	historyList.Args = func(cmd *cobra.Command, args []string) error {
		if latestFlag != "true" && latestFlag != "all" {
			return usageError{errors.New("--latest-flag 仅支持 true 或 all")}
		}
		return positional(1)(cmd, args)
	}

	detail := &cobra.Command{Use: "detail TASK_ID", Short: "查询训练任务详情", Args: positional(1)}
	detail.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		result, err := api.TrainDetail(cmd.Context(), args[0], "", false)
		if err != nil {
			return err
		}
		return renderTrainDetail(cmd.OutOrStdout(), result, format)
	})
	outputFlag(detail)

	historyDetail := &cobra.Command{Use: "detail TASK_ID JOB_ID", Short: "查询执行记录详情及分布式角色列表", Args: positional(2)}
	historyDetail.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		record, err := api.TrainHistoryRecord(cmd.Context(), args[0], args[1], "true")
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			r := agentRecord(record, columnKeys(trainHistoryColumns, "taskId")...)
			if err := agentHistory(record, r); err != nil {
				return err
			}
			return agentResult(cmd, r)
		}
		return renderTrainHistoryDetail(cmd.OutOrStdout(), record, args[0], args[1], format)
	})
	outputFlag(historyDetail)
	history.AddCommand(historyList, historyDetail, newTrainLogs(options, load, true))
	instance.AddCommand(instanceList, newTrainLogs(options, load, false))
	config.AddCommand(newTrainUpdate(options, load), newTrainExport(options, load))
	group.AddCommand(instance, history, config, list, detail)
	group.AddCommand(newTrainStart(options, load), newTrainDelete(options, load), newTrainCancel(options, load), newTrainClone(options, load))
	return group
}

type queryTrainPage func(context.Context, *platform.API, *cobra.Command, []string, int, int) (platform.Page, string, error)

func trainListCommand(use, short string, argsCount int, options Options, load loadConfig, query queryTrainPage, cols []recordColumn, empty string) *cobra.Command {
	cmd := &cobra.Command{Use: use, Short: short, Args: positional(argsCount)}
	page, size := pagination(cmd)
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		result, heading, err := query(cmd.Context(), api, cmd, args, *page, *size)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			columns := allBusinessColumns(cols, allBusinessRequested(cmd))
			rows := agentRows(result.Items, columns)
			fields := agentFields(columns, nil)
			switch cmd.Parent().Name() {
			case "instance":
				now := time.Now()
				for i, r := range result.Items {
					fillAgentRunningTime(r, rows[i], now)
				}
			case "history":
				fields["jobType"] = "作业类型"
				fields["plogReady"] = "普通作业的 plog 是否已就绪"
				fields["roleJobInfo"] = "分布式角色列表"
				fields["roleJobInfo.plogReady"] = "该角色的 plog 是否已就绪"
				for _, col := range trainRoles {
					fields["roleJobInfo."+col.key] = col.title
				}
				for i, r := range result.Items {
					if err := agentHistory(r, rows[i]); err != nil {
						return err
					}
				}
			}
			return agentResult(cmd, output.AgentList(rows, fields, "paged", result.PageIndex, result.PageSize, &result.Count))
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), result)
		}
		return renderTrainPage(cmd.OutOrStdout(), result, heading, allBusinessColumns(cols, allBusinessRequested(cmd)), empty)
	})
	return cmd
}

func newTrainStart(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "start TASK_ID", Short: "立即执行指定训练任务，返回作业 ID", Args: positional(1)}
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		jobID, err := api.StartTrain(cmd.Context(), args[0])
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"taskId": args[0], "jobId": jobID})
		}
		if jobID == "" {
			_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[警告] 训练任务执行成功，但接口未返回有效 jobId，请查询执行记录确认。")
		} else {
			_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 训练任务执行成功，jobId："+jobID)
		}
		return err
	})
	return cmd
}

func newTrainDelete(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "delete TASK_ID", Short: "软删除当前业务下的训练任务", Args: positional(1)}
	cmd.Flags().BoolP("yes", "y", false, "跳过删除确认")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		task, err := api.TrainTask(cmd.Context(), args[0])
		if err != nil {
			return err
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "待删除训练任务：%s · %s（团队 %s）\n", task.Text("taskName"), args[0], loginValue(task.Text("teamId")))
		ok, err := approve(cmd, "确认软删除此任务？")
		if !ok || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消操作")
			return err
		}
		if err := api.DeleteTrain(cmd.Context(), task); err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"taskId": args[0], "status": "deleted"})
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 删除训练任务"+args[0]+"成功")
		return err
	})
	return cmd
}

func newTrainCancel(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "cancel TASK_ID", Short: "查询所有执行实例并逐个取消", Args: positional(1)}
	cmd.Flags().BoolP("yes", "y", false, "跳过批量取消确认")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		ctx := cmd.Context()
		task, err := api.TrainTask(ctx, args[0])
		if err != nil {
			return err
		}
		items, err := api.AllTrainInstances(ctx, task)
		if err != nil {
			return err
		}
		if len(items) == 0 {
			return errors.New("没有正在执行的任务，无法取消任务执行")
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "训练任务 %s 有 %d 个执行实例待取消。\n", args[0], len(items))
		ok, err := approve(cmd, "确认逐个取消全部执行实例？")
		if !ok || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消操作")
			return err
		}
		failed := 0
		var outcomes []map[string]any
		for _, item := range items {
			if err := ctx.Err(); err != nil {
				return err
			}
			description, err := api.CancelTrainInstance(ctx, args[0], item)
			if agentMode(cmd) {
				itemResult := map[string]any{"jobId": item.Text("jobId"), "cancelled": err == nil}
				if err != nil {
					itemResult["error"] = err.Error()
				}
				outcomes = append(outcomes, itemResult)
			}
			if err != nil {
				failed++
				fmt.Fprintf(cmd.ErrOrStderr(), "[错误] 取消训练任务%s的执行实例%s失败：%s\n", args[0], item.Text("jobId"), err)
				if errors.Is(err, platform.ErrTargetChanged) {
					return err
				}
			} else {
				fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 取消训练任务%s的执行实例%s成功，响应描述是%s\n", args[0], item.Text("jobId"), description)
			}
		}
		summary := fmt.Sprintf("取消完成：成功 %d 个，失败 %d 个。", len(items)-failed, failed)
		if agentMode(cmd) {
			if err := agentResult(cmd, map[string]any{"succeeded": len(items) - failed, "failed": failed, "items": outcomes}); err != nil {
				return err
			}
		}
		if failed > 0 {
			return errors.New(summary)
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] "+summary)
		return err
	})
	return cmd
}

func newTrainClone(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "clone TASK_ID", Short: "读取完整训练任务详情并创建副本", Args: positional(1)}
	name := cmd.Flags().String("name", "", "克隆后的新任务名称")
	custom := cmd.Flags().String("customize-config", "", "可选自定义参数，按字符串原样传递")
	cmd.Flags().BoolP("yes", "y", false, "跳过克隆确认")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if err := positional(1)(cmd, []string{*name}); err != nil {
			return usageError{errors.New("--name 不能为空")}
		}
		ctx := cmd.Context()
		task, err := api.TrainTask(ctx, args[0])
		if err != nil {
			return err
		}
		detail, err := api.CloneTrainDetail(ctx, task)
		if err != nil {
			return err
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "克隆为：%s（源任务：%s）\n", *name, args[0])
		ok, err := approve(cmd, "确认克隆？")
		if !ok || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消克隆")
			return err
		}
		var config *string
		if cmd.Flags().Changed("customize-config") {
			config = custom
		}
		id, err := api.CloneTrain(ctx, detail, *name, config)
		if err != nil {
			return err
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 克隆训练任务"+args[0]+"成功")
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"sourceTaskId": args[0], "taskId": id})
		}
		if id != "" {
			_, err = fmt.Fprintln(cmd.OutOrStdout(), "新任务 ID："+id)
		}
		return err
	})
	return cmd
}

func newTrainUpdate(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "update TASK_ID", Short: "获取训练任务详情，保留完整 taskInfo 后更新自定义参数", Args: positional(1)}
	config := cmd.Flags().String("customize-config", "", "自定义参数，按字符串原样传递")
	_ = cmd.MarkFlagRequired("customize-config")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if err := api.UpdateTrainConfig(cmd.Context(), args[0], *config); err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"taskId": args[0], "status": "updated"})
		}
		_, err := fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 更新训练任务自定义参数成功！")
		return err
	})
	return cmd
}

func newTrainExport(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "export TASK_ID", Short: "导出并下载训练任务的 YAML 配置", Args: positional(1)}
	file := cmd.Flags().String("file", "", "本地保存路径，父目录须已存在")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if *file != "" {
			info, err := os.Stat(filepath.Dir(*file))
			if err != nil || !info.IsDir() {
				return errors.New("目标目录不存在")
			}
		}
		path, size, err := api.ExportTrain(cmd.Context(), args[0], *file)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]any{"file": path, "bytes": size})
		}
		_, err = fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 训练任务配置已下载：%s（%d 字节）\n", path, size)
		return err
	})
	return cmd
}
