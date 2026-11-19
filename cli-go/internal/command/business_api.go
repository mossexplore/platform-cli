package command

import (
	"bufio"
	"errors"
	"fmt"
	"io"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

type loadConfig func() (localstate.Paths, localstate.Config, error)

func accessAuditCommand(cmd *cobra.Command, options Options) string {
	command, _, _ := formatHistoryCommand(cmd.CommandPath(), options.Args)
	return command
}

func authorized(options Options, load loadConfig, run func(*cobra.Command, []string, *platform.API, string) error) func(*cobra.Command, []string) error {
	return func(cmd *cobra.Command, args []string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		profile, err := cfg.RequireProfile()
		if err != nil {
			return err
		}
		format := profile.Output
		textOutput := cmd.Annotations["text_output"] == "true"
		if cmd.Flags().Lookup("output") != nil && (cmd.Flags().Changed("output") || textOutput) {
			format, _ = cmd.Flags().GetString("output")
		}
		format = strings.ToLower(format)
		if cmd.Flags().Lookup("output") != nil && format != "json" && (format != "table" || textOutput) && (format != "text" || !textOutput) {
			if textOutput {
				return usageError{errors.New("output 仅支持 text 或 json")}
			}
			return usageError{errors.New("output 仅支持 table 或 json")}
		}
		path := strings.TrimPrefix(cmd.CommandPath(), cmd.Root().Name()+" ")
		if profile.PlatformType == "mlops" && wiseRecOnly(cmd) {
			return fmt.Errorf("管理台 mlops 不支持命令 ml %s；运行 ml tree 查看支持的命令", path)
		}
		if settings := profile.Jupyter; strings.HasPrefix(path, "jupyter ") && settings.Mode != "webstudio" && settings.BusinessFile != "" {
			paths.BusinessOverride = paths.ConfigRelative(settings.BusinessFile)
		}
		session := platform.Session{Paths: paths, Config: cfg, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
		if diagnose, _ := cmd.Flags().GetBool("diagnose"); path == "access status" && diagnose {
			session.Diagnostic = cmd.ErrOrStderr()
		}
		api, err := session.Authorize(cmd.Context(), path, accessAuditCommand(cmd, options))
		if err != nil {
			return err
		}
		defer api.Close()
		defer func() {
			if profile, username, origin, ok := api.RecordActivity(); ok {
				keepalive.Touch(paths, profile, username, origin)
			}
		}()
		return run(cmd, args, api, format)
	}
}

func wiseRecOnly(cmd *cobra.Command) bool {
	return cmd.Annotations["platform"] == "wiserec"
}

func positional(count int) cobra.PositionalArgs {
	return func(_ *cobra.Command, args []string) error {
		if len(args) != count {
			return usageError{fmt.Errorf("需要 %d 个位置参数", count)}
		}
		for index, value := range args {
			args[index] = strings.TrimSpace(value)
			if args[index] == "" {
				return usageError{errors.New("位置参数不能为空")}
			}
		}
		return nil
	}
}

func outputFlag(cmd *cobra.Command) {
	cmd.Flags().StringP("output", "o", "", "输出格式为 table 或 json")
}

func pagination(cmd *cobra.Command) (page, size *int) {
	return cmd.Flags().Int("page", 1, "页码"), cmd.Flags().Int("page-size", 10, "每页记录数")
}

func approve(cmd *cobra.Command, prompt string) (bool, error) {
	if yes, _ := cmd.Flags().GetBool("yes"); yes {
		return true, nil
	}
	in := bufio.NewReader(cmd.InOrStdin())
	for {
		fmt.Fprintf(cmd.ErrOrStderr(), "%s [y/N] ", prompt)
		answer, err := in.ReadString('\n')
		if err != nil && err != io.EOF {
			return false, err
		}
		switch strings.ToLower(strings.TrimSpace(answer)) {
		case "y", "yes":
			return true, nil
		case "", "n", "no":
			return false, nil
		}
		if err == io.EOF {
			return false, nil
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "请输入 y 或 n")
	}
}
