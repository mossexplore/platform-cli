package command

import "golang.org/x/sys/windows"

func quoteHistoryArg(value string) string { return windows.EscapeArg(value) }
