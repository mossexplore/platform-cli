package command

import (
	"context"
	"errors"
	"fmt"
	"os"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"golang.org/x/term"
)

func (r *trainLogRun) selectRoles(rows []platform.Record, distributed bool) ([]platform.Record, error) {
	o := r.options
	if o.retry {
		return rows, nil
	}
	if !distributed && (o.all || len(o.roles) > 0) {
		return nil, logUsage("单机作业不接受 --all 或 --role-job-id")
	}
	if len(rows) == 0 {
		return rows, nil
	}
	order := []string{}
	byRole := map[string][]platform.Record{}
	for _, row := range rows {
		id := row.Text("roleJobId")
		if distributed && id == "" {
			return nil, errors.New("角色记录缺少 roleJobId")
		}
		if _, ok := byRole[id]; !ok {
			order = append(order, id)
		}
		byRole[id] = append(byRole[id], row)
	}
	if distributed && r.source == "running" {
		if err := renderRunningLogRoles(r.steps.out, order, byRole); err != nil {
			return nil, err
		}
	}
	if o.all {
		return rows, nil
	}
	ids := o.roles
	if len(ids) == 0 {
		if len(order) == 1 {
			return rows, nil
		}
		input, ok := r.cmd.InOrStdin().(*os.File)
		if r.format == "json" || !ok || !term.IsTerminal(int(input.Fd())) {
			return nil, logUsage("请使用 --role-job-id 选择角色，或使用 --all")
		}
		indices, err := selectTrainLogInputs(r.cmd, "", false, len(order), func(int) bool { return true })
		if err != nil {
			return nil, err
		}
		if len(indices) == 0 {
			return nil, errLogSelectionCancelled
		}
		for _, idx := range indices {
			ids = append(ids, order[idx])
		}
	}
	var selected []platform.Record
	seen := map[string]bool{}
	for _, id := range ids {
		if len(byRole[id]) == 0 {
			return nil, logUsage("作业中没有角色 " + id)
		}
		if !seen[id] {
			selected = append(selected, byRole[id]...)
			seen[id] = true
		}
	}
	return selected, nil
}

func latestArchive(rows []platform.Record) (platform.Record, error) {
	if len(rows) == 1 {
		return rows[0], nil
	}
	var best platform.Record
	var stamp time.Time
	ambiguous := false
	var ids []string
	for _, row := range rows {
		ids = append(ids, row.Text("archiveId"))
	}
	for _, row := range rows {
		at, ok := recordTime(row["createTime"])
		if !ok {
			return nil, fmt.Errorf("归档时间无效，候选 archiveId: %s", strings.Join(ids, ", "))
		}
		if best == nil || at.After(stamp) {
			best, stamp, ambiguous = row, at, false
		} else if at.Equal(stamp) && row.Text("archiveId") != best.Text("archiveId") {
			ambiguous = true
		}
	}
	if ambiguous {
		return nil, fmt.Errorf("多份归档并列最新，候选 archiveId: %s", strings.Join(ids, ", "))
	}
	return best, nil
}

func (r *trainLogRun) running(rows []platform.Record, distributed bool) error {
	groups := map[string][]platform.Record{}
	for _, row := range rows {
		id := row.Text("roleJobId")
		groups[id] = append(groups[id], row)
	}
	r.distributed = distributed || len(groups) > 1
	selected, err := r.selectRoles(rows, r.distributed)
	if err != nil {
		return err
	}
	for _, row := range selected {
		if err := r.cmd.Context().Err(); err != nil {
			return err
		}
		if !r.options.retry {
			id := row.Text("roleJobId")
			group := groups[id]
			if len(group) == 0 {
				continue
			}
			delete(groups, id)
			chosen, err := latestArchive(group)
			if err != nil {
				i := r.item(row)
				i.ArchiveID = ""
				i.fail("select_log", err)
				continue
			}
			row = chosen
		}
		i := r.item(row)
		switch string(row["status"]) {
		case "0":
			i.Status = "archiving"
			continue
		case "1":
		case "2":
			if !r.options.retry {
				i.fail("archive_log", fmt.Errorf("归档失败：%s", fieldText(row["statusReason"])))
				r.retrySuggested = true
				continue
			}
		default:
			i.fail("archive_log", errors.New("无法识别归档状态"))
			continue
		}
		link, err := r.api.RunningDownloadURL(r.cmd.Context(), row, r.options.retry)
		if errors.Is(err, platform.ErrLogNotReady) {
			i.Status = "archiving"
			continue
		}
		if err != nil {
			i.fail("get_download_url", err)
			continue
		}
		r.save(i, link)
	}
	return nil
}

func (r *trainLogRun) history(job platform.Record) error {
	rows := []platform.Record{job}
	distributed := job.Text("jobType") == "dps-train"
	r.distributed = distributed
	if err := renderRecordTable(r.steps.out, trainHistoryColumns, rows, trainHistoryValue); err != nil {
		return err
	}
	if distributed {
		var err error
		rows, err = responseRecords(job, "roleJobInfo")
		if err != nil {
			return err
		}
		if len(rows) == 0 {
			return errors.New("作业没有可下载的角色日志")
		}
		if err := renderTrainHistoryLogRoles(r.steps.out, rows); err != nil {
			return err
		}
	}
	rows, err := r.selectRoles(rows, distributed)
	if err != nil {
		return err
	}
	seen := map[string]bool{}
	for _, row := range rows {
		id := row.Text("roleJobId")
		if distributed && (id == "" || seen[id] || row.Text("taskId") != r.task || row.Text("jobId") != r.job || (row.Text("businessId") != "" && row.Text("businessId") != r.api.BusinessID())) {
			return errors.New("所选角色标识重复、缺失或归属不匹配")
		}
		seen[id] = true
		r.item(row)
	}
	return r.pollHistory(func(ctx context.Context, item *trainLogItem) (string, error) {
		return r.api.HistoryLogURL(ctx, r.task, r.job, item.RoleID, r.options.kind == "plog", func(stage, _ string) { r.steps.stage = stage })
	}, r.save)
}

func (r *trainLogRun) pollHistory(lookup func(context.Context, *trainLogItem) (string, error), save func(*trainLogItem, string)) error {
	ctx := r.cmd.Context()
	queryCtx := ctx
	var start, deadline time.Time
	defer func() {
		if !start.IsZero() {
			r.waited = min(time.Since(start), deadline.Sub(start))
		}
	}()
	wait := r.options.wait && !r.options.noWait && r.options.timeout > 0
	for {
		pending := false
		for _, i := range r.items {
			if err := ctx.Err(); err != nil {
				return err
			}
			if i.Status != "" && i.Status != "not_ready" {
				continue
			}
			if queryCtx.Err() != nil {
				i.Status, i.Stage, i.Error = "wait_timeout", "check_log", "等待日志可用超时"
				continue
			}
			plog := r.options.kind == "plog"
			if plog && !platform.HasPlog(i.row) {
				i.fail("validate_role", errors.New("该记录没有 plog 日志"))
				continue
			}
			link, err := lookup(queryCtx, i)
			switch {
			case queryCtx.Err() != nil:
				if ctx.Err() != nil {
					return ctx.Err()
				}
				i.Status, i.Stage, i.Error = "wait_timeout", r.steps.stage, "等待日志可用超时"
			case errors.Is(err, platform.ErrLogNotReady):
				i.Status, i.Stage = "not_ready", r.steps.stage
				pending = true
				if wait && start.IsZero() {
					start = time.Now()
					deadline = start.Add(time.Duration(r.options.timeout) * time.Second)
					var cancel context.CancelFunc
					queryCtx, cancel = context.WithDeadline(ctx, deadline)
					defer cancel()
				}
			case err != nil:
				i.fail(r.steps.stage, err)
			default:
				save(i, link)
			}
		}
		if !pending || !wait {
			return nil
		}
		remaining := max(0, time.Until(deadline))
		delay := min(time.Duration(r.options.interval)*time.Second, remaining)
		r.showWait(delay, remaining)
		timer := time.NewTimer(delay)
		select {
		case <-timer.C:
		case <-queryCtx.Done():
			timer.Stop()
		}
		r.clearProgress()
	}
}
