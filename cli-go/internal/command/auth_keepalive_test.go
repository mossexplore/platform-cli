package command

import (
	"fmt"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestAuthKeepaliveNote(t *testing.T) {
	now := time.Date(2026, 11, 21, 6, 32, 0, 0, time.UTC)
	interval := 10 * time.Minute
	for _, tt := range []struct {
		name    string
		entry   keepalive.Entry
		running bool
		want    string
	}{
		{"scheduled", keepalive.Entry{Status: "running", LastActivity: now.Add(-2 * time.Minute)}, true,
			"自动保活运行中，下次预计保活时间：\n2026-11-21 14:40:00"},
		{"due", keepalive.Entry{Status: "running", LastActivity: now.Add(-interval)}, true,
			"自动保活运行中，等待发起请求"},
		{"unknown time", keepalive.Entry{Status: "running"}, true, "自动保活运行中，暂无预计时间"},
		{"retrying", keepalive.Entry{Status: "retrying", LastActivity: now}, true, "自动保活重试中"},
		{"waiting", keepalive.Entry{Status: "waiting"}, true, "自动保活等待有效业务上下文"},
		{"requesting", keepalive.Entry{Status: "requesting"}, true, "自动保活请求中"},
		{"starting", keepalive.Entry{Status: "starting"}, true, "自动保活正在启动"},
		{"manual stop", keepalive.Entry{Status: "running", ManualStop: true}, true, "自动保活已开启，当前未运行"},
		{"stopped", keepalive.Entry{Status: "running", LastActivity: now}, false, "自动保活已开启，当前未运行"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			if got := authKeepaliveNote(tt.entry, tt.running, interval, now); got != tt.want {
				t.Fatalf("got %q, want %q", got, tt.want)
			}
		})
	}
}

func TestAuthStatusShowsKeepaliveInRemainingTime(t *testing.T) {
	for _, tt := range []struct {
		name    string
		enabled bool
		corrupt bool
		want    string
	}{
		{"enabled", true, false, "分钟（自动保活已开启，当前未运行）"},
		{"disabled", false, false, ""},
		{"unavailable", true, true, "分钟（自动保活状态暂不可用）"},
	} {
		t.Run(tt.name, func(t *testing.T) {
			config := fmt.Sprintf(`{
				"current":"dev",
				"profiles":[{"name":"dev","api_endpoint":"https://preview.example.test"}],
				"auth":{"auto_ping":%t}
			}`, tt.enabled)
			paths, err := localstate.NewPaths(t.TempDir(), []byte(config))
			if err != nil {
				t.Fatal(err)
			}
			saveSharedEnvState(t, paths, "dev", "https://preview.example.test", "alice")
			if tt.corrupt {
				if err := localstate.WritePrivate(filepath.Join(paths.Dir, "ping-go.json"), []byte("{")); err != nil {
					t.Fatal(err)
				}
			}
			code, stdout, stderr := run(t, paths, "auth", "status")
			if code != 0 {
				t.Fatalf("auth status failed: %d, %s", code, stderr)
			}
			for _, line := range strings.Split(stdout, "\n") {
				if strings.Contains(line, "remaining_minutes") {
					if tt.enabled && !strings.Contains(line, tt.want) || !tt.enabled && strings.Contains(line, "自动保活") {
						t.Fatalf("unexpected remaining time: %s", line)
					}
					return
				}
			}
			t.Fatalf("remaining_minutes missing: %s", stdout)
		})
	}
}
