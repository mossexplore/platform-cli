package command

import (
	"archive/zip"
	"bytes"
	_ "embed"
	"encoding/json"
	"errors"
	"io"
	"os"
	"regexp"
	"strconv"

	"github.com/spf13/cobra"
	"golang.org/x/term"
)

//go:embed python-help.zip
var pythonHelp []byte

var helpSGR = regexp.MustCompile("\x1b\\[[0-9;]*m")

// Go CLI commands that intentionally diverge from cli-python and must render live Cobra help.
var goNativeHelpPaths = map[string]bool{
	"ml service":                 true,
	"ml service host":            true,
	"ml service host log-search": true,
	"ml service host log-stdout": true,
	"ml service host pod-event":  true,
}

func loadHelpFile(name string, target any) error {
	archive, err := zip.NewReader(bytes.NewReader(pythonHelp), int64(len(pythonHelp)))
	if err != nil {
		return err
	}
	entry, err := archive.Open(name)
	if err != nil {
		return err
	}
	defer entry.Close()
	return json.NewDecoder(entry).Decode(target)
}

func helpWidth(out io.Writer) int {
	for _, name := range []string{"TERMINAL_WIDTH", "COLUMNS"} {
		if width, err := strconv.Atoi(os.Getenv(name)); err == nil && width > 0 {
			return width
		}
	}
	if file, ok := out.(*os.File); ok {
		if width, _, err := term.GetSize(int(file.Fd())); err == nil && width > 0 {
			return width
		}
	}
	return 80
}

func pythonHelpFunc(fallback func(*cobra.Command, []string)) func(*cobra.Command, []string) {
	return func(cmd *cobra.Command, args []string) {
		if goNativeHelpPaths[cmd.CommandPath()] {
			fallback(cmd, args)
			return
		}
		out := cmd.OutOrStdout()
		page, err := pythonHelpPage(cmd.CommandPath(), helpWidth(out))
		if err != nil {
			fallback(cmd, args)
			return
		}
		file, isFile := out.(*os.File)
		_, noColor := os.LookupEnv("NO_COLOR")
		useColor := false
		if isFile && !noColor {
			var restore func()
			useColor, restore = enableHelpColor(file)
			if restore != nil {
				defer restore()
			}
		}
		if !useColor {
			page = helpSGR.ReplaceAllString(page, "")
		}
		if _, err := io.WriteString(out, page); err != nil {
			cmd.PrintErrln(err)
		}
	}
}

func pythonHelpPage(path string, width int) (string, error) {
	var layout struct {
		FirstWidth int      `json:"first_width"`
		Pages      []string `json:"pages"`
	}
	if err := loadHelpFile("help/"+path+".json", &layout); err != nil {
		return "", err
	}
	if len(layout.Pages) == 0 {
		return "", errors.New("没有可用的 Python 帮助页面")
	}
	index := min(max(0, width-layout.FirstWidth), len(layout.Pages)-1)
	return layout.Pages[index], nil
}
