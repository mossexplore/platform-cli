package command

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"slices"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

var serviceLogTypes = map[string][]string{
	"infer-python": {"run", "interface", "metrics", "engine", "ascend", "mslite", "alarm"},
	"rtc":          {"rtc", "run", "interface", "dcs", "metrics", "gc", "interface_manager", "interface_extend", "engine", "monitor", "catalina", "dmq"},
}

func newServiceLogs(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "logs SERVICE_ID", Short: "选择服务主机和文件并查看日志", Args: positional(1)}
	pod := cmd.Flags().String("pod", "", "Pod 名称")
	cluster := cmd.Flags().String("cluster-name", "", "集群名称")
	logType := cmd.Flags().String("type", "", "日志类别")
	file := cmd.Flags().String("file", "", "日志文件名称")
	keywords := cmd.Flags().StringArrayP("keyword", "k", nil, "关键词，可重复")
	lines := cmd.Flags().IntP("lines", "n", 200, "查询行数")
	list := cmd.Flags().Bool("list", false, "仅显示日志文件列表")
	noInput := cmd.Flags().Bool("no-input", false, "禁止交互选择")
	order := cmd.Flags().String("search-order", "tail", "检索顺序")
	scope := cmd.Flags().String("grep-scope", "C", "关键词范围")
	contextLines := cmd.Flags().Int("grep-line", 0, "关键词上下文行数")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if cmd.Flags().Changed("pod") != cmd.Flags().Changed("cluster-name") || *lines < 1 || *contextLines < 0 ||
			strings.TrimSpace(*order) == "" || strings.TrimSpace(*scope) == "" {
			return usageError{errors.New("主机、集群或日志检索参数无效")}
		}
		for _, key := range []string{"pod", "cluster-name", "type", "file"} {
			value, _ := cmd.Flags().GetString(key)
			if cmd.Flags().Changed(key) && strings.TrimSpace(value) == "" {
				return usageError{fmt.Errorf("%s 不能为空白", key)}
			}
		}
		for _, word := range *keywords {
			if strings.TrimSpace(word) == "" {
				return usageError{errors.New("关键词不能为空白")}
			}
		}
		for _, flag := range []string{"file", "keyword", "lines", "search-order", "grep-scope", "grep-line"} {
			if *list && cmd.Flags().Changed(flag) {
				return usageError{errors.New("--list 不能与正文检索选项同时使用")}
			}
		}
		input := bufio.NewReader(cmd.InOrStdin())
		inFile, isFile := cmd.InOrStdin().(*os.File)
		interactive := !*noInput && isFile && term.IsTerminal(int(inFile.Fd()))
		host, err := serviceLogHost(cmd, api, args[0], *pod, *cluster, interactive, input)
		if err != nil {
			return err
		}
		infra := host.Text("infraType")
		types, supported := serviceLogTypes[infra]
		if !supported {
			return fmt.Errorf("不支持的主机 infraType：%s", infra)
		}
		kind := strings.TrimSpace(*logType)
		if kind == "" {
			index, err := chooseServiceLog(cmd, input, types, "日志类别", "--type", interactive)
			if err != nil {
				return err
			}
			kind = types[index]
		} else if !slices.Contains(types, kind) {
			return fmt.Errorf("该主机不支持日志类别 %s", kind)
		}
		result, err := podLogRequest(cmd, api, host, infra, "queryPodAdvanceLogFileList", map[string]string{"type": kind})
		if err != nil {
			return err
		}
		files, err := responseRecords(result, "podLogFiles")
		if err != nil {
			return err
		}
		var names []string
		var rows [][]string
		for i, item := range files {
			name := item.Text("fileName")
			updated := fieldText(item["updateTime"])
			if strings.Contains(updated, "T") {
				updated = dateText(item["updateTime"])
			}
			rows = append(rows, []string{strconv.Itoa(i + 1), name, fieldText(item["fileSize"]), updated})
			if *file == "" || *file == name {
				names = append(names, name)
			}
		}
		if *list {
			return output.Table(cmd.OutOrStdout(), []string{"编号", "文件名称", "大小", "修改时间"}, rows)
		}
		if len(files) == 0 && *file == "" {
			_, err := fmt.Fprintln(cmd.ErrOrStderr(), "暂无日志文件")
			return err
		}
		index, err := chooseServiceLog(cmd, input, names, "日志文件", "--file", interactive)
		if err != nil {
			return err
		}
		name := names[index]
		if strings.TrimSpace(name) == "" {
			return errors.New("日志文件缺少有效的 fileName")
		}
		words := append([]string{}, (*keywords)...)
		data, err := podLogRequest(cmd, api, host, infra, "queryPodAdvanceLog", map[string]any{
			"type": kind, "keywords": words, "line": *lines, "searchOrder": strings.TrimSpace(*order),
			"logFileName": name, "grepScope": strings.TrimSpace(*scope), "grepLine": *contextLines,
		})
		if err != nil {
			return err
		}
		var content *string
		if json.Unmarshal(data.Object("data")["content"], &content) != nil || content == nil {
			return errors.New("日志响应缺少有效的 content")
		}
		_, err = io.WriteString(cmd.OutOrStdout(), *content)
		return err
	})
	return cmd
}

func podLogRequest(cmd *cobra.Command, api *platform.API, host platform.Record, infra, action string, search any) (platform.Record, error) {
	if strings.TrimSpace(host.Text("nodeName")) == "" || strings.TrimSpace(host.Text("clusterName")) == "" {
		return nil, errors.New("主机缺少 Pod 名称或集群名称")
	}
	data := map[string]any{"podStatus": 0, "businessId": api.BusinessID(), "podName": host.Text("nodeName"),
		"clusterName": host.Text("clusterName"), "serviceLogSearch": search, "belongingService": ""}
	if infra == "infer-python" {
		data["type"] = "rtc_python"
	}
	return servicePost(cmd, api, containerPrefix+action, map[string]any{"version": "1.0",
		"meta": map[string]string{"uuid": localstate.NewID()}, "data": data})
}

func serviceLogHost(cmd *cobra.Command, api *platform.API, id, pod, cluster string, interactive bool, input *bufio.Reader) (platform.Record, error) {
	for page := 1; ; {
		items, count, err := serviceHosts(cmd, api, id, "", page)
		if err != nil {
			return nil, err
		}
		if len(items) == 0 {
			return nil, errors.New("主机列表为空")
		}
		if pod != "" {
			record := platform.Record{"infraType": items[0]["infraType"]}
			_ = record.Put("nodeName", strings.TrimSpace(pod))
			_ = record.Put("clusterName", strings.TrimSpace(cluster))
			return record, nil
		}
		if count == 1 && len(items) == 1 {
			return items[0], nil
		}
		if !interactive {
			return nil, errors.New("主机无法唯一确定，请同时指定 --pod 和 --cluster-name")
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "主机列表 · 第 %d 页 · 共 %d 条\n", page, count)
		for i, item := range items {
			fmt.Fprintf(cmd.ErrOrStderr(), "%d. %s · %s\n", i+1, item.Text("clusterName"), item.Text("nodeName"))
		}
		fmt.Fprint(cmd.ErrOrStderr(), "输入编号选择，n 下一页，p 上一页，q 退出：")
		answer, err := input.ReadString('\n')
		if err != nil {
			return nil, silentExit(130)
		}
		switch answer = strings.TrimSpace(strings.ToLower(answer)); answer {
		case "q":
			return nil, silentExit(130)
		case "n":
			if page*10 < count {
				page++
			}
		case "p":
			page = max(1, page-1)
		default:
			if index, err := strconv.Atoi(answer); err == nil && index >= 1 && index <= len(items) {
				return items[index-1], nil
			}
		}
	}
}

func chooseServiceLog(cmd *cobra.Command, input *bufio.Reader, items []string, label, flag string, interactive bool) (int, error) {
	if len(items) == 0 {
		return 0, fmt.Errorf("没有可用的%s", label)
	}
	if len(items) == 1 {
		return 0, nil
	}
	if !interactive {
		return 0, fmt.Errorf("%s无法唯一确定，请指定 %s", label, flag)
	}
	for index, item := range items {
		fmt.Fprintf(cmd.ErrOrStderr(), "%d. %s\n", index+1, item)
	}
	for {
		fmt.Fprint(cmd.ErrOrStderr(), "请选择"+label+"：")
		answer, err := input.ReadString('\n')
		if err != nil {
			return 0, silentExit(130)
		}
		if value, err := strconv.Atoi(strings.TrimSpace(answer)); err == nil && value >= 1 && value <= len(items) {
			return value - 1, nil
		}
	}
}
