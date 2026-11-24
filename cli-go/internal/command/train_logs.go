package command

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

func newTrainLogs(options Options, load loadConfig, history bool) *cobra.Command {
	group := &cobra.Command{Use: "logs", Short: "执行实例日志归档与下载"}
	short := "归档并下载执行实例日志"
	if history {
		short = "检查归档并下载执行记录日志"
	}
	cmd := &cobra.Command{Use: "download TASK_ID JOB_ID", Short: short, Args: positional(2)}
	dir := cmd.Flags().String("directory", ".", "已存在的保存目录，默认当前目录")
	outputFlag(cmd)
	selection := ""
	kind := "log"
	role := ""
	wait := 120
	if history {
		cmd.Flags().StringVar(&kind, "type", kind, "日志类型 log 或 plog")
		cmd.Flags().StringVar(&role, "role-job-id", "", "分布式角色作业ID，即jobType为dps-train，非交互下载时必填")
		cmd.Flags().IntVar(&wait, "wait-timeout", wait, "归档等待参数")
		_ = cmd.Flags().MarkHidden("wait-timeout")
	} else {
		cmd.Flags().StringVar(&selection, "select", "", "日志编号，多个用英文逗号分隔，all 下载全部已归档日志")
	}
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if info, err := os.Stat(*dir); err != nil || !info.IsDir() {
			return errors.New("保存目录不存在或不是目录")
		}
		if !history {
			return runningTrainDownload(cmd, api, args[0], args[1], selection, *dir, format)
		}
		if wait < 0 || (kind != "log" && kind != "plog") || kind == "plog" && wait != 120 ||
			cmd.Flags().Changed("role-job-id") && strings.TrimSpace(role) == "" {
			return usageError{errors.New("日志类型、角色或归档等待参数无效")}
		}
		return historyTrainDownload(cmd, api, args[0], args[1], strings.TrimSpace(role), *dir, format, kind == "plog")
	})
	group.AddCommand(cmd)
	return group
}

func runningTrainDownload(cmd *cobra.Command, api *platform.API, taskID, jobID, selection, directory, format string) error {
	ctx := cmd.Context()
	steps := logDownloadSteps{out: cmd.ErrOrStderr()}
	steps.start("query_instance", "开始查询执行实例")
	items, err := api.RunningLogArchives(ctx, taskID, jobID, func() {
		steps.start("archive_log", "请求归档并查询归档日志")
	})
	if err != nil {
		return steps.failure(err)
	}
	if len(items) == 0 {
		steps.note("日志归档中，请稍后执行下载命令！")
		if format == "json" {
			return showOfflineResult(cmd, format, map[string]any{"status": "archiving", "count": 0, "items": items})
		}
		return nil
	}
	steps.start("select_log", "已获取归档记录，选择待下载日志")
	if err := renderRunningLogArchives(cmd.ErrOrStderr(), items); err != nil {
		return steps.failure(err)
	}
	downloadable := func(i int) bool { return platform.RunningLogArchiveReady(items[i]) }
	if selection == "" && !cmd.Flags().Changed("select") {
		available, _ := selectedLogs("all", len(items), downloadable)
		if len(available) == 0 {
			steps.note("暂无可下载的日志")
			if format == "json" {
				return showOfflineResult(cmd, format, map[string]any{"status": "unavailable", "count": len(items), "items": items})
			}
			return nil
		}
	}
	indices, err := selectTrainLogInputs(cmd, selection, cmd.Flags().Changed("select"), len(items), downloadable)
	if err != nil {
		return steps.failure(err)
	}
	if len(indices) == 0 {
		steps.note("没有选择可下载的日志")
		return nil
	}
	summaries := []map[string]any{}
	for index, idx := range indices {
		if err := ctx.Err(); err != nil {
			return err
		}
		item := items[idx]
		summary := map[string]any{"number": idx + 1, "taskName": item.Text("taskName"), "jobId": item.Text("jobId"), "roleJobId": item["roleJobId"]}
		name := platform.LogDownloadName(strings.Join([]string{item.Text("taskName"), item.Text("roleType"), item.Text("roleJobId"), item.Text("archiveId")}, "-") + "-logs")
		if len(indices) > 1 {
			steps.note(fmt.Sprintf("开始处理第 %d/%d 条日志", index+1, len(indices)))
		}
		steps.start("get_download_url", fmt.Sprintf("开始获取编号 %d 的日志下载地址", idx+1))
		url, err := api.RunningLogURL(ctx, item)
		if err == nil {
			var size int64
			var path string
			path, size, err = steps.download(ctx, api, url, filepath.Join(directory, name), directory, name, "日志")
			if err == nil {
				summary["status"], summary["path"], summary["bytes"] = "downloaded", path, size
			}
		}
		if err != nil {
			steps.failItem(summary, err)
		}
		summaries = append(summaries, summary)
	}
	return showLogSummaries(cmd, format, summaries, false)
}

func renderRunningLogArchives(out io.Writer, items []platform.Record) error {
	headers := []string{"编号", "任务名称", "jobId", "roleJobId", "节点名称", "状态", "失败原因", "开始时间", "结束时间", "是否可以下载"}
	rows := make([][]string, 0, len(items))
	for i, item := range items {
		status, downloadable := "未知状态", "否"
		switch {
		case platform.RunningLogArchiveReady(item):
			status, downloadable = "归档成功", "是"
		case string(item["status"]) == "0":
			status = "归档中"
		case string(item["status"]) == "2":
			status = "归档失败"
		}
		rows = append(rows, []string{
			strconv.Itoa(i + 1), fieldText(item["taskName"]), fieldText(item["jobId"]), fieldText(item["roleJobId"]),
			fieldText(item["roleType"]), status, fieldText(item["statusReason"]), dateText(item["createTime"]),
			dateText(item["updateTime"]), downloadable,
		})
	}
	// Keep both IDs, the status and the timestamps on one line even in narrow terminals.
	return output.Table(out, headers, rows, 2, 3, 5, 7, 8)
}

func historyTrainDownload(cmd *cobra.Command, api *platform.API, taskID, jobID, roleID, directory, format string, plog bool) error {
	ctx := cmd.Context()
	steps := logDownloadSteps{out: cmd.ErrOrStderr()}
	steps.start("query_record", "开始查询执行记录")
	row, err := api.TrainHistoryRecord(ctx, taskID, jobID, "all")
	if err != nil {
		return steps.failure(err)
	}
	items := []platform.Record{row}
	distributed := row.Text("jobType") == "dps-train"
	if distributed {
		steps.start("select_role", "已找到分布式训练记录，选择日志角色")
		roles, err := responseRecords(row, "roleJobInfo")
		if err != nil && strings.TrimSpace(string(row["roleJobInfo"])) != "null" {
			return steps.failure(err)
		}
		if len(roles) == 0 {
			return steps.failure(errors.New("该job无分布式角色，无日志可下载"))
		}
		if roleID != "" {
			items = nil
			for _, role := range roles {
				if role.Text("roleJobId") == roleID {
					items = append(items, role)
				}
			}
			if len(items) != 1 {
				return steps.failure(errors.New("roleJobId 不属于当前执行记录或匹配了多条角色"))
			}
		} else {
			input, interactive := cmd.InOrStdin().(*os.File)
			if format == "json" || !interactive || !term.IsTerminal(int(input.Fd())) {
				return steps.failure(errors.New("非交互或 JSON 模式请指定 --role-job-id"))
			}
			if err := renderTrainHistoryLogRoles(cmd.ErrOrStderr(), roles); err != nil {
				return steps.failure(err)
			}
			indices, err := selectTrainLogInputs(cmd, "", false, len(roles), func(i int) bool { return !plog || platform.HasPlog(roles[i]) })
			if err != nil {
				return steps.failure(err)
			}
			if len(indices) == 0 {
				steps.note("已取消日志下载")
				return nil
			}
			items = nil
			for _, i := range indices {
				items = append(items, roles[i])
			}
		}
	} else if roleID != "" {
		steps.start("select_role", "校验日志角色选项")
		return steps.failure(errors.New("普通训练不支持 --role-job-id"))
	}
	steps.start("validate_role", fmt.Sprintf("开始校验 %d 条待下载日志的信息", len(items)))
	for _, item := range items {
		if distributed && (item.Text("taskId") != taskID || item.Text("jobId") != jobID || strings.TrimSpace(item.Text("roleJobId")) == "") {
			return steps.failure(errors.New("分布式日志记录与当前任务或作业不一致"))
		}
		if plog && !platform.HasPlog(item) {
			return steps.failure(errors.New("该记录没有 plog 日志"))
		}
	}
	archives := map[string]error{}
	summaries := []map[string]any{}
	label := "日志"
	if plog {
		label = "plog 日志"
	}
	for index, item := range items {
		if len(items) > 1 {
			steps.note(fmt.Sprintf("开始处理第 %d/%d 条日志", index+1, len(items)))
		}
		summary := map[string]any{"taskId": taskID, "jobId": jobID}
		id := ""
		if distributed {
			id = item.Text("roleJobId")
			summary["roleJobId"], summary["roleType"] = id, item["roleType"]
		}
		link, err := api.HistoryLogURL(ctx, taskID, jobID, id, plog, steps.start)
		if errors.Is(err, platform.ErrLogNotReady) {
			if done, ok := archives[jobID]; ok {
				steps.start("archive_log", "检查本次归档请求结果")
				err = done
			} else {
				steps.start("archive_log", "日志未就绪，开始手动归档")
				err = api.ArchiveHistoryLog(ctx, jobID)
				archives[jobID] = err
			}
			if err == nil {
				message := "手动归档中，请稍后再次下载日志！"
				steps.note(message)
				summary["status"], summary["stage"], summary["message"] = "not_ready", steps.stage, message
				summaries = append(summaries, summary)
				continue
			}
		}
		if err == nil {
			baseName, destination := platform.LogDownloadName(jobID+"-logs"), ""
			if plog {
				baseName = platform.LogDownloadName(jobID + "-plog-logs")
			}
			if distributed {
				if plog {
					baseName = platform.LogDownloadName(id + "_plog.zip")
				} else {
					baseName = platform.LogDownloadName(jobID + "-" + item.Text("roleType") + "-" + id + "-logs")
				}
				destination = filepath.Join(directory, baseName)
			}
			path, bytes, downloadErr := steps.download(ctx, api, link, destination, directory, baseName, label)
			err = downloadErr
			if err == nil {
				summary["status"], summary["path"], summary["bytes"] = "downloaded", path, bytes
			}
		}
		if err != nil {
			steps.failItem(summary, err)
		}
		summaries = append(summaries, summary)
	}
	return showLogSummaries(cmd, format, summaries, !distributed)
}

func selectedLogs(text string, count int, downloadable func(int) bool) ([]int, error) {
	indices := []int{}
	if strings.EqualFold(strings.TrimSpace(text), "all") {
		for index := 0; index < count; index++ {
			if downloadable(index) {
				indices = append(indices, index)
			}
		}
		return indices, nil
	}
	seen := map[int]bool{}
	for _, input := range strings.Split(text, ",") {
		input = strings.TrimSpace(input)
		index, err := strconv.Atoi(input)
		if err != nil || index < 1 || index > count {
			return nil, errors.New("请输入有效编号，多个编号使用英文逗号分隔")
		}
		if !downloadable(index - 1) {
			return nil, fmt.Errorf("编号 %d 尚不可下载", index)
		}
		if !seen[index] {
			indices = append(indices, index-1)
			seen[index] = true
		}
	}
	return indices, nil
}

func selectTrainLogInputs(cmd *cobra.Command, value string, provided bool, count int, downloadable func(int) bool) ([]int, error) {
	if provided {
		return selectedLogs(value, count, downloadable)
	}
	input := bufio.NewReader(cmd.InOrStdin())
	for {
		fmt.Fprint(cmd.ErrOrStderr(), "输入日志编号，多个用英文逗号分隔；all 下载全部；q 取消：")
		answer, err := input.ReadString('\n')
		if strings.EqualFold(strings.TrimSpace(answer), "q") || err != nil && answer == "" {
			return nil, nil
		}
		values, parse := selectedLogs(answer, count, downloadable)
		if parse == nil {
			return values, nil
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[错误]", parse)
		if err != nil {
			return nil, parse
		}
	}
}

func showLogSummaries(cmd *cobra.Command, format string, summaries []map[string]any, single bool) error {
	failed := 0
	for _, summary := range summaries {
		if summary["status"] != "downloaded" {
			failed++
		}
	}
	status := "downloaded"
	if failed > 0 {
		status = "failed"
	}
	result := any(map[string]any{"status": status, "succeeded": len(summaries) - failed, "failed": failed, "items": summaries})
	if single && len(summaries) == 1 {
		result = summaries[0]
	}
	if err := showOfflineResult(cmd, format, result); err != nil {
		return err
	}
	if failed > 0 {
		return silentExit(1)
	}
	return nil
}
