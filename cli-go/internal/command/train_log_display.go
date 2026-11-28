package command

import (
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"golang.org/x/term"
)

var errLogSelectionCancelled = errors.New("已取消选择")

func renderRunningLogRoles(out io.Writer, order []string, groups map[string][]platform.Record) error {
	var rows [][]string
	for n, id := range order {
		group := groups[id]
		row, err := latestArchive(group)
		status, reason, start, end := "无法选择", "-", "-", "-"
		if err != nil {
			reason = err.Error()
		} else {
			status = map[string]string{"0": "归档中", "1": "归档成功", "2": "归档失败"}[string(row["status"])]
			if status == "" {
				status = "未知状态"
			}
			reason, start, end = fieldText(row["statusReason"]), dateText(row["createTime"]), dateText(row["updateTime"])
		}
		rows = append(rows, []string{strconv.Itoa(n + 1), id, fieldText(group[0]["roleType"]), status, reason, start, end})
	}
	return output.Table(out, []string{"编号", "roleJobId", "角色", "归档状态", "原因", "开始时间", "结束时间"}, rows, 1, 3, 5, 6)
}

var logResultLabels = map[string]string{
	"succeeded": "下载成功", "partial": "部分成功", "failed": "失败", "not_ready": "日志未就绪", "wait_timeout": "等待超时", "archiving": "归档中",
}

func (r *trainLogRun) renderResult(out io.Writer, status string, succeeded int) error {
	source := map[string]string{"running": "执行实例", "history": "历史作业"}[r.source]
	fmt.Fprintf(out, "下载结果 · %s · 已下载 %d/%d\n", logResultLabels[status], succeeded, len(r.items))
	if r.job != "" {
		fmt.Fprintf(out, "%s 作业ID：%s\n", source, r.job)
	}
	if len(r.items) == 0 {
		return nil
	}
	headers := []string{}
	if r.distributed {
		headers = append(headers, "角色作业 ID", "角色")
	}
	if r.options.retry {
		headers = append(headers, "archiveId")
	}
	headers = append(headers, "结果", "大小", "文件或原因")
	var rows [][]string
	for _, i := range r.items {
		row := []string{}
		if r.distributed {
			row = append(row, i.RoleID, i.RoleType)
		}
		if r.options.retry {
			row = append(row, i.ArchiveID)
		}
		size, detail := "-", i.File
		if i.Bytes != nil {
			size = logByteSize(*i.Bytes)
		}
		if i.Error != "" {
			detail = i.Error
		}
		if detail == "" {
			detail = "-"
		}
		label := logResultLabels[i.Status]
		if i.Status == "failed" && i.Stage == "archive_log" {
			label = "归档失败"
		}
		rows = append(rows, append(row, label, size, detail))
	}
	return output.Table(out, headers, rows)
}

func (r *trainLogRun) retryCommand() string {
	quote := func(value string) string {
		if runtime.GOOS == "windows" { // Training examples use PowerShell.
			return "'" + strings.ReplaceAll(value, "'", "''") + "'"
		}
		return quoteCommandArg(value)
	}
	cmd := "ml train logs download " + quote(r.task) + " " + quote(r.job) + " --retry --directory " + quote(r.options.directory)
	if agentMode(r.cmd) {
		cmd += " --agent"
	}
	return cmd
}

func logByteSize(n int64) string { return readableBytes(strconv.FormatInt(n, 10)) }

func (r *trainLogRun) progressTTY() bool {
	file, ok := r.steps.out.(*os.File)
	return ok && term.IsTerminal(int(file.Fd()))
}

func (r *trainLogRun) progress(message string) {
	if r.progressTTY() {
		fmt.Fprintf(r.steps.out, "\r\033[2K%s", message)
	} else {
		fmt.Fprintln(r.steps.out, message)
	}
}

func (r *trainLogRun) clearProgress() {
	if r.progressTTY() {
		fmt.Fprint(r.steps.out, "\r\033[2K")
	}
}

func (r *trainLogRun) showWait(delay, remaining time.Duration, targets string) {
	downloaded := 0
	for _, i := range r.items {
		if i.Status == "succeeded" {
			downloaded++
		}
	}
	r.progress(fmt.Sprintf("已下载 %d/%d · 等待 %s · %.0f 秒后重查 · 剩余 %.0f 秒", downloaded, len(r.items), targets, math.Ceil(delay.Seconds()), math.Ceil(remaining.Seconds())))
}

func (r *trainLogRun) logLabel(i *trainLogItem) string {
	if i.RoleType != "" {
		return i.RoleType
	}
	if i.RoleID != "" {
		return i.RoleID
	}
	return r.job
}

func (r *trainLogRun) downloadFile(i *trainLogItem, link, name string) (string, int64, error) {
	r.steps.stage = "validate_download_url"
	label := "正在下载 " + r.logLabel(i)
	events := platform.LogDownloadEvents{Start: func() {
		r.steps.stage = "download_file"
		r.progress(label)
	}}
	if r.progressTTY() {
		var last time.Time
		events.Progress = func(received, total int64) {
			if received != total && time.Since(last) < 250*time.Millisecond {
				return
			}
			last = time.Now()
			message := label + " · " + logByteSize(received)
			if total >= 0 {
				message += " / " + logByteSize(total)
			}
			r.progress(message)
		}
		defer r.clearProgress()
	}
	dir := r.options.directory
	return r.api.SignedLogDownload(r.cmd.Context(), link, filepath.Join(dir, name), dir, name, events)
}
