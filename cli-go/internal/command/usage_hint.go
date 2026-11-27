package command

import (
	"fmt"
	"io"
	"strings"

	"github.com/spf13/cobra"
	"github.com/spf13/pflag"
)

func writeUsageHint(out io.Writer, cmd *cobra.Command, err error) {
	if cmd == nil || err == nil {
		return
	}
	msg := err.Error()
	if suggestion := suggestFlag(cmd, msg); suggestion != "" {
		fmt.Fprintf(out, "[提示] 是否指：%s\n", suggestion)
	}
	if suggestion := suggestSubcommand(cmd, msg); suggestion != "" {
		fmt.Fprintf(out, "[提示] 是否指：%s\n", suggestion)
	}
	fmt.Fprintf(out, "[用法] %s\n", compactUsage(cmd))
	if children := availableSubcommands(cmd); len(children) > 0 {
		fmt.Fprintf(out, "[子命令] %s\n", strings.Join(children, ", "))
	}
	if flags := compactFlags(cmd); len(flags) > 0 {
		fmt.Fprintf(out, "[选项] %s\n", strings.Join(flags, ", "))
	}
}

func compactUsage(cmd *cobra.Command) string {
	path := cmd.CommandPath()
	_, positional, _ := strings.Cut(cmd.Use, " ")
	var parts []string
	parts = append(parts, path)
	if positional != "" {
		parts = append(parts, positional)
	}
	if cmd.HasAvailableSubCommands() && !cmd.Runnable() {
		parts = append(parts, "COMMAND")
	}
	parts = append(parts, "[OPTIONS]")
	return strings.Join(parts, " ")
}

func availableSubcommands(cmd *cobra.Command) []string {
	var names []string
	for _, child := range cmd.Commands() {
		if child.IsAvailableCommand() && !child.Hidden && child.Name() != "help" {
			names = append(names, child.Name())
		}
	}
	return names
}

func compactFlags(cmd *cobra.Command) []string {
	var items []string
	add := func(f *pflag.Flag) {
		if f.Hidden || f.Name == "help" {
			return
		}
		label := "--" + f.Name
		if f.Shorthand != "" {
			label += "/-" + f.Shorthand
		}
		if f.Value.Type() != "bool" {
			if f.DefValue != "" && f.DefValue != "[]" {
				label += "=" + f.DefValue
			} else {
				label += " " + strings.ToUpper(f.Value.Type())
			}
		}
		if _, required := f.Annotations[cobra.BashCompOneRequiredFlag]; required {
			label += "(必填)"
		}
		items = append(items, label)
	}
	cmd.NonInheritedFlags().VisitAll(add)
	if f := cmd.InheritedFlags().Lookup("agent"); f != nil {
		add(f)
	}
	return items
}

func suggestFlag(cmd *cobra.Command, msg string) string {
	const prefix = "unknown flag: --"
	idx := strings.Index(msg, prefix)
	if idx < 0 {
		return ""
	}
	unknown := strings.Fields(msg[idx+len(prefix):])[0]
	var candidates []string
	cmd.Flags().VisitAll(func(f *pflag.Flag) {
		if !f.Hidden && f.Name != "help" {
			candidates = append(candidates, f.Name)
		}
	})
	best := closestMatch(unknown, candidates)
	if best == "" {
		return ""
	}
	return "--" + best
}

func suggestSubcommand(cmd *cobra.Command, msg string) string {
	const prefix = `unknown command "`
	idx := strings.Index(msg, prefix)
	if idx < 0 {
		return ""
	}
	rest := msg[idx+len(prefix):]
	end := strings.IndexByte(rest, '"')
	if end <= 0 {
		return ""
	}
	unknown := rest[:end]
	return closestMatch(unknown, availableSubcommands(cmd))
}

func closestMatch(target string, candidates []string) string {
	best, bestScore := "", 4
	for _, candidate := range candidates {
		score := levenshtein(target, candidate)
		if strings.HasPrefix(candidate, target) || strings.HasPrefix(target, candidate) {
			if score > 1 {
				score = 1
			}
		} else if commonPrefixLen(target, candidate) >= 4 && commonPrefixLen(target, candidate)*2 >= min(len(target), len(candidate)) {
			if score > 2 {
				score = 2
			}
		}
		if score < bestScore {
			best, bestScore = candidate, score
		}
	}
	if bestScore > 3 {
		return ""
	}
	return best
}

func commonPrefixLen(a, b string) int {
	ra, rb := []rune(a), []rune(b)
	n := min(len(ra), len(rb))
	i := 0
	for i < n && ra[i] == rb[i] {
		i++
	}
	return i
}

func levenshtein(a, b string) int {
	ra, rb := []rune(a), []rune(b)
	if len(ra) == 0 {
		return len(rb)
	}
	if len(rb) == 0 {
		return len(ra)
	}
	prev := make([]int, len(rb)+1)
	for j := range prev {
		prev[j] = j
	}
	for i, ca := range ra {
		curr := make([]int, len(rb)+1)
		curr[0] = i + 1
		for j, cb := range rb {
			cost := 1
			if ca == cb {
				cost = 0
			}
			curr[j+1] = min(curr[j]+1, min(prev[j+1]+1, prev[j]+cost))
		}
		prev = curr
	}
	return prev[len(rb)]
}
