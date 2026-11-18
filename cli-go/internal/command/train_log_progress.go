package command

import (
	"context"
	"fmt"
	"io"
	"os"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"golang.org/x/term"
)

var logStageNames = map[string]string{
	"query_record":          "查询执行记录",
	"query_instance":        "查询执行实例",
	"select_role":           "选择日志角色",
	"select_log":            "选择归档日志",
	"validate_role":         "校验角色信息",
	"check_log":             "查询日志是否存在",
	"archive_log":           "归档日志",
	"get_download_url":      "获取下载地址",
	"validate_download_url": "校验下载地址",
	"download_file":         "下载日志文件",
}

type logDownloadSteps struct {
	out    io.Writer
	number int
	stage  string
}

func (s *logDownloadSteps) start(stage, message string) {
	s.stage = stage
	s.note(message)
}

func (s *logDownloadSteps) note(message string) {
	s.number++
	fmt.Fprintf(s.out, "[%d] %s\n", s.number, message)
}

func (s *logDownloadSteps) failure(err error) error {
	return fmt.Errorf("[%d] 阶段「%s」失败：%w", s.number, logStageNames[s.stage], err)
}

func (s *logDownloadSteps) failItem(item map[string]any, err error) {
	message := s.failure(err).Error()
	item["status"], item["stage"], item["error"] = "failed", s.stage, message
	fmt.Fprintln(s.out, message)
}

func (s *logDownloadSteps) download(ctx context.Context, api *platform.API, link, destination, directory, name, label string) (string, int64, error) {
	s.start("validate_download_url", "开始校验下载地址")
	events := platform.LogDownloadEvents{
		Start: func() { s.start("download_file", "开始下载 "+label) },
	}
	var lastReport time.Time
	if file, ok := s.out.(*os.File); ok && term.IsTerminal(int(file.Fd())) {
		events.Progress = func(received, total int64) {
			now := time.Now()
			if received != total && now.Sub(lastReport) < 250*time.Millisecond {
				return
			}
			lastReport = now
			if total >= 0 {
				fmt.Fprintf(s.out, "\r已接收 %d/%d 字节", received, total)
			} else {
				fmt.Fprintf(s.out, "\r已接收 %d 字节", received)
			}
		}
	}
	path, size, err := api.SignedLogDownload(ctx, link, destination, directory, name, events)
	if !lastReport.IsZero() {
		fmt.Fprintln(s.out)
	}
	if err == nil {
		s.note(fmt.Sprintf("%s下载完成，保存到：%s，共 %d 字节", label, path, size))
	}
	return path, size, err
}
