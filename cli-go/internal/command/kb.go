package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newKB(options Options, load loadConfig, cfg localstate.KnowledgeBase) *cobra.Command {
	root := &cobra.Command{Use: "kb", Short: "查询共享 Wiki 知识库"}
	pages := &cobra.Command{Use: "page", Short: "浏览 Wiki 页面"}
	root.AddCommand(pages, newKBFiles(options, load, cfg))
	for _, spec := range []struct {
		use, route, short string
		parent            *cobra.Command
	}{{"list", "list", "列出可见知识库", root}, {"search QUERY", "search", "按关键词检索已发布页面", root}, {"list", "pages", "浏览知识库页面目录", pages}, {"show SLUG", "page", "查看 Wiki 页面预览及来源", pages}} {
		route := spec.route
		var kb, format string
		var page, size, limit int
		leaf := &cobra.Command{Use: spec.use, Short: spec.short, Args: cobra.ExactArgs(len(strings.Fields(spec.use)) - 1)}
		if route != "list" {
			leaf.Flags().StringVar(&kb, "kb", cfg.Default, "知识库名称或 ID")
		}
		if route == "pages" {
			leaf.Flags().IntVar(&page, "page", 1, "页码")
			leaf.Flags().IntVar(&size, "page-size", 20, "每页条数（1–50）")
		}
		if route == "search" {
			leaf.Flags().IntVar(&limit, "limit", 5, "结果条数（1–20）")
		}
		def := "table"
		if route == "page" {
			def = "text"
		}
		leaf.Flags().StringVarP(&format, "output", "o", def, "输出格式 "+def+" 或 json")
		leaf.RunE = func(cmd *cobra.Command, args []string) error {
			if format != def && format != "json" {
				return errors.New("输出格式无效")
			}
			q := url.Values{}
			if kb != "" {
				q.Set("kb", kb)
			}
			switch route {
			case "pages":
				if page < 1 || size < 1 || size > 50 {
					return errors.New("页码或每页条数无效")
				}
				q.Set("page", strconv.Itoa(page))
				q.Set("page_size", strconv.Itoa(size))
			case "page":
				q.Set("slug", args[0])
			case "search":
				if limit < 1 || limit > 20 || strings.TrimSpace(args[0]) == "" || len([]rune(args[0])) > 512 {
					return errors.New("检索词或条数无效")
				}
				q.Set("limit", strconv.Itoa(limit))
				q.Set("q", args[0])
			}
			paths, c, e := load()
			if e != nil {
				return e
			}
			command := strings.TrimPrefix(cmd.CommandPath(), "ml ")
			session := platform.Session{Paths: paths, Config: c, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
			raw, e := session.ReadKB(cmd.Context(), command, route, accessAuditCommand(options.Args), q)
			if e != nil {
				return e
			}
			return writeKBResult(cmd, route, format, raw)
		}
		spec.parent.AddCommand(leaf)
	}
	return root
}

type kbItem struct {
	ID, Name, Description, Slug, Title, Summary string
	Updated                                     string `json:"updated_at"`
}

func writeKBResult(cmd *cobra.Command, route, format string, raw json.RawMessage) error {
	if agentMode(cmd) && route != "page" {
		var parsed struct {
			KBID   string `json:"kb_id"`
			KBName string `json:"kb_name"`
			Items  []platform.Record
			Page   int
			Size   int `json:"page_size"`
			Total  *int
			Window *bool `json:"candidate_window_exhausted"`
		}
		if err := json.Unmarshal(raw, &parsed); err != nil {
			return err
		}
		if parsed.Items == nil {
			return errors.New("知识库响应缺少有效的 items")
		}
		mode := "unpaged"
		if route == "pages" {
			mode = "paged"
		} else if route == "search" {
			mode = "limited"
		}
		v := output.AgentList(agentRows(parsed.Items, nil, "id", "name", "description", "slug", "title", "summary", "updated_at", "kb_id", "source_refs", "score"), mode, parsed.Page, parsed.Size, parsed.Total)
		if parsed.KBID != "" {
			v["kb_id"] = parsed.KBID
		}
		if parsed.KBName != "" {
			v["kb_name"] = parsed.KBName
		}
		if parsed.Window != nil {
			v["candidate_window_exhausted"] = *parsed.Window
		}
		return agentResult(cmd, v)
	}
	if format == "json" {
		return output.JSON(cmd.OutOrStdout(), raw)
	}
	var result struct {
		Items          []kbItem
		Page, Total    int
		PageSize       int `json:"page_size"`
		Title, Content string
		Refs           []string `json:"source_refs"`
		Truncated      bool
		Window         bool `json:"candidate_window_exhausted"`
	}
	if e := json.Unmarshal(raw, &result); e != nil {
		return e
	}
	out := cmd.OutOrStdout()
	if route == "page" {
		fmt.Fprintln(out, result.Title)
		fmt.Fprintln(out, result.Content)
		if result.Truncated {
			fmt.Fprintf(out, "已截断，展示 %d 字节\n", len(result.Content))
		}
		for _, ref := range result.Refs {
			fmt.Fprintln(out, "来源", ref)
		}
		return nil
	}
	rows := make([][]string, 0, len(result.Items))
	if route == "list" {
		for _, item := range result.Items {
			rows = append(rows, []string{item.ID, item.Name, item.Updated, item.Description})
		}
		return output.Table(out, []string{"知识库 ID", "名称", "更新时间", "说明"}, rows)
	}
	for _, item := range result.Items {
		rows = append(rows, []string{item.Slug, item.Title, item.Updated, item.Summary})
	}
	if route == "pages" {
		fmt.Fprintf(out, "第 %d 页，每页 %d 条，共 %d 条\n", result.Page, result.PageSize, result.Total)
	}
	if result.Window {
		fmt.Fprintln(cmd.ErrOrStderr(), "候选窗口已满，请使用更精确的关键词")
	}
	return output.Table(out, []string{"Slug", "标题", "更新时间", "摘要"}, rows, 0)
}
