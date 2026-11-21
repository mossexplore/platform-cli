package command

import (
	_ "embed"
	"encoding/json"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

//go:embed python_help.json
var pythonHelpJSON []byte

type helpPage struct {
	Path, Usage, Intro string
	Arguments, Options []output.HelpRow
	Children           []string
}

var pythonHelp = loadPythonHelp()

func loadPythonHelp() map[string]helpPage {
	var pages []helpPage
	if err := json.Unmarshal(pythonHelpJSON, &pages); err != nil {
		panic(err)
	}
	byPath := make(map[string]helpPage, len(pages))
	for _, page := range pages {
		byPath[page.Path] = page
	}
	return byPath
}

func showHelp(cmd *cobra.Command, _ []string) {
	path := helpPath(cmd)
	page, exists := pythonHelp[path]
	children := helpChildren(cmd, page.Children)
	if !exists {
		page = liveHelpPage(cmd, len(children) > 0)
	}
	if err := output.WriteHelp(cmd.OutOrStdout(), cmd.CommandPath(), page.Usage, page.Intro,
		page.Arguments, helpOptions(cmd, page.Options), children); err != nil {
		cmd.PrintErrln(err)
	}
}

func helpPath(cmd *cobra.Command) string {
	_, path, _ := strings.Cut(cmd.CommandPath(), " ")
	return path
}

func liveHelpPage(cmd *cobra.Command, group bool) helpPage {
	_, positional, _ := strings.Cut(cmd.Use, " ")
	page := helpPage{Usage: "[OPTIONS]", Intro: cmd.Short}
	if group {
		page.Usage += " COMMAND [ARGS]..."
	}
	if positional != "" {
		page.Usage += " " + positional
	}
	for _, syntax := range strings.Fields(positional) {
		name := strings.ToLower(strings.Trim(syntax, "[]"))
		row := output.HelpRow{Label: name, Value: syntax, Required: !strings.HasPrefix(syntax, "[")}
		if row.Required {
			row.Value = "TEXT"
			row.Description = []string{"[required]"}
		}
		if name == "service_id" {
			row.Description = append([]string{"服务 ID"}, row.Description...)
		}
		page.Arguments = append(page.Arguments, row)
	}
	return page
}

func helpChildren(cmd *cobra.Command, pythonOrder []string) []output.HelpRow {
	children := cmd.Commands()
	byName := make(map[string]*cobra.Command, len(children))
	for _, child := range children {
		if child.IsAvailableCommand() {
			byName[child.Name()] = child
		}
	}
	var rows []output.HelpRow
	appendChild := func(child *cobra.Command) {
		if child == nil {
			return
		}
		intro := child.Short
		if page, ok := pythonHelp[helpPath(child)]; ok {
			intro, _, _ = strings.Cut(page.Intro, "\n\n")
		}
		rows = append(rows, output.HelpRow{Label: child.Name(), Description: []string{intro}})
		delete(byName, child.Name())
	}
	for _, name := range pythonOrder {
		appendChild(byName[name])
	}
	for _, child := range children {
		appendChild(byName[child.Name()])
	}
	return rows
}

const helpDescription = "Show this message and exit."

func helpOptions(cmd *cobra.Command, reference []output.HelpRow) []output.HelpRow {
	cmd.InitDefaultHelpFlag()
	cmd.InitDefaultVersionFlag()
	cmd.InheritedFlags()
	flags := cmd.Flags()
	flags.SortFlags = false

	var rows []output.HelpRow
	listed := make(map[string]bool)
	for _, source := range reference {
		row := source
		var labels []string
		for _, label := range strings.Split(row.Label, ",") {
			name := strings.TrimPrefix(label, "--")
			if flag := flags.Lookup(name); flag != nil && !flag.Hidden {
				labels = append(labels, label)
				listed[name] = true
				if isRequiredHelpFlag(flag) && !row.Required {
					row.Required = true
					row.Description = append(append([]string(nil), row.Description...), "[required]")
				}
			}
		}
		if len(labels) > 0 && row.Label != "--help" {
			row.Label = strings.Join(labels, ",")
			rows = append(rows, row)
		}
	}
	flags.VisitAll(func(flag *pflag.Flag) {
		if !flag.Hidden && flag.Name != "help" && !listed[flag.Name] {
			rows = append(rows, liveHelpOption(flag))
		}
	})
	return append(rows, output.HelpRow{Label: "--help", Description: []string{helpDescription}})
}

func isRequiredHelpFlag(flag *pflag.Flag) bool {
	return len(flag.Annotations[cobra.BashCompOneRequiredFlag]) > 0
}

func liveHelpOption(flag *pflag.Flag) output.HelpRow {
	placeholder, description := pflag.UnquoteUsage(flag)
	row := output.HelpRow{
		Label: "--" + flag.Name, Required: isRequiredHelpFlag(flag),
		Description: []string{description},
	}
	if flag.Shorthand != "" && flag.ShorthandDeprecated == "" {
		row.Short = "-" + flag.Shorthand
	}
	switch flag.Value.Type() {
	case "bool":
	case "int", "int64", "uint", "uint64":
		row.Value = "INTEGER"
	case "float32", "float64":
		row.Value = "FLOAT"
	case "string", "stringSlice", "stringArray":
		row.Value = "TEXT"
	default:
		row.Value = strings.ToUpper(placeholder)
	}
	if flag.DefValue != "" && flag.DefValue != "[]" && flag.DefValue != "false" {
		row.Description = append(row.Description, "[default: "+flag.DefValue+"]")
	}
	if row.Required {
		row.Description = append(row.Description, "[required]")
	}
	return row
}
