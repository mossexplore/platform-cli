package redact

import "regexp"

const hidden = "[REDACTED]"

var rules = []struct {
	pattern     *regexp.Regexp
	replacement string
}{
	{regexp.MustCompile("(?si)-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?(?:-----END [A-Z0-9 ]*PRIVATE KEY-----|\\z)"), hidden},
	{regexp.MustCompile("(?i)\\b((?:set-cookie|cookie|authorization|proxy-authorization|x-ingest-token)[\"']?[ \\t]*[:=][ \\t]*)[^\\r\\n]*"), "${1}" + hidden},
	{regexp.MustCompile(`(?i)\b(?:basic|bearer)[ \t]+[A-Za-z0-9._~+/=-]+`), hidden},
	{regexp.MustCompile(`(?i)\b(?:pk-lf-|sk-lf-|sk-|gh[pousr]_|github_pat_|AKIA)[A-Za-z0-9_-]+`), hidden},
	{regexp.MustCompile("(?i)\\b((?:x-csrftoken|csrftoken|csrf_token|password|passwd|secret|token|access[_-]?key|api[_-]?key)[\"']?[ \\t]*[:=][ \\t]*)(?:\\[REDACTED\\]|\"(?:\\\\.|[^\"\\\\])*(?:\"|$)|'(?:\\\\.|[^'\\\\])*(?:'|$)|[^\\s,;}&\\]]+)"), "${1}" + hidden},
	{regexp.MustCompile(`(?i)(https?://)[^\s/@]+:[^\s/@]+@`), "${1}" + hidden + "@"},
}

func Text(value string) string {
	for _, rule := range rules {
		value = rule.pattern.ReplaceAllString(value, rule.replacement)
	}
	return value
}
