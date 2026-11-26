package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newKBFiles(options Options, load loadConfig, cfg localstate.KnowledgeBase) *cobra.Command {
	group := &cobra.Command{Use: "file", Short: "查询和下载知识库原始文件"}
	list := &cobra.Command{Use: "list", Short: "列出知识库原始文件", Args: positional(0)}
	kb := list.Flags().String("kb", cfg.Default, "知识库名称或 ID")
	page := list.Flags().Int("page", 1, "页码")
	size := list.Flags().Int("page-size", 20, "每页扫描的知识条目数（1–50）")
	all := list.Flags().Bool("all", false, "自动翻页列出全部原始文件")
	format := list.Flags().StringP("output", "o", "table", "输出格式为 table 或 json")
	list.MarkFlagsMutuallyExclusive("page", "all")
	list.RunE = func(cmd *cobra.Command, _ []string) error {
		if *page < 1 || *size < 1 || *size > 50 {
			return errors.New("页码或每页条数无效")
		}
		if *format != "table" && *format != "json" {
			return errors.New("输出格式无效")
		}
		paths, config, err := load()
		if err != nil {
			return err
		}
		session := platform.Session{Paths: paths, Config: config, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
		result, err := listKBFiles(cmd, session, accessAuditCommand(options.Args), *kb, *page, *size, *all)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			for i, item := range result.Items {
				if item.Updated != "" {
					raw, _ := json.Marshal(item.Updated)
					result.Items[i].Updated = dateText(raw)
				}
			}
			mode := "paged"
			if *all {
				mode = "unpaged"
			}
			v := output.AgentList(result.Items, map[string]string{
				"id": "知识条目 ID", "file_name": "文件名",
				"folder_path": "目录", "file_size": "文件大小（字节）",
				"updated_at": "更新时间",
			}, mode, result.Page, result.Size, nil)
			v["kb_id"], v["kb_name"] = result.ID, result.Name
			if result.HasMore != nil {
				v["has_more"] = *result.HasMore
			}
			return agentResult(cmd, v)
		}
		if *format == "json" {
			return output.JSON(cmd.OutOrStdout(), result)
		}
		fmt.Fprintln(cmd.OutOrStdout(), "知识库 ID", result.ID)
		rows := make([][]string, 0, len(result.Items))
		for _, item := range result.Items {
			size := "-"
			if item.Size != nil {
				size = strconv.FormatInt(*item.Size, 10)
			}
			rows = append(rows, []string{item.ID, terminalControl.ReplaceAllString(item.Name, ""),
				labelOrID(terminalControl.ReplaceAllString(item.Folder, ""), "/"), size, item.Updated})
		}
		if *all {
			fmt.Fprintf(cmd.OutOrStdout(), "共 %d 个文件\n", len(rows))
		} else {
			fmt.Fprintf(cmd.OutOrStdout(), "第 %d 页，显示 %d 个文件\n", *page, len(rows))
			if *result.HasMore {
				fmt.Fprintln(cmd.ErrOrStderr(), "[提示] 还有下一页，可增加 --page 或使用 --all")
			}
		}
		return output.Table(cmd.OutOrStdout(), []string{"知识条目 ID", "文件名", "目录", "字节数", "更新时间"}, rows)
	}

	download := &cobra.Command{Use: "download KNOWLEDGE_ID", Short: "下载知识库原始文件", Args: positional(1)}
	source := download.Flags().String("kb", "", "知识库名称或 ID")
	file := download.Flags().String("file", "", "本地保存路径")
	_ = download.MarkFlagRequired("kb")
	download.RunE = func(cmd *cobra.Command, args []string) error {
		if strings.TrimSpace(*source) == "" {
			return errors.New("请通过 --kb 指定知识库名称或 ID")
		}
		paths, config, err := load()
		if err != nil {
			return err
		}
		session := platform.Session{Paths: paths, Config: config, CLIVersion: options.Version, Stderr: cmd.ErrOrStderr()}
		query := url.Values{"kb": {*source}, "id": {args[0]}}
		path, size, err := session.DownloadKBFile(cmd.Context(), accessAuditCommand(options.Args), query, *file)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]any{"file": path, "bytes": size})
		}
		_, err = fmt.Fprintf(cmd.OutOrStdout(), "已保存到 %s（%d 字节）\n", path, size)
		return err
	}
	group.AddCommand(list, download)
	return group
}

type kbFile struct {
	ID      string `json:"id"`
	Name    string `json:"file_name"`
	Folder  string `json:"folder_path"`
	Size    *int64 `json:"file_size"`
	Updated string `json:"updated_at"`
}

type kbFiles struct {
	ID      string   `json:"kb_id"`
	Name    string   `json:"kb_name"`
	Page    int      `json:"page,omitempty"`
	Size    int      `json:"page_size,omitempty"`
	HasMore *bool    `json:"has_more,omitempty"`
	Items   []kbFile `json:"items"`
}

func listKBFiles(cmd *cobra.Command, session platform.Session, audit, kb string, page, size int, all bool) (kbFiles, error) {
	result := kbFiles{Items: []kbFile{}}
	seen := map[string]bool{}
	for ; ; page++ {
		query := url.Values{"kb": {kb}, "page": {strconv.Itoa(page)}, "page_size": {strconv.Itoa(size)}}
		var raw json.RawMessage
		var err error
		for attempt := 0; ; attempt++ {
			raw, err = session.ReadKB(cmd.Context(), "kb file list", "files", audit, query)
			if !all || attempt == 2 || !errors.Is(err, platform.ErrKBRateLimited) {
				break
			}
			select {
			case <-cmd.Context().Done():
				return kbFiles{}, cmd.Context().Err()
			case <-time.After(time.Second):
			}
		}
		if err != nil {
			return kbFiles{}, err
		}
		var batch kbFiles
		if json.Unmarshal(raw, &batch) != nil || batch.Items == nil || batch.HasMore == nil ||
			batch.ID == "" || batch.Page != page || batch.Size != size || (result.ID != "" && batch.ID != result.ID) {
			return kbFiles{}, errors.New("知识库文件列表分页响应无效")
		}
		if !all {
			return batch, nil
		}
		result.ID, result.Name, kb = batch.ID, batch.Name, batch.ID
		for _, file := range batch.Items {
			if !seen[file.ID] {
				result.Items = append(result.Items, file)
				seen[file.ID] = true
			}
		}
		if !*batch.HasMore {
			return result, nil
		}
	}
}
