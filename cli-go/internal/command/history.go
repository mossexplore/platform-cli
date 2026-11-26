package command

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"slices"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

const historyPageSize = 20

func newHistory(options Options) *cobra.Command {
	group := &cobra.Command{Use: "history", Short: "查看和管理本地命令历史", Args: positional(0)}
	list := &cobra.Command{Use: "list", Short: "查询历史执行记录", Args: positional(0)}
	limit := list.Flags().Int("limit", historyPageSize, "最多显示条数，非交互和 JSON 默认 20")
	query := list.Flags().String("search", "", "命令内容关键字")
	env := list.Flags().String("env", "", "执行前的环境")
	status := list.Flags().String("status", "", "success、failed 或 interrupted")
	format := list.Flags().StringP("output", "o", "table", "输出格式为 table 或 json")
	list.RunE = func(cmd *cobra.Command, _ []string) error {
		if *limit < 1 || *limit > 1000 || (*format != "json" && *format != "table") ||
			!slices.Contains([]string{"", "success", "failed", "interrupted"}, *status) {
			return usageError{errors.New("limit、status 或 output 超出有效范围")}
		}
		paths, err := options.Paths()
		if err != nil {
			return err
		}
		rows, damaged, err := paths.ReadHistory()
		if err != nil {
			return err
		}
		if damaged != 0 {
			fmt.Fprintf(cmd.ErrOrStderr(), "[警告] 历史文件有 %d 条损坏记录，已跳过\n", damaged)
		}
		in, inOK := cmd.InOrStdin().(*os.File)
		out, outOK := cmd.OutOrStdout().(*os.File)
		browse := *format == "table" && inOK && outOK && term.IsTerminal(int(in.Fd())) && term.IsTerminal(int(out.Fd()))
		maxRows := *limit
		if browse && !cmd.Flags().Changed("limit") {
			maxRows = len(rows)
		}
		filtered := []localstate.HistoryEntry{}
		slices.Reverse(rows)
		slices.SortStableFunc(rows, func(a, b localstate.HistoryEntry) int {
			if a.Started < b.Started {
				return 1
			}
			if a.Started > b.Started {
				return -1
			}
			return 0
		})
		for _, row := range rows {
			if *query != "" && !strings.Contains(strings.ToLower(row.Command), strings.ToLower(*query)) ||
				*env != "" && (row.Before == nil || *row.Before != *env) || *status != "" && row.Status != *status {
				continue
			}
			row.Key = ""
			filtered = append(filtered, row)
			if len(filtered) == maxRows {
				break
			}
		}
		if agentMode(cmd) {
			return agentResult(cmd, output.AgentList(filtered, "limited", 0, 0, nil))
		}
		if *format == "json" {
			return output.JSON(cmd.OutOrStdout(), filtered)
		}
		if browse && len(filtered) > 0 {
			return browseHistory(cmd.Context(), in, out, cmd.ErrOrStderr(), filtered)
		}
		return renderHistory(cmd.OutOrStdout(), filtered)
	}
	group.RunE = list.RunE
	clear := &cobra.Command{Use: "clear", Short: "清理历史记录", Args: positional(0)}
	targetEnv := clear.Flags().String("env", "", "仅清理指定环境")
	before := clear.Flags().String("before", "", "清理早于指定北京时间的记录")
	yes := clear.Flags().Bool("yes", false, "跳过交互确认")
	clear.RunE = func(cmd *cobra.Command, _ []string) error {
		var cutoff time.Time
		var err error
		if cmd.Flags().Changed("before") {
			cutoff, err = time.ParseInLocation("2006-01-02 15:04:05", *before, beijing)
			if err != nil {
				return usageError{errors.New("时间须为 YYYY-MM-DD HH:mm:ss 北京时间")}
			}
		}
		paths, err := options.Paths()
		if err != nil {
			return err
		}
		rows, _, err := paths.ReadHistory()
		if err != nil {
			return err
		}
		selected := map[string]bool{}
		for _, row := range rows {
			if *targetEnv != "" && (row.Before == nil || *row.Before != *targetEnv) ||
				!cutoff.IsZero() && row.Started >= float64(cutoff.Unix()) {
				continue
			}
			selected[row.Key] = true
		}
		if len(selected) == 0 {
			if agentMode(cmd) {
				return agentResult(cmd, map[string]int{"deleted": 0})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 已清理 0 条历史记录")
			return nil
		}
		in, interactive := cmd.InOrStdin().(*os.File)
		if !*yes && (!interactive || !term.IsTerminal(int(in.Fd()))) {
			return errors.New("非交互清理必须传入 --yes")
		}
		approved, err := approve(cmd, fmt.Sprintf("将删除 %d 条历史记录，是否继续？", len(selected)))
		if err != nil {
			return err
		}
		count := 0
		if approved {
			count, err = paths.ClearHistory(selected)
			if err != nil {
				return err
			}
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]any{"deleted": count, "confirmed": approved})
		}
		_, err = fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 已清理 %d 条历史记录\n", count)
		return err
	}
	group.AddCommand(list, clear)
	return group
}

func renderHistory(out io.Writer, rows []localstate.HistoryEntry) error {
	table := make([][]string, 0, len(rows))
	for _, row := range rows {
		env := "-"
		if row.Before != nil {
			env = *row.Before
		}
		state := labelOrID(map[string]string{"success": "成功", "failed": "失败", "interrupted": "中断"}[row.Status], row.Status)
		table = append(table, []string{row.Time, env, state, fmt.Sprintf("%.2fs", float64(row.Duration)/1000), row.Command})
	}
	if err := output.Table(out, []string{"执行时间", "环境", "结果", "耗时", "命令"}, table); err != nil {
		return err
	}
	if len(rows) == 0 {
		_, err := fmt.Fprintln(out, "暂无匹配的历史记录")
		return err
	}
	return nil
}

func browseHistory(ctx context.Context, in io.Reader, out, prompts io.Writer, rows []localstate.HistoryEntry) error {
	page, pages := 0, (len(rows)+historyPageSize-1)/historyPageSize
	reader := bufio.NewReader(in)
render:
	for {
		start := page * historyPageSize
		if err := renderHistory(out, rows[start:min(start+historyPageSize, len(rows))]); err != nil {
			return err
		}
		if _, err := fmt.Fprintf(out, "第 %d / %d 页 · 共 %d 条记录\n", page+1, pages, len(rows)); err != nil {
			return err
		}
		for {
			fmt.Fprint(prompts, "[n] 下一页  [p] 上一页  [q] 退出，请输入：")
			type input struct {
				line string
				err  error
			}
			result := make(chan input, 1)
			// A console read can block after Ctrl+C until the process exits.
			go func() {
				line, err := reader.ReadString('\n')
				result <- input{line, err}
			}()
			select {
			case <-ctx.Done():
				return nil
			case answer := <-result:
				if answer.err != nil {
					if errors.Is(answer.err, io.EOF) {
						return nil
					}
					return answer.err
				}
				switch strings.ToLower(strings.TrimSpace(answer.line)) {
				case "q":
					return nil
				case "n":
					if page+1 < pages {
						page++
						continue render
					}
					fmt.Fprintln(prompts, "已经是最后一页")
				case "p":
					if page > 0 {
						page--
						continue render
					}
					fmt.Fprintln(prompts, "已经是第一页")
				default:
					fmt.Fprintln(prompts, "请输入 n、p 或 q 后按回车")
				}
			}
		}
	}
}

type historyInvocation struct {
	paths localstate.Paths
	start time.Time
	entry localstate.HistoryEntry
}

func startHistory(cmd *cobra.Command, options Options) *historyInvocation {
	path := cmd.CommandPath()
	if path == "ml" || path == "ml auth ping tick" || strings.HasPrefix(path, "ml tree") || strings.HasPrefix(path, "ml history") ||
		path == "ml help" || (path == "ml business" && cmd.Flags().NArg() == 0) || os.Getenv("ML_HISTORY") == "0" {
		return nil
	}
	paths, err := options.Paths()
	if err != nil {
		return nil
	}
	now := time.Now()
	command, redacted, truncated := formatHistoryCommand(path, options.Args)
	cwd, _ := os.Getwd()
	return &historyInvocation{paths: paths, start: now, entry: localstate.HistoryEntry{
		Time: now.In(beijing).Format("2006-01-02 15:04:05"), Started: float64(now.UnixNano()) / 1e9, Command: command,
		Config: paths.Config(), CWD: cwd, Before: paths.CurrentEnvironment(), Version: options.Version, Redacted: redacted,
		Truncated: truncated,
	}}
}

func (record *historyInvocation) finish(code int, options Options) {
	if record == nil {
		return
	}
	now := time.Now()
	entry := record.entry
	entry.Finished, entry.Duration = float64(now.UnixNano())/1e9, now.Sub(record.start).Milliseconds()
	entry.After, entry.ExitCode = record.paths.CurrentEnvironment(), code
	entry.Status = "failed"
	if code == 0 {
		entry.Status = "success"
	} else if code == 130 {
		entry.Status = "interrupted"
	}
	if err := record.paths.AppendHistory(entry); err != nil {
		fmt.Fprintln(options.Stderr, "[警告] 无法保存本次命令历史")
	}
}
