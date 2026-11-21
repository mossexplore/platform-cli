package command

import (
	"fmt"
	"math"
	"strconv"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
)

func newAuth(options Options, load loadConfig) (*cobra.Command, *cobra.Command) {
	auth := &cobra.Command{Use: "auth", Short: "查看认证状态"}
	status := &cobra.Command{Use: "status", Short: "显示当前环境的认证有效期，不显示敏感值", Args: positional(0)}
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
		remaining := max(0, int(math.Ceil(time.Until(expires).Minutes())))
		state := "valid"
		if remaining == 0 {
			state = "expired"
		}
		fields := output.Fields{
			{Key: "profile", Value: creds.Profile}, {Key: "username", Value: creds.Username},
			{Key: "cn_name", Value: creds.ChineseName}, {Key: "department", Value: creds.Department},
			{Key: "businessId", Value: business}, {Key: "status", Value: state},
			{Key: "role", Value: creds.AdminRoleLabel()},
			{Key: "remaining_minutes", Value: strconv.Itoa(remaining)},
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
		if err := keepalive.Stop(paths, profile.Name, *all); err != nil {
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
