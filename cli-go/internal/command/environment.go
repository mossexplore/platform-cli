package command

import (
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newEnv(options Options, load loadConfig) *cobra.Command {
	env := &cobra.Command{Use: "env", Short: "管理运行环境"}
	list := &cobra.Command{Use: "list", Short: "列出已授权及授权状态未知的环境", Args: positional(0)}
	format := list.Flags().StringP("output", "o", "table", "输出格式为 table 或 json")
	list.RunE = func(cmd *cobra.Command, _ []string) error {
		selected := strings.ToLower(*format)
		if selected != "table" && selected != "json" {
			return usageError{errors.New("output 仅支持 table 或 json")}
		}
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		session := platform.Session{Paths: paths, Config: cfg, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
		statuses, accessErr := session.EnvironmentStatuses(cmd.Context(), accessAuditCommand(options.Args))
		if accessErr != nil {
			fmt.Fprintln(cmd.ErrOrStderr(), "[错误]", accessErr)
		}
		rows := []output.Fields{}
		currentRow := -1
		for _, profile := range cfg.Profiles {
			state := statuses[profile.Name]
			if state == "未授权" || errors.Is(accessErr, platform.ErrNoAccess) {
				continue
			}
			if state == "" {
				state = "授权状态未知"
			}
			marker := ""
			if cfg.Current == profile.Name {
				marker = "*"
				currentRow = len(rows)
			}
			platformName := "搜推广工程平台"
			if profile.PlatformType == "mlops" {
				platformName = "WiseMLOps平台"
			}
			rows = append(rows, output.Fields{{Key: "当前在用环境", Value: marker}, {Key: "环境标识", Value: profile.Name},
				{Key: "环境名", Value: labelOrID(profile.Alias, profile.Name)}, {Key: "管理台类型", Value: platformName},
				{Key: "管理台地址", Value: profile.PublicEndpoint()}, {Key: "状态", Value: state}})
		}
		if len(rows) == 0 && selected == "table" {
			_, err := fmt.Fprintln(cmd.ErrOrStderr(), "[提示] 暂无已授权环境")
			return err
		}
		return renderEnvironmentList(cmd, selected, rows, currentRow)
	}
	show := &cobra.Command{Use: "show", Short: "显示当前环境", Args: positional(0)}
	show.RunE = func(cmd *cobra.Command, _ []string) error {
		_, cfg, err := load()
		if err != nil {
			return err
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		verify := profile.VerifyTLS
		if verify == nil {
			verify = cfg.API.VerifyTLS
		}
		tls := "True"
		if verify != nil && !*verify {
			tls = "False"
		}
		fields := output.Fields{{Key: "name", Value: profile.Name}, {Key: "platform_type", Value: profile.PlatformType},
			{Key: "api_endpoint", Value: profile.PublicEndpoint()}, {Key: "base_url", Value: profile.Origin()},
			{Key: "output_format", Value: profile.Output}, {Key: "verify_ssl", Value: tls}}
		return fields.Table(cmd.OutOrStdout())
	}
	use := &cobra.Command{Use: "use NAME", Short: "切换当前环境", Args: positional(1)}
	use.RunE = func(cmd *cobra.Command, args []string) error {
		paths, err := options.Paths()
		if err != nil {
			return err
		}
		if err := paths.ValidateSession(); err != nil {
			return err
		}
		prevCurrent := ""
		if prevCfg, err := paths.LoadOrInitializeConfig(); err == nil {
			prevCurrent = prevCfg.Current
		}
		profile, err := paths.UseEnvironment(args[0])
		if err != nil {
			return err
		}
		cfg, err := paths.LoadOrInitializeConfig()
		if err != nil {
			return err
		}
		cfg.Current = profile.Name
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 当前环境已切换为: "+profile.Name)
		if paths.IsSessionIsolated() {
			if creds, err := paths.CredentialsFor(profile); err == nil {
				if _, err := paths.SelectedBusiness(creds); err != nil {
					fmt.Fprintf(cmd.ErrOrStderr(), "[提示] 当前会话在环境 %s 下尚未选择业务，请运行 ml business <租户ID>\n", profile.Name)
				}
			}
			if paths.Session.Mode == localstate.SessionModeDSH {
				return nil
			}
			if prevCurrent == profile.Name {
				prevCurrent = ""
			}
			message, err := keepalive.SyncEnvironment(paths, cfg, prevCurrent, options.Version, cfg.PingEnabled() && canStartPing(cmd, paths))
			switch {
			case errors.Is(err, localstate.ErrLockBusy), errors.Is(err, keepalive.ErrRegistrationPending):
				fmt.Fprintln(cmd.ErrOrStderr(), "[提示] 环境已切换，保活登记待重试：", err)
			case err != nil:
				fmt.Fprintln(cmd.ErrOrStderr(), "[警告] 环境已切换，自动保活登记失败：", err)
			case message != "":
				fmt.Fprintln(cmd.ErrOrStderr(), message)
			}
			return nil
		}
		if prevCurrent != "" && prevCurrent != profile.Name && fromTerminal(cmd) {
			_ = keepalive.DetachTerminal(paths, prevCurrent)
		}
		startAutoPing(cmd, paths, cfg, options.Version, true)
		return nil
	}
	env.AddCommand(list, show, use)
	return env
}

func renderEnvironmentList(cmd *cobra.Command, format string, rows []output.Fields, currentRow int) error {
	if format == "json" {
		return output.JSON(cmd.OutOrStdout(), rows)
	}
	headers := make([]string, 0, len(rows[0]))
	for _, field := range rows[0] {
		headers = append(headers, field.Key)
	}
	values := make([][]string, 0, len(rows))
	for _, row := range rows {
		cells := make([]string, 0, len(row))
		for _, field := range row {
			cells = append(cells, field.Value)
		}
		values = append(values, cells)
	}
	return output.HighlightedTable(cmd.OutOrStdout(), headers, values, currentRow)
}

func labelOrID(label, id string) string {
	if label != "" {
		return label
	}
	return id
}

func newUser(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "user", Short: "用户信息"}
	info := &cobra.Command{Use: "info", Short: "查询当前登录用户信息", Args: positional(0)}
	outputFlag(info)
	info.RunE = authorized(options, load, func(cmd *cobra.Command, _ []string, api *platform.API, format string) error {
		payload, err := api.JSON(cmd.Context(), http.MethodGet, "/ai/user/info", nil, nil)
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), payload)
		}
		return output.ResultTable(cmd.OutOrStdout(), payload)
	})
	group.AddCommand(info)
	return group
}

func newAccess(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "access", Short: "检查 CLI 在线访问授权"}
	status := &cobra.Command{Use: "status", Short: "实时检查当前平台账号及环境的访问授权", Args: positional(0)}
	diagnose := status.Flags().Bool("diagnose", false, "显示权限请求配置和耗时，不输出凭据")
	status.RunE = func(cmd *cobra.Command, args []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if _, err := cfg.RequireProfile(); err != nil {
			return err
		}
		if *diagnose {
			fmt.Fprintf(cmd.ErrOrStderr(), "CLI 版本：%s\n配置文件：%s\n证书来源：%s\n", options.Version, paths.Config(), cfg.Access.CASource)
		}
		if !cfg.Access.Active() {
			_, err = fmt.Fprintln(cmd.ErrOrStderr(), "已关闭在线权限检查。")
			return err
		}
		return authorized(options, func() (localstate.Paths, localstate.Config, error) { return paths, cfg, nil },
			func(cmd *cobra.Command, _ []string, _ *platform.API, _ string) error {
				_, err := fmt.Fprintln(cmd.OutOrStdout(), "当前账号已获当前环境访问授权。")
				return err
			})(cmd, args)
	}
	group.AddCommand(status)
	return group
}
