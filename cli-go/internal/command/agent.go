package command

import (
	"errors"
	"os"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
)

func agentRequested(cmd *cobra.Command) bool {
	flags := cmd.Flags()
	if flags.Changed("agent") {
		enabled, _ := flags.GetBool("agent")
		return enabled
	}
	return os.Getenv("ML_AGENT") == "1" && !flags.Changed("output") && !flags.Changed("json")
}

func setupAgent(cmd *cobra.Command, args []string) error {
	flags := cmd.Flags()
	if !agentRequested(cmd) {
		return nil
	}
	if flags.Changed("output") || flags.Changed("json") {
		return usageError{errors.New("--agent 不能与 --output / --json 同时使用")}
	}
	switch cmd.CommandPath() {
	case "ml":
		install, _ := flags.GetBool("install-completion")
		if !install {
			return nil
		}
	case "ml help", "ml auth ping tick", "ml jupyter terminal open", "ml jupyter terminal attach", "ml __complete", "ml __completeNoDesc":
		return nil
	case "ml business", "ml service":
		if len(args) == 0 {
			return nil
		}
	}
	cmd.SetOut(&output.AgentWriter{Writer: cmd.OutOrStdout()})
	// Local-only commands and error handlers also consult the bound output option.
	if flag := flags.Lookup("output"); flag != nil {
		return flag.Value.Set("json")
	}
	return nil
}

func agentMode(cmd *cobra.Command) bool { return output.IsAgent(cmd.OutOrStdout()) }

func agentResult(cmd *cobra.Command, value any) error {
	return output.JSON(cmd.OutOrStdout(), value)
}

func withoutLeadingAgent(args []string) []string {
	for len(args) > 0 && (args[0] == "--agent" || strings.HasPrefix(args[0], "--agent=")) {
		args = args[1:]
	}
	return args
}
