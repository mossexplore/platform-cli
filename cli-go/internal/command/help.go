package command

import (
	"fmt"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func showHelp(cmd *cobra.Command, _ []string) {
	if err := writeHelp(cmd); err != nil {
		cmd.PrintErrln(err)
	}
}

func writeHelp(cmd *cobra.Command) error {
	cmd.InitDefaultHelpFlag()
	cmd.InitDefaultVersionFlag()
	out := cmd.OutOrStdout()

	local := helpOptions(cmd.LocalFlags())
	inherited := helpOptions(cmd.InheritedFlags())
	usage := cmd.CommandPath()
	if cmd.HasAvailableSubCommands() {
		usage += " <子命令>"
	}
	if len(local)+len(inherited) > 0 {
		usage += " [选项]"
	}
	_, positional, _ := strings.Cut(cmd.Use, " ")
	if positional != "" {
		usage += " " + positional
	}

	description := strings.TrimSpace(cmd.Long)
	if description == "" {
		description = cmd.Short
	}
	if _, err := fmt.Fprintf(out, "用法：%s\n\n%s\n", usage, description); err != nil {
		return err
	}

	var children [][2]string
	for _, child := range cmd.Commands() {
		if child.IsAvailableCommand() {
			children = append(children, [2]string{child.Name(), child.Short})
		}
	}
	for _, section := range []struct {
		title string
		rows  [][2]string
	}{
		{"子命令", children},
		{"位置参数", helpArguments(cmd, positional)},
		{"选项", local},
		{"全局选项", inherited},
	} {
		if err := output.HelpSection(out, section.title, section.rows); err != nil {
			return err
		}
	}
	if cmd.Example != "" {
		_, err := fmt.Fprintf(out, "\n示例\n%s\n", cmd.Example)
		return err
	}
	return nil
}

func helpOptions(flags *pflag.FlagSet) [][2]string {
	var rows [][2]string
	flags.VisitAll(func(flag *pflag.Flag) {
		if flag.Hidden {
			return
		}
		name := "--" + flag.Name
		if flag.Shorthand != "" && flag.ShorthandDeprecated == "" {
			name = "-" + flag.Shorthand + ", " + name
		}
		value, description := pflag.UnquoteUsage(flag)
		if value != "" {
			name += " " + value
		}
		switch flag.Name {
		case "help":
			description = "显示帮助并退出"
		case "version":
			description = "显示 CLI 版本并退出"
		default:
			switch {
			case len(flag.Annotations[cobra.BashCompOneRequiredFlag]) > 0:
				description += "（必填）"
			case flag.Name == "output" && flag.DefValue == "":
				description += "（默认：当前环境配置）"
			case flag.DefValue != "" && flag.DefValue != "[]":
				description += "（默认：" + flag.DefValue + "）"
			}
		}
		rows = append(rows, [2]string{name, description})
	})
	return rows
}

func helpArguments(cmd *cobra.Command, positional string) [][2]string {
	var rows [][2]string
	for _, syntax := range strings.Fields(positional) {
		if syntax == "--" {
			continue
		}
		name := strings.TrimSuffix(strings.Trim(syntax, "[]"), "...")
		description := argumentHelp[name]
		if cmd.Parent() != nil && cmd.Parent().Name() == "env" && name == "NAME" {
			description = "环境名称"
		}
		if cmd.Parent() != nil && cmd.Parent().Name() == "notebook" && name == "SOURCE" {
			description = "本地 Notebook 路径"
		}
		if strings.HasPrefix(syntax, "[") {
			description += "（可选）"
		} else {
			description += "（必填）"
		}
		rows = append(rows, [2]string{syntax, description})
	}
	return rows
}

var argumentHelp = map[string]string{
	"ALGORITHM_ID":  "算法仓 ID",
	"ARG":           "传给远端程序的参数，可传多个",
	"DATASET_ID":    "数据集 ID",
	"ENV_ID":        "Web Studio 实例 ID",
	"EXPERIMENT_ID": "训练看板实验 ID",
	"JOB_ID":        "执行记录 ID",
	"KEY":           "配置项名称",
	"LOCAL":         "本地文件路径",
	"LOCAL_FILE":    "待上传的本地文件路径",
	"MODEL_ID":      "模型 ID",
	"NAME":          "远程终端名称",
	"NAMESPACE_ID":  "训练看板项目空间 ID",
	"PATH":          "相对 Jupyter 根目录的远端路径",
	"PROGRAM":       "要在远端执行的程序",
	"PROJECT_ID":    "项目 ID",
	"REMOTE":        "相对 Jupyter 根目录的远端文件路径",
	"SERVICE_ID":    "服务 ID",
	"SET_ID":        "特征集 ID",
	"SOURCE":        "远端源路径",
	"SOURCE_ID":     "源算法仓 ID",
	"TARGET":        "远端目标路径",
	"TARGET_DIR":    "远端目标目录",
	"TASK_ID":       "任务 ID",
	"TEMPLATE_ID":   "模板 ID",
}
