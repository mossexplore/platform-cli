package command

import "golang.org/x/sys/windows"

func quoteCommandArg(value string) string { return windows.EscapeArg(value) }
