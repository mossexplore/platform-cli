package command

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"regexp"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/jupyter"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
)

type runFileOperation func(*cobra.Command, []string, *jupyter.Client, string) (any, error)

func newJupyterFiles(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "files", Short: "远端单文件与目录操作"}
	add := func(use, short string, argsCount int, operation runFileOperation) *cobra.Command {
		cmd := &cobra.Command{Use: use, Short: short, Args: positional(argsCount), Annotations: map[string]string{"text_output": "true"}}
		format := cmd.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
		cmd.Flags().String("studio-id", "", "Web Studio 实例 ID")
		run := withJupyter(options, load, func(cmd *cobra.Command, args []string, client *jupyter.Client, format string) error {
			data, err := operation(cmd, args, client, format)
			if err != nil || data == nil {
				return err
			}
			raw, err := json.Marshal(data)
			if err != nil {
				return err
			}
			var decoded any
			decoder := json.NewDecoder(bytes.NewReader(raw))
			decoder.UseNumber()
			if err := decoder.Decode(&decoded); err != nil {
				return err
			}
			convertJupyterDates(decoded)
			if agentMode(cmd) {
				if cmd.Name() == "list" {
					model, ok := decoded.(map[string]any)
					if !ok {
						return errors.New("无效目录响应")
					}
					items, ok := model["content"].([]any)
					if !ok {
						return errors.New("缺少目录内容")
					}
					fields := map[string]string{
						"name": "名称", "path": "远端路径",
						"type": "条目类型", "writable": "是否可写",
						"created": "创建时间", "last_modified": "更新时间",
						"size": "文件大小（字节）", "mimetype": "MIME 类型",
						"format": "内容格式", "hash": "内容哈希",
						"hash_algorithm": "哈希算法",
					}
					rows := make([]map[string]any, 0, len(items))
					for _, item := range items {
						entry, ok := item.(map[string]any)
						if !ok {
							return errors.New("目录内容包含无效条目")
						}
						row := make(map[string]any)
						for key := range fields {
							if value, ok := entry[key]; ok {
								row[key] = value
							}
						}
						rows = append(rows, row)
					}
					v := output.AgentList(rows, fields, "unpaged", 0, 0, nil)
					v["path"] = model["path"]
					return agentResult(cmd, v)
				}
				return agentResult(cmd, decoded)
			}
			if format == "json" {
				return output.JSON(cmd.OutOrStdout(), client.Result(decoded))
			}
			return output.JSON(cmd.OutOrStdout(), decoded)
		})
		cmd.RunE = func(cmd *cobra.Command, args []string) error {
			err := run(cmd, args)
			var usage usageError
			if err == nil || !strings.EqualFold(*format, "json") || errors.As(err, &usage) || cmd.Context().Err() != nil {
				return err
			}
			if writeErr := output.JSON(cmd.OutOrStdout(), map[string]string{"status": "FAILED", "error": terminalControl.ReplaceAllString(err.Error(), "")}); writeErr != nil {
				return writeErr
			}
			return silentExit(1)
		}
		group.AddCommand(cmd)
		return cmd
	}
	list := add("list [PATH]", "列出目录的一层内容", 0, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		path := ""
		if len(args) == 1 {
			path = args[0]
		}
		model, err := client.Get(cmd.Context(), path, true, "")
		if err == nil && model.Text("type") != "directory" {
			err = errors.New("list 目标必须是目录")
		}
		return model, err
	})
	list.Args = maximumArgs(1)
	add("stat PATH", "查询类型、大小、时间和可写性", 1, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		return client.Get(cmd.Context(), args[0], false, "")
	})
	read := add("read PATH", "读取 UTF-8 文本和指定行范围", 1, readJupyterFile)
	read.Flags().Int("start-line", 1, "起始行")
	read.Flags().Int("end-line", 0, "结束行")
	write := add("write PATH", "从本地 UTF-8 文件或标准输入写入远端文件", 1,
		func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
			path, _ := cmd.Flags().GetString("from-file")
			stdin, _ := cmd.Flags().GetBool("stdin")
			overwrite, _ := cmd.Flags().GetBool("overwrite")
			if (path != "") == stdin {
				return nil, errors.New("--from-file 与 --stdin 必须且只能指定一个")
			}
			var data []byte
			var err error
			if stdin {
				data, err = io.ReadAll(cmd.InOrStdin())
			} else {
				data, err = os.ReadFile(path)
			}
			if err != nil {
				return nil, err
			}
			return client.Save(cmd.Context(), args[0], data, overwrite, true)
		})
	write.Flags().String("from-file", "", "本地 UTF-8 文件")
	write.Flags().Bool("stdin", false, "读取标准输入")
	write.Flags().Bool("overwrite", false, "允许覆盖远端文件")
	add("mkdir PATH", "创建一个目录，父目录必须存在", 1, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		return client.Mkdir(cmd.Context(), args[0])
	})
	upload := add("upload LOCAL REMOTE", "上传单文件，目标须含文件名", 2, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		overwrite, _ := cmd.Flags().GetBool("overwrite")
		data, err := os.ReadFile(args[0])
		if err != nil {
			return nil, err
		}
		return client.Save(cmd.Context(), args[1], data, overwrite, false)
	})
	upload.Flags().Bool("overwrite", false, "允许覆盖远端文件")
	download := add("download REMOTE LOCAL", "下载单文件，本地父目录必须存在", 2, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		overwrite, _ := cmd.Flags().GetBool("overwrite")
		return client.Download(cmd.Context(), args[0], args[1], overwrite)
	})
	download.Flags().Bool("overwrite", false, "允许覆盖本地文件")
	add("move SOURCE TARGET", "移动或重命名，目标必须不存在", 2, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		return client.Move(cmd.Context(), args[0], args[1])
	})
	add("copy SOURCE TARGET_DIR", "复制单文件至已有目录", 2, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		return client.Copy(cmd.Context(), args[0], args[1])
	})
	add("delete PATH", "删除文件或空目录", 1, func(cmd *cobra.Command, args []string, client *jupyter.Client, _ string) (any, error) {
		return client.Delete(cmd.Context(), args[0])
	})
	return group
}

var terminalControl = regexp.MustCompile("\\x1b\\][^\\x07\\x1b]*(?:\\x07|\\x1b\\\\)|\\x1b\\[[0-?]*[ -/]*[@-~]|[\\x00-\\x08\\x0b-\\x1f\\x7f]")
var pythonLineBreak = regexp.MustCompile("\\r\\n|[\\r\\n\\x0b\\x0c\\x1c-\\x1e\\x{85}\\x{2028}\\x{2029}]")

func readJupyterFile(cmd *cobra.Command, args []string, client *jupyter.Client, format string) (any, error) {
	first, _ := cmd.Flags().GetInt("start-line")
	last, _ := cmd.Flags().GetInt("end-line")
	lastSet := cmd.Flags().Changed("end-line")
	if first < 1 || lastSet && last < first {
		return nil, errors.New("行范围无效，结束行不能小于起始行")
	}
	model, err := client.Get(cmd.Context(), args[0], true, "text")
	if err != nil {
		return nil, err
	}
	content, err := jupyter.TextContent(model["content"])
	if err != nil {
		return nil, err
	}
	positions := []int{0}
	for _, boundary := range pythonLineBreak.FindAllStringIndex(content, -1) {
		positions = append(positions, boundary[1])
	}
	if positions[len(positions)-1] != len(content) {
		positions = append(positions, len(content))
	}
	startPosition := positions[min(first-1, len(positions)-1)]
	endPosition, endValue := len(content), any(nil)
	if lastSet {
		endPosition, endValue = positions[min(last, len(positions)-1)], last
	}
	text := content[startPosition:endPosition]
	if format == "json" {
		return map[string]any{"path": args[0], "content": text, "start_line": first, "end_line": endValue}, nil
	}
	_, err = io.WriteString(cmd.OutOrStdout(), terminalControl.ReplaceAllString(text, ""))
	return nil, err
}

func convertJupyterDates(value any) {
	switch current := value.(type) {
	case map[string]any:
		for key, item := range current {
			if key == "created" || key == "last_modified" {
				raw, _ := json.Marshal(item)
				current[key] = dateText(raw)
			} else {
				convertJupyterDates(item)
			}
		}
	case []any:
		for _, item := range current {
			convertJupyterDates(item)
		}
	}
}

type silentExit int

func (s silentExit) Error() string { return fmt.Sprintf("exit %d", s) }
