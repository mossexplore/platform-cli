package command

import (
	"fmt"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

type serviceHelpGroup struct {
	title string
	names []string
}

type serviceHelpPage struct {
	intro, note     string
	examples        []string
	childGroups     []serviceHelpGroup
	optionGroups    []serviceHelpGroup
	alternateTarget string
	argumentUsage   string
}

func showServiceHelp(cmd *cobra.Command, args []string) {
	page, ok := serviceHelpPages[strings.TrimPrefix(cmd.CommandPath(), cmd.Root().Name()+" ")]
	if !ok {
		showHelp(cmd, args)
		return
	}
	if err := writeServiceHelp(cmd, page); err != nil {
		cmd.PrintErrln(err)
	}
}

func writeServiceHelp(cmd *cobra.Command, page serviceHelpPage) error {
	cmd.InitDefaultHelpFlag()
	out := cmd.OutOrStdout()
	intro := page.intro
	if intro == "" {
		intro = cmd.Short + "。"
	}
	_, positional, _ := strings.Cut(cmd.Use, " ")
	usageArgs := positional
	if page.argumentUsage != "" {
		usageArgs = page.argumentUsage
	}
	var required []string
	local := cmd.LocalFlags()
	local.VisitAll(func(flag *pflag.Flag) {
		if !flag.Hidden && serviceFlagRequired(flag) {
			required = append(required, serviceFlagLabel(flag, false))
		}
	})
	usage := cmd.CommandPath()
	if cmd.HasAvailableSubCommands() {
		usage += " <子命令>"
	}
	for _, segment := range append([]string{usageArgs}, required...) {
		if segment != "" {
			usage += " " + segment
		}
	}
	usage += " [选项]"
	var text strings.Builder
	fmt.Fprintf(&text, "%s\n\n用法\n  %s\n", intro, usage)
	if page.alternateTarget != "" {
		fmt.Fprintf(&text, "  %s %s [选项]\n", cmd.CommandPath(), page.alternateTarget)
	}
	if page.note != "" {
		fmt.Fprintf(&text, "\n%s\n", page.note)
	}

	sections := serviceChildSections(cmd, page.childGroups)
	if len(page.examples) > 0 {
		var examples strings.Builder
		examples.WriteString("\n示例\n")
		for _, line := range page.examples {
			fmt.Fprintf(&examples, "  %s\n", line)
		}
		sections = append(sections, output.HelpBlock{Text: examples.String()})
	}

	var arguments []output.HelpRow
	for _, row := range helpArguments(cmd, positional) {
		arguments = append(arguments, output.HelpRow{
			Label: row[0], Description: row[1], Required: !strings.HasPrefix(row[0], "["),
		})
	}
	sections = append(sections, output.HelpBlock{Title: "位置参数", Rows: arguments})

	seen := map[string]bool{"help": true}
	for _, group := range page.optionGroups {
		block := output.HelpBlock{Title: group.title}
		for _, name := range group.names {
			if flag := local.Lookup(name); flag != nil && !flag.Hidden {
				block.Rows = append(block.Rows, serviceFlagHelp(flag))
				seen[name] = true
			}
		}
		sections = append(sections, block)
	}
	var remaining, inherited []output.HelpRow
	local.VisitAll(func(flag *pflag.Flag) {
		if !flag.Hidden && !seen[flag.Name] {
			remaining = append(remaining, serviceFlagHelp(flag))
		}
	})
	cmd.InheritedFlags().VisitAll(func(flag *pflag.Flag) {
		if !flag.Hidden {
			inherited = append(inherited, serviceFlagHelp(flag))
		}
	})
	sections = append(sections,
		output.HelpBlock{Title: "选项", Rows: remaining},
		output.HelpBlock{Title: "全局选项", Rows: inherited},
		output.HelpBlock{Title: "帮助", Rows: []output.HelpRow{{Label: "-h, --help", Description: "显示帮助"}}},
	)
	return output.WriteHelpList(out, text.String(), sections)
}

func serviceChildSections(cmd *cobra.Command, groups []serviceHelpGroup) []output.HelpBlock {
	children := make(map[string]*cobra.Command)
	for _, child := range cmd.Commands() {
		if child.IsAvailableCommand() {
			children[child.Name()] = child
		}
	}
	var sections []output.HelpBlock
	for _, group := range groups {
		section := output.HelpBlock{Title: group.title}
		for _, name := range group.names {
			if child := children[name]; child != nil {
				section.Rows = append(section.Rows, output.HelpRow{Label: name, Description: child.Short})
				delete(children, name)
			}
		}
		sections = append(sections, section)
	}
	other := output.HelpBlock{Title: "子命令"}
	for _, child := range cmd.Commands() {
		if children[child.Name()] != nil {
			other.Rows = append(other.Rows, output.HelpRow{Label: child.Name(), Description: child.Short})
		}
	}
	return append(sections, other)
}

func serviceFlagRequired(flag *pflag.Flag) bool {
	return len(flag.Annotations[cobra.BashCompOneRequiredFlag]) > 0
}

func serviceFlagLabel(flag *pflag.Flag, shorthand bool) string {
	name := "--" + flag.Name
	if shorthand && flag.Shorthand != "" && flag.ShorthandDeprecated == "" {
		name = "-" + flag.Shorthand + ", " + name
	}
	if value, _ := pflag.UnquoteUsage(flag); value != "" {
		if placeholder := serviceFlagPlaceholders[flag.Name]; placeholder != "" {
			value = placeholder
		}
		name += " <" + value + ">"
	}
	return name
}

func serviceFlagHelp(flag *pflag.Flag) output.HelpRow {
	_, description := pflag.UnquoteUsage(flag)
	required := serviceFlagRequired(flag)
	switch {
	case required:
		description += "（必填）"
	case flag.Name == "output" && flag.DefValue == "":
		description += "，默认使用当前环境配置"
	case flag.DefValue != "" && flag.DefValue != "[]" && flag.DefValue != "false":
		description += "，默认 " + flag.DefValue
	}
	return output.HelpRow{Label: serviceFlagLabel(flag, true), Description: description, Required: required}
}
