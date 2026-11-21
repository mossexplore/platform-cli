package command

import (
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
	path := strings.Join(strings.Fields(cmd.CommandPath())[1:], " ")
	page, ok := serviceHelpPages[path]
	if !ok {
		page = helpPages[path]
	}
	intro := strings.TrimSpace(cmd.Long)
	if page.intro != "" {
		intro = page.intro
	}
	if intro == "" {
		intro = cmd.Short + "。"
	}
	if page.note != "" {
		intro += "\n" + page.note
	}
	_, positional, _ := strings.Cut(cmd.Use, " ")
	usage := cmd.CommandPath()
	children := helpChildren(cmd)
	if len(children) > 0 {
		if cmd.Runnable() {
			usage += " [子命令]"
		} else {
			usage += " <子命令>"
		}
	}
	cmd.InheritedFlags() // Merge registered persistent flags into Flags before listing options.
	options := cmd.Flags()
	var rows []output.HelpRow
	var required []string
	options.VisitAll(func(flag *pflag.Flag) {
		if flag.Hidden || flag.Name == "help" {
			return
		}
		rows = append(rows, helpFlagRow(path, flag))
		if helpFlagRequired(flag) {
			required = append(required, helpFlagLabel(path, flag, false))
		}
	})
	if flag := options.Lookup("help"); flag != nil && !flag.Hidden {
		rows = append(rows, helpFlagRow(path, flag))
	}

	arguments := positional
	if page.argumentUsage != "" {
		arguments = page.argumentUsage
	}
	suffix := strings.Join(append(required, "[选项]"), " ")
	switch {
	case strings.HasPrefix(arguments, "-- "):
		usage += " " + suffix + " " + arguments
	case arguments != "":
		usage += " " + arguments + " " + suffix
	default:
		usage += " " + suffix
	}
	usageLines := []string{usage}
	if page.alternateTarget != "" {
		usageLines = append(usageLines, cmd.CommandPath()+" "+page.alternateTarget+" [选项]")
	}
	examples := page.examples
	if len(examples) == 0 && cmd.Example != "" {
		examples = strings.Split(cmd.Example, "\n")
	}
	if len(examples) == 0 && len(children) > 0 {
		examples = []string{cmd.CommandPath() + " " + children[0].Label + " --help"}
	}
	for _, example := range examples {
		if strings.Contains(example, exampleID) {
			intro += "\n示例 ID 为演示值，请换成当前环境中实际查询到的 ID。"
			break
		}
	}
	var argRows []output.HelpRow
	for _, row := range helpArguments(cmd, positional) {
		argRows = append(argRows, output.HelpRow{
			Label: row[0], Description: row[1], Required: !strings.HasPrefix(row[0], "["),
		})
	}

	return output.WriteHelpTable(cmd.OutOrStdout(), usageLines, intro, []output.HelpBlock{
		{Rows: children},
		{Title: "示例", PreserveWords: true, Lines: examples},
		{Title: "位置参数", Rows: argRows},
		{Title: "选项", Rows: rows},
	})
}

func helpChildren(cmd *cobra.Command) []output.HelpRow {
	var children []output.HelpRow
	for _, child := range cmd.Commands() {
		if child.IsAvailableCommand() {
			children = append(children, output.HelpRow{Label: child.Name(), Description: child.Short})
		}
	}
	return children
}

func helpFlagRequired(flag *pflag.Flag) bool {
	return len(flag.Annotations[cobra.BashCompOneRequiredFlag]) > 0
}

func helpFlagLabel(path string, flag *pflag.Flag, shorthand bool) string {
	name := "--" + flag.Name
	if shorthand && flag.Shorthand != "" && flag.ShorthandDeprecated == "" {
		name = "-" + flag.Shorthand + ", " + name
	}
	if value, _ := pflag.UnquoteUsage(flag); value != "" {
		name += " <" + helpFlagValue(path, flag, value) + ">"
	}
	return name
}

func helpFlagRow(path string, flag *pflag.Flag) output.HelpRow {
	_, description := pflag.UnquoteUsage(flag)
	required := helpFlagRequired(flag)
	switch {
	case flag.Name == "help":
		description = "显示帮助"
	case flag.Name == "version" && path == "":
		description = "显示 CLI 版本并退出"
	case required:
		description += "（必填）"
	case flag.Name == "output" && flag.DefValue == "":
		description += "，默认使用当前环境配置"
	case flag.DefValue != "" && flag.DefValue != "[]" && flag.DefValue != "false" && !strings.Contains(description, "默认"):
		description += "，默认 " + flag.DefValue
	}
	return output.HelpRow{
		Label: helpFlagLabel(path, flag, true), Description: description, Required: required, Switch: flag.Value.Type() == "bool",
	}
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
	"command":       "要查看帮助的命令路径，可包含多级子命令",
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
