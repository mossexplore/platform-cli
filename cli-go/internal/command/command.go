package command

import (
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/edgelogin"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/mossexplore/platform-cli/cli-go/internal/updater"
	"github.com/spf13/cobra"
)

type Options struct {
	Args       []string
	Version    string
	Stdout     io.Writer
	Stderr     io.Writer
	Paths      func() (localstate.Paths, error)
	KBSettings func() (localstate.KnowledgeBase, error)
}

type usageError struct{ error }

func Run(ctx context.Context, options Options) (code int) {
	if options.Paths == nil {
		options.Paths = localstate.DefaultPaths
		options.KBSettings = func() (localstate.KnowledgeBase, error) {
			paths, err := localstate.DefaultPaths()
			if err != nil {
				return localstate.KnowledgeBase{}, err
			}
			return paths.KBSettings()
		}
	}
	root := newRoot(options)
	var invocation *historyInvocation
	root.PersistentPreRunE = func(cmd *cobra.Command, args []string) error {
		if err := setupAgent(cmd, args); err != nil {
			return err
		}
		invocation = startHistory(cmd, options)
		return nil
	}
	defer func() { invocation.finish(code, options) }()
	executed, err := root.ExecuteContextC(ctx)
	if err != nil {
		if errors.Is(err, context.Canceled) || errors.Is(ctx.Err(), context.Canceled) {
			fmt.Fprintln(options.Stderr, "[提示] 已取消操作")
			return 130
		}
		var silent silentExit
		if errors.As(err, &silent) {
			return int(silent)
		}
		fmt.Fprintln(options.Stderr, "[错误]", err)
		var denial *platform.VersionDenial
		if errors.As(err, &denial) && denial.Code == "CLI_VERSION_TOO_OLD" {
			cmd := executed
			if cmd != nil {
				format := ""
				if cmd.Flags().Changed("output") {
					format, _ = cmd.Flags().GetString("output")
				}
				jsonOutput, _ := cmd.Flags().GetBool("json")
				noInput, _ := cmd.Flags().GetBool("no-input")
				if !agentRequested(cmd) && !jsonOutput && !noInput && !strings.EqualFold(format, "json") {
					updater.Offer(ctx, cmd.InOrStdin(), options.Stdout, options.Stderr, options.Paths, format, denial)
				}
			}
		}
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
	root.PersistentFlags().Bool("agent", false, "输出适合 Agent 的紧凑 JSON（ML_AGENT=1 可设为默认）")
	root.CompletionOptions.DisableDefaultCmd = true
	root.SetHelpFunc(showHelp)
	addCompletionOptions(root)
	root.SetVersionTemplate("ml {{.Version}}\n")
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
			session, _, err := paths.LoadSessionState()
			if err != nil {
				return err
			}
			currentEnv := cfg.Current
			if currentEnv == "" {
				currentEnv = "未绑定"
			}
			sessionID, sessionFile := "-", "-"
			if paths.IsSessionIsolated() {
				sessionID = paths.Session.ID
				sessionFile = paths.SessionFile()
			}
			currentBusiness, currentTenant, loginStatus := contextBusiness(paths, cfg)
			if paths.IsSessionIsolated() {
				latest, _, err := paths.LoadSessionState()
				if err != nil {
					return err
				}
				if (cfg.Current != "" && session.Current != cfg.Current) ||
					latest.Current != session.Current || !latest.UpdatedAt.Equal(session.UpdatedAt) {
					return errors.New("读取期间当前会话上下文已变化，请重试")
				}
			}
			result := output.Fields{
				{Key: "运行模式", Value: "Go CLI"},
				{Key: "上下文模式", Value: paths.Session.Label()},
				{Key: "会话 ID", Value: sessionID},
				{Key: "当前环境", Value: currentEnv},
				{Key: "当前业务", Value: currentBusiness},
				{Key: "登录状态", Value: loginStatus},
				{Key: "当前租户", Value: currentTenant},
				{Key: "CLI 版本", Value: options.Version},
				{Key: "CLI 路径", Value: executable},
				{Key: "配置路径", Value: paths.Config()},
				{Key: "会话文件", Value: sessionFile},
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
			if _, err := cfg.RequireProfile(); err != nil {
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
				{Key: "权限角色", Value: result.AdminRole},
				{Key: "businessId", Value: loginValue(result.BusinessID)},
			}
			if showSecrets && agentMode(cmd) {
				cookie, csrf := result.Secrets()
				fields = append(fields, output.Field{Key: "cookie", Value: cookie}, output.Field{Key: "csrftoken", Value: csrf})
			}
			if err := fields.Table(cmd.OutOrStdout()); err != nil {
				return err
			}
			if showSecrets && !agentMode(cmd) {
				if err := result.PrintSecrets(cmd.OutOrStdout()); err != nil {
					return err
				}
			}
			startAutoPing(cmd, paths, cfg, options.Version, false)
			maintainSessionFiles(paths)
			return nil
		},
	}
	login.Flags().BoolVar(&showSecrets, "show-secrets", false, "登录成功后显示完整 Cookie 和 CSRF Token")

	auth, logout := newAuth(options, config)
	root.AddCommand(contextCommand, tree, login, logout, auth, newTrain(options, config))
	root.AddCommand(newEnv(options, config), newBusiness(options, config), newUser(options, config), newAccess(options, config), newHistory(options))
	root.AddCommand(newDataset(options, config), newFeatureSet(options, config), newFeatureTask(options, config), newModel(options, config))
	root.AddCommand(newService(options, config), newQuality(options, config), newStudio(options, config), newJupyter(options, config))
	root.AddCommand(newTemplateGroup(options, config, false), newTemplateGroup(options, config, true), newSwanBoard(options, config), newAlgorithm(options, config), newOffline(options, config), newSample(options, config))
	if options.KBSettings != nil && needsKBCommands(options.Args) {
		// Execution reports malformed overrides; the packaged command stays discoverable.
		if kb, _ := options.KBSettings(); kb.Enable {
			root.AddCommand(newKB(options, config, kb))
		}
	}
	return root
}

// Only discovery and Wiki commands need the optional local Wiki settings.
func needsKBCommands(args []string) bool {
	args = withoutLeadingAgent(args)
	if len(args) == 0 {
		return true
	}
	switch args[0] {
	case "kb", "tree", "help", "--help", "-h", "__complete", "__completeNoDesc", "completion":
		return true
	default:
		return false
	}
}

func contextBusiness(paths localstate.Paths, cfg localstate.Config) (business, tenant, login string) {
	business, login = "未绑定", "未登录"
	profile, err := cfg.RequireProfile()
	if err != nil {
		return business, tenant, login
	}
	creds, err := paths.CredentialsFor(profile)
	if err != nil {
		return business, tenant, login
	}
	if expiry, err := creds.Expiry(); err == nil {
		login = "已过期"
		if time.Now().Before(expiry) {
			login = "有效"
		}
	}
	id, err := paths.SelectedBusiness(creds)
	if err != nil || id == "" {
		return business, tenant, login
	}
	if login == "有效" {
		if entry, err := paths.BusinessEntry(creds); err == nil && entry.Selected.BusinessID == id {
			_, tenant, _ = businessSelectionNames(entry)
		}
	}
	return id, tenant, login
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
