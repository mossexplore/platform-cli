package command

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/edgelogin"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

type Options struct {
	Args    []string
	Version string
	Stdout  io.Writer
	Stderr  io.Writer
	Paths   func() (localstate.Paths, error)
}

type usageError struct{ error }

func Run(ctx context.Context, options Options) (code int) {
	if options.Paths == nil {
		options.Paths = localstate.DefaultPaths
	}
	root := newRoot(options)
	var invocation *historyInvocation
	root.PersistentPreRun = func(cmd *cobra.Command, args []string) {
		invocation = startHistory(cmd, options, args)
	}
	defer func() { invocation.finish(code, options) }()
	if err := root.ExecuteContext(ctx); err != nil {
		if errors.Is(err, context.Canceled) || errors.Is(ctx.Err(), context.Canceled) {
			fmt.Fprintln(options.Stderr, "[提示] 已取消操作")
			return 130
		}
		var silent silentExit
		if errors.As(err, &silent) {
			return int(silent)
		}
		fmt.Fprintln(options.Stderr, "[错误]", err)
		var usage usageError
		if errors.As(err, &usage) {
			return 2
		}
		return 1
	}
	return 0
}

func newRoot(options Options) *cobra.Command {
	root := &cobra.Command{
		Use: "ml", Short: "WiseRec 命令行工具，Go 客户端",
		Version: options.Version, SilenceErrors: true, SilenceUsage: true,
		DisableSuggestions: true,
	}
	root.CompletionOptions.DisableDefaultCmd = true
	root.SetVersionTemplate("ml {{.Version}}\n")
	root.PersistentFlags().Bool("no-history", false, "不保存本次命令历史")
	root.SetArgs(append([]string{}, options.Args...))
	root.SetOut(options.Stdout)
	root.SetErr(options.Stderr)
	root.SetFlagErrorFunc(func(_ *cobra.Command, err error) error {
		return usageError{err}
	})

	config := func() (localstate.Paths, localstate.Config, error) {
		paths, err := options.Paths()
		if err != nil {
			return localstate.Paths{}, localstate.Config{}, err
		}
		value, err := paths.LoadOrInitializeConfig()
		return paths, value, err
	}

	contextCommand := &cobra.Command{
		Use: "context", Short: "查看当前运行模式及生效配置路径", Args: maximumArgs(0),
		RunE: func(cmd *cobra.Command, _ []string) error {
			paths, cfg, err := config()
			if err != nil {
				return err
			}
			executable, err := os.Executable()
			if err != nil {
				return errors.New("无法定位 CLI 路径")
			}
			if resolved, err := filepath.EvalSymlinks(executable); err == nil {
				executable = resolved
			}
			result := output.Fields{
				{Key: "运行模式", Value: "Go CLI"},
				{Key: "当前环境", Value: cfg.Current},
				{Key: "平台地址", Value: cfg.Profile().PublicEndpoint()},
				{Key: "CLI 版本", Value: options.Version},
				{Key: "CLI 路径", Value: executable},
				{Key: "配置路径", Value: paths.Config()},
				{Key: "状态目录", Value: paths.Dir},
			}
			asJSON, _ := cmd.Flags().GetBool("json")
			if asJSON {
				return output.JSON(cmd.OutOrStdout(), result)
			}
			return result.Table(cmd.OutOrStdout())
		},
	}
	contextCommand.Flags().Bool("json", false, "输出 JSON")

	tree := &cobra.Command{
		Use: "tree", Short: "显示当前安装版本的完整命令树", Args: maximumArgs(0),
		RunE: func(cmd *cobra.Command, _ []string) error {
			paths, cfg, err := config()
			if err != nil {
				return err
			}
			all, _ := cmd.Flags().GetBool("all")
			return writeTree(cmd.OutOrStdout(), root, paths, cfg, all)
		},
	}
	tree.Flags().Bool("all", false, "展示全部命令及当前平台支持情况")

	showSecrets := false
	login := &cobra.Command{
		Use: "login", Short: "打开 Edge 登录并刷新当前环境的本地认证信息", Args: maximumArgs(0),
		RunE: func(cmd *cobra.Command, _ []string) error {
			paths, cfg, err := config()
			if err != nil {
				return err
			}
			result, err := edgelogin.Run(cmd.Context(), paths, cfg, cmd.ErrOrStderr())
			if err != nil {
				return err
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 登录成功，用户信息如下：")
			fields := output.Fields{
				{Key: "环境", Value: result.Environment},
				{Key: "账号", Value: result.Username},
				{Key: "中文名", Value: loginValue(result.ChineseName)},
				{Key: "部门", Value: loginValue(result.Department)},
				{Key: "businessId", Value: loginValue(result.BusinessID)},
			}
			if err := fields.Table(cmd.OutOrStdout()); err != nil {
				return err
			}
			if showSecrets {
				if err := result.PrintSecrets(cmd.OutOrStdout()); err != nil {
					return err
				}
			}
			startAutoPing(cmd, paths, cfg, options.Version, false)
			return nil
		},
	}
	login.Flags().BoolVar(&showSecrets, "show-secrets", false, "登录成功后显示完整 Cookie 和 CSRF Token")

	mep := &cobra.Command{Use: "mep", Short: "MEP 管理"}
	mepConfig := &cobra.Command{Use: "config", Short: "MEP 配置"}
	get := &cobra.Command{
		Use: "get [KEY]", Short: "查询一个 MEP 配置项", Args: maximumArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			paths, cfg, err := config()
			if err != nil {
				return err
			}
			format, _ := cmd.Flags().GetString("output")
			if format == "" {
				format = cfg.Profile().Output
			}
			format = strings.ToLower(format)
			if format != "table" && format != "json" {
				return usageError{errors.New("output 仅支持 table 或 json")}
			}
			key := platform.DefaultMEPKey
			if len(args) == 1 {
				key = args[0]
			}
			session := platform.Session{Paths: paths, Config: cfg, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
			result, err := session.QueryMEP(cmd.Context(), key)
			if err != nil {
				return err
			}
			if format == "json" {
				return output.JSON(cmd.OutOrStdout(), result)
			}
			return output.ResultTable(cmd.OutOrStdout(), result)
		},
	}
	get.Flags().StringP("output", "o", "", "输出格式 table 或 json")
	mepConfig.AddCommand(get)
	mep.AddCommand(mepConfig)
	auth, logout := newAuth(options, config)
	root.AddCommand(contextCommand, tree, login, logout, auth, mep, newTrain(options, config))
	root.AddCommand(newEnv(options, config), newBusiness(options, config), newUser(options, config), newAccess(options, config), newHistory(options))
	root.AddCommand(newDataset(options, config), newFeatureSet(options, config), newFeatureTask(options, config), newModel(options, config))
	root.AddCommand(newService(options, config), newQuality(options, config), newStudio(options, config), newJupyter(options, config))
	root.AddCommand(newTemplateGroup(options, config, false), newTemplateGroup(options, config, true), newSwanBoard(options, config), newAlgorithm(options, config), newOffline(options, config), newSample(options, config))
	return root
}

func maximumArgs(maximum int) cobra.PositionalArgs {
	return func(_ *cobra.Command, args []string) error {
		if len(args) > maximum {
			return usageError{fmt.Errorf("最多接受 %d 个位置参数", maximum)}
		}
		return nil
	}
}

func loginValue(value string) string {
	if value == "" {
		return "未获取"
	}
	return value
}
