package command

import (
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func (r *trainLogRun) checkRunningItem(i *trainLogItem) {
	link, err := r.api.RunningDownloadURL(r.cmd.Context(), i.row, r.options.retry)
	switch {
	case errors.Is(err, platform.ErrLogNotReady):
		i.Status, i.Stage = "archiving", "get_download_url"
	case errors.Is(err, platform.ErrArchiveFailed):
		i.fail("archive_log", err)
		r.retrySuggested = !r.options.retry
	case err != nil:
		i.fail("get_download_url", err)
	default:
		r.save(i, link)
	}
}

func (r *trainLogRun) waitRunning(check func(*trainLogItem)) error {
	if !r.options.wait || r.options.noWait || r.options.timeout == 0 {
		return nil
	}
	ctx := r.cmd.Context()
	limit := time.Duration(r.options.timeout) * time.Second
	start := time.Now()
	deadline := start.Add(limit)
	for round := 1; ; round++ {
		var labels []string
		var pending []*trainLogItem
		for _, i := range r.items {
			if i.Status == "archiving" {
				pending = append(pending, i)
				labels = append(labels, r.logLabel(i))
			}
		}
		if len(pending) == 0 {
			return nil
		}
		remaining := max(0, time.Until(deadline))
		delay := min(remaining, time.Duration(r.options.interval)*time.Second)
		targets := strings.Join(labels, "、")
		r.showWait(delay, remaining, targets)
		timer := time.NewTimer(delay)
		select {
		case <-ctx.Done():
			timer.Stop()
			r.clearProgress()
			r.waited = min(time.Since(start), limit)
			return ctx.Err()
		case <-timer.C:
		}
		r.clearProgress()
		r.waited = min(time.Since(start), limit)
		if err := ctx.Err(); err != nil {
			return err
		}
		fmt.Fprintf(r.steps.out, "日志归档中，第 %d 次复查状态 · 已等待 %d 秒 · 正在查询 %s 的归档状态\n", round, int(r.waited/time.Second), targets)
		final := !time.Now().Before(deadline)
		for _, i := range pending {
			if err := ctx.Err(); err != nil {
				return err
			}
			check(i)
			if final && i.Status == "archiving" {
				i.Status, i.Stage, i.Error = "wait_timeout", "get_download_url", fmt.Sprintf("已等待 %d 秒，服务端仍在归档", r.options.timeout)
			}
		}
	}
}
