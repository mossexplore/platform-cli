package command

import (
	"context"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

type trainLogOptions struct {
	directory, kind          string
	roles                    []string
	all, retry, wait, noWait bool
	interval, timeout        int
}

func newUnifiedTrainLogs(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "logs", Short: "训练日志查询与下载"}
	cmd := &cobra.Command{Use: "download TASK_ID [JOB_ID]", Short: "按作业状态下载训练日志"}
	var o trainLogOptions
	f := cmd.Flags()
	f.StringVar(&o.directory, "directory", ".", "已存在的保存目录")
	f.StringVar(&o.kind, "type", "log", "日志类型 log 或 plog")
	f.StringArrayVar(&o.roles, "role-job-id", nil, "角色作业 ID，可重复指定")
	f.BoolVar(&o.all, "all", false, "下载全部角色")
	f.BoolVar(&o.retry, "retry", false, "确认对指定运行中作业的全部日志重新下载")
	f.BoolVar(&o.wait, "wait", true, "等待历史普通日志可用")
	f.BoolVar(&o.noWait, "no-wait", false, "仅查询一轮")
	f.IntVar(&o.interval, "poll-interval", 30, "轮询间隔秒数")
	f.IntVar(&o.timeout, "wait-timeout", 120, "等待上限秒数，0 表示仅查询一轮")
	outputFlag(cmd)
	cmd.Args = func(cmd *cobra.Command, args []string) error {
		if len(args) < 1 || len(args) > 2 {
			return logUsage("需要 TASK_ID，可选 JOB_ID")
		}
		if err := positional(len(args))(cmd, args); err != nil {
			return err
		}
		if o.kind != "log" && o.kind != "plog" {
			return logUsage("--type 仅支持 log 或 plog")
		}
		const maxSeconds = int64((1<<63 - 1) / time.Second)
		if o.interval < 1 || o.timeout < 0 || int64(o.interval) > maxSeconds || int64(o.timeout) > maxSeconds {
			return logUsage("轮询间隔或等待上限无效")
		}
		if f.Changed("wait") && f.Changed("no-wait") {
			return logUsage("--wait 与 --no-wait 互斥")
		}
		for i, id := range o.roles {
			o.roles[i] = strings.TrimSpace(id)
			if o.roles[i] == "" {
				return logUsage("角色 ID 不能为空")
			}
		}
		if (o.all || o.retry) && len(o.roles) > 0 {
			return logUsage("--all、--retry 不能与 --role-job-id 同用")
		}
		if o.retry && (len(args) != 2 || o.kind != "log") {
			return logUsage("--retry 需要显式 JOB_ID 且仅支持运行中作业普通日志")
		}
		return nil
	}
	cmd.RunE = func(cmd *cobra.Command, args []string) error {
		format, _ := cmd.Flags().GetString("output")
		run := trainLogRun{options: o, cmd: cmd, format: format, task: args[0], steps: logDownloadSteps{out: cmd.ErrOrStderr(), stage: "authorize"}, items: []*trainLogItem{}}
		if len(args) == 2 {
			run.job = args[1]
		}
		invoke := authorized(options, load, func(_ *cobra.Command, _ []string, api *platform.API, format string) error {
			run.api, run.format = api, format
			if info, err := os.Stat(o.directory); err != nil || !info.IsDir() {
				return logUsage("保存目录不存在或不是目录")
			}
			return run.execute()
		})
		err := invoke(cmd, args)
		if cmd.Context().Err() != nil {
			err = cmd.Context().Err()
		}
		return run.result(err)
	}
	group.AddCommand(cmd)
	return group
}

func logUsage(message string) error { return usageError{errors.New(message)} }

type trainLogRun struct {
	options                   trainLogOptions
	api                       *platform.API
	cmd                       *cobra.Command
	format, task, job, source string
	steps                     logDownloadSteps
	items                     []*trainLogItem
	waited                    time.Duration
}

type trainLogItem struct {
	RoleID    string `json:"roleJobId,omitempty"`
	RoleType  string `json:"roleType,omitempty"`
	ArchiveID string `json:"archiveId,omitempty"`
	Status    string `json:"status"`
	Stage     string `json:"stage,omitempty"`
	Error     string `json:"error,omitempty"`
	File      string `json:"file,omitempty"`
	Bytes     *int64 `json:"bytes,omitempty"`
	row       platform.Record
}

func (r *trainLogRun) item(row platform.Record) *trainLogItem {
	i := &trainLogItem{row: row, RoleID: row.Text("roleJobId"), RoleType: row.Text("roleType"), ArchiveID: row.Text("archiveId")}
	r.items = append(r.items, i)
	return i
}

func (i *trainLogItem) fail(stage string, err error) {
	i.Status, i.Stage, i.Error = "failed", stage, err.Error()
}

func (r *trainLogRun) save(i *trainLogItem, link string) {
	parts := []string{r.job}
	for _, value := range []string{i.RoleID, i.ArchiveID} {
		if value != "" {
			parts = append(parts, value)
		}
	}
	name := platform.LogDownloadName(strings.Join(append(parts, r.options.kind), "-") + ".zip")
	file, size, err := r.steps.download(r.cmd.Context(), r.api, link, filepath.Join(r.options.directory, name), r.options.directory, name, "日志")
	if err != nil {
		i.fail(r.steps.stage, err)
		return
	}
	i.Status, i.File, i.Bytes, i.Stage, i.Error = "succeeded", file, &size, "", ""
}

func (r *trainLogRun) result(err error) error {
	status := "succeeded"
	counts := map[string]int{}
	for _, i := range r.items {
		counts[i.Status]++
	}
	switch {
	case err != nil:
		status = "failed"
	case counts["succeeded"] > 0 && counts["succeeded"] < len(r.items):
		status = "partial"
	case counts["failed"] > 0:
		status = "failed"
	case counts["wait_timeout"] > 0:
		status = "wait_timeout"
	case counts["not_ready"] > 0:
		status = "not_ready"
	case counts["archiving"] > 0 || len(r.items) == 0:
		status = "archiving"
	}
	result := map[string]any{"status": status, "source": r.source, "taskId": r.task, "jobId": r.job, "type": r.options.kind, "waitedSeconds": int(r.waited.Seconds()), "items": r.items}
	if err != nil {
		result["error"] = err.Error()
		result["stage"] = r.steps.stage
	}
	if r.format == "json" {
		if err := output.JSON(r.cmd.OutOrStdout(), result); err != nil {
			return err
		}
	} else {
		out := r.cmd.OutOrStdout()
		fmt.Fprintf(out, "任务 %s · 作业 %s · %s · %s\n", r.task, r.job, r.source, status)
		if len(r.items) > 0 {
			rows := make([][]string, 0, len(r.items))
			for _, item := range r.items {
				detail := item.File
				if item.Error != "" {
					detail = item.Error
				}
				rows = append(rows, []string{item.RoleID, item.RoleType, item.Status, detail})
			}
			if err := output.Table(out, []string{"角色作业 ID", "角色", "状态", "文件或原因"}, rows); err != nil {
				return err
			}
		}
	}
	if err != nil {
		// Preserve global handling of usage errors, interrupts and version denials.
		return err
	}
	switch status {
	case "failed", "partial", "wait_timeout":
		return silentExit(1)
	}
	return nil
}

func (r *trainLogRun) execute() error {
	ctx := r.cmd.Context()
	r.steps.start("query_instance", "查询当前任务及执行实例")
	task, err := r.api.TrainTask(ctx, r.task)
	if err != nil {
		return err
	}
	if task.Text("businessId") != r.api.BusinessID() {
		return errors.New("任务与当前业务不一致")
	}
	instances, err := r.api.AllTrainInstances(ctx, task)
	if err != nil {
		return err
	}
	job, err := chooseTrainJob(instances, r.job, false)
	if err != nil {
		return err
	}
	if job != nil {
		r.source, r.job = "running", job.Text("jobId")
		if job.Text("taskId") != r.task || job.Text("businessId") != r.api.BusinessID() {
			return errors.New("执行实例与当前任务或业务不一致")
		}
		if r.options.kind == "plog" {
			return logUsage("运行中作业不支持 plog")
		}
		rows, err := r.api.RunningLogArchives(ctx, r.task, r.job, func() { r.steps.start("archive_log", "请求当前作业的日志归档列表") })
		if err == nil {
			return r.running(rows, job.Text("jobType") == "dps-train" || task.Text("taskType") == "dps-train")
		}
		if !errors.Is(err, platform.ErrRunningInstanceGone) {
			return err
		}
	}
	if r.options.retry {
		return errors.New("重新下载的目标作业已不在执行实例中")
	}
	r.source = "history"
	r.steps.start("query_record", "查询历史执行记录")
	if r.job != "" {
		job, err = r.api.TrainHistoryRecord(ctx, r.task, r.job, "all")
	} else {
		job, err = r.latestHistory(ctx)
	}
	if err != nil {
		return err
	}
	if job == nil {
		return errors.New("当前任务没有可下载日志的作业")
	}
	for key, expected := range map[string]string{"taskId": r.task, "businessId": r.api.BusinessID()} {
		if id := job.Text(key); id != "" && id != expected {
			return fmt.Errorf("历史记录 %s 不匹配", key)
		}
	}
	r.job = job.Text("jobId")
	return r.history(job)
}

func chooseTrainJob(rows []platform.Record, id string, history bool) (platform.Record, error) {
	var latest platform.Record
	var stamp time.Time
	for _, row := range rows {
		job := row.Text("jobId")
		if job == "" {
			return nil, errors.New("执行记录缺少 jobId")
		}
		if id != "" {
			if job == id {
				return row, nil
			}
			continue
		}
		at, ok := recordTime(row["createTime"])
		if !ok && history {
			at, ok = recordTime(row["statusTime"])
		}
		if !ok && len(rows) > 1 {
			return nil, errors.New("时间缺失，无法确定最新作业，请指定 JOB_ID")
		}
		if latest == nil || at.After(stamp) || at.Equal(stamp) && job > latest.Text("jobId") {
			latest, stamp = row, at
		}
	}
	return latest, nil
}

func (r *trainLogRun) latestHistory(ctx context.Context) (platform.Record, error) {
	var rows []platform.Record
	seen := map[string]bool{}
	for page := 1; ; page++ {
		p, err := r.api.TrainHistory(ctx, r.task, page, 200, "all")
		if err != nil {
			return nil, err
		}
		for _, row := range p.Items {
			id := row.Text("jobId")
			if id == "" || seen[id] {
				return nil, errors.New("历史分页包含重复或无效作业")
			}
			seen[id] = true
			rows = append(rows, row)
		}
		if len(rows) >= p.Count {
			return chooseTrainJob(rows, "", true)
		}
		if len(p.Items) == 0 {
			return nil, errors.New("历史分页提前结束")
		}
	}
}
