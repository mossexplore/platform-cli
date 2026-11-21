package command

import (
	"fmt"
	"regexp"
	"slices"
	"strings"
	"unicode"
)

const maxHistoryCommand = 8192

var (
	historySecret = regexp.MustCompile(`(?i)password|passwd|secret|token|cookie|csrf|authorization|api[-_]?key|credential`)
	historyURL    = regexp.MustCompile(`(?i)://[^/\s]*@|[?&](access[-_]?token|token|key|password|secret|api[-_]?key|signature|x-(amz|obs|oss)-[^=&]+)=`)
	historyJSON   = regexp.MustCompile(`(?i)"[^"]*(password|passwd|secret|token|cookie|csrf|authorization|api[-_]?key|credential)[^"]*"\s*:`)
)

func formatHistoryCommand(path string, args []string) (command string, redacted bool, truncated bool) {
	parts := []string{"ml"}
	hideNext := false
	for index, arg := range args {
		key, _, assigned := strings.Cut(arg, "=")
		switch {
		case hideNext:
			arg, hideNext, redacted = "[REDACTED]", false, true
		case strings.HasPrefix(key, "-") && (historySecret.MatchString(key) || slices.Contains(
			[]string{"--customize-config", "--data", "--body", "--payload", "--header", "--headers"}, strings.ToLower(key))):
			if assigned {
				arg = key + "=[REDACTED]"
			}
			hideNext, redacted = !assigned, true
		case historyURL.MatchString(arg):
			arg, redacted = "[REDACTED URL]", true
		case historyJSON.MatchString(arg):
			arg, redacted = "[REDACTED JSON]", true
		case assigned && historySecret.MatchString(key):
			arg, redacted = key+"=[REDACTED]", true
		}
		parts = append(parts, quoteCommandArg(arg))
		if path == "ml jupyter exec" && args[index] == "exec" {
			parts = append(parts, quoteCommandArg("[REDACTED EXEC]"))
			redacted = true
			break
		}
	}
	var safe strings.Builder
	for _, r := range strings.Join(parts, " ") {
		if unicode.IsControl(r) {
			fmt.Fprintf(&safe, "\\x%02x", r)
		} else {
			safe.WriteRune(r)
		}
	}
	command = safe.String()
	if text := []rune(command); len(text) > maxHistoryCommand {
		const suffix = " …[已截断]"
		return string(text[:maxHistoryCommand-len([]rune(suffix))]) + suffix, redacted, true
	}
	return command, redacted, false
}
