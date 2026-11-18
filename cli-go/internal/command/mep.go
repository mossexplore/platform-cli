package command

import (
	"errors"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

// newMEP retains the command implementation without registering it on the public CLI.
func newMEP(options Options, load loadConfig) *cobra.Command {
	mep := &cobra.Command{Use: "mep", Short: "MEP 管理"}
	mepConfig := &cobra.Command{Use: "config", Short: "MEP 配置"}
	get := &cobra.Command{
		Use: "get [KEY]", Short: "查询一个 MEP 配置项", Args: maximumArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			paths, cfg, err := load()
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
			result, err := session.QueryMEP(cmd.Context(), key, accessAuditCommand(cmd, options))
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
	return mep
}
