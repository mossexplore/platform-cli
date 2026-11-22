package command

import (
	"fmt"
	"math"
	"strconv"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
)

func newAuth(options Options, load loadConfig) (*cobra.Command, *cobra.Command) {
	auth := &cobra.Command{Use: "auth", Short: "查看认证状态"}
	status := &cobra.Command{Use: "status", Short: "查看当前环境的认证有效期和保活状态", Args: positional(0)}
	status.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		creds, err := paths.CredentialsFor(profile)
		if err != nil {
			return err
		}
		expires, err := creds.Expiry()
		if err != nil {
			return err
		}
		acquired, err := creds.Acquired()
		if err != nil {
			acquired = expires.Add(-time.Duration(cfg.Auth.TTLSeconds) * time.Second)
		}
		business, err := paths.SelectedBusiness(creds)
		if err != nil {
			business = "-"
		}
		now := time.Now()
		remaining := max(0, int(math.Ceil(expires.Sub(now).Minutes())))
		state := "valid"
		if remaining == 0 {
			state = "expired"
		}
		remainingText := strconv.Itoa(remaining)
		if cfg.PingEnabled() {
			interval := time.Duration(cfg.Auth.PingMinutes) * time.Minute
			note := "自动保活状态暂不可用"
			if paths.Session.Mode == localstate.SessionModeDSH {
				if host, err := keepalive.ViewHost(paths, cfg, now); err == nil {
					note = host.State
					if !host.Next.IsZero() {
						note += "，下次可探活时间：\n" + pingTime(host.Next)
					}
				}
			} else if entry, running, err := keepalive.View(paths, profile.Name); err == nil {
				running = running && len(entry.Owner) > 0 && entry.Endpoint == profile.Origin() && entry.Username == creds.Username
				note = authKeepaliveNote(entry, running, interval, now)
			}
			remainingText += " 分钟（" + note + "）"
		}
		fields := output.Fields{
			{Key: "profile", Value: creds.Profile}, {Key: "username", Value: creds.Username},
			{Key: "cn_name", Value: creds.ChineseName}, {Key: "department", Value: creds.Department},
			{Key: "businessId", Value: business}, {Key: "status", Value: state},
			{Key: "role", Value: creds.AdminRoleLabel()},
			{Key: "remaining_minutes", Value: remainingText},
			{Key: "acquired_at", Value: acquired.In(beijing).Format("2006-01-02 15:04:05")},
			{Key: "expires_at", Value: expires.In(beijing).Format("2006-01-02 15:04:05")},
			{Key: "timezone", Value: "Asia/Shanghai"},
		}
		return fields.Table(cmd.OutOrStdout())
	}
	auth.AddCommand(status, newPing(options, load))
	logout := &cobra.Command{Use: "logout", Short: "清除当前环境的本地认证信息", Args: positional(0)}
	all := logout.Flags().Bool("all", false, "清除所有环境的本地认证信息")
	forget := logout.Flags().Bool("forget-browser", false, "同时清除专用 Edge Profile")
	logout.RunE = func(cmd *cobra.Command, _ []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		profile := cfg.Profile()
		if !*all {
			profile, err = cfg.RequireProfile()
			if err != nil {
				return err
			}
		}
		if *all {
			err = keepalive.StopAll(paths, cfg.Profiles)
		} else {
			err = keepalive.Stop(paths, profile.Name)
		}
		if err != nil {
			return err
		}
		if err := paths.Logout(profile, *all, *forget); err != nil {
			return err
		}
		target := profile.Name
		if *all {
			target = "所有环境"
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 已清除 %s 的本地认证信息\n", target)
		if *forget {
			fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 已清除 %s 的专用 Edge Profile\n", target)
		}
		return nil
	}
	return auth, logout
}

func authKeepaliveNote(entry keepalive.Entry, running bool, interval time.Duration, now time.Time) string {
	if !running || entry.ManualStop {
		return "自动保活已开启，当前未运行"
	}
	switch entry.Status {
	case keepalive.WorkerStandby:
		return workerStandbyLabel
	case "retrying":
		return "自动保活重试中"
	case "waiting":
		return "自动保活等待有效业务上下文"
	case "starting":
		return "自动保活正在启动"
	case "requesting":
		return "自动保活请求中"
	case "running":
		next := nextPingTime(entry, interval)
		if next.After(now) {
			return "自动保活运行中，下次预计保活时间：\n" + pingTime(next)
		}
		if !next.IsZero() {
			return "自动保活运行中，等待发起请求"
		}
		return "自动保活运行中，暂无预计时间"
	default:
		return "自动保活已开启，当前未运行"
	}
}
