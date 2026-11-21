package command

import (
	"bufio"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

const defaultPodLogContainer = "appcontainer"

func newServiceHostPodEvent(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "pod-event [SERVICE_ID]", Short: "查询指定主机的 Pod 事件", Args: optionalPositional(1)}
	pod := cmd.Flags().String("pod", "", "Pod 名称")
	cluster := cmd.Flags().String("cluster-name", "", "集群名称，须与 --pod 一起传入")
	noInput := cmd.Flags().Bool("no-input", false, "禁止交互选择")
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		podName := strings.TrimSpace(*pod)
		clusterName := strings.TrimSpace(*cluster)
		if cmd.Flags().Changed("pod") && podName == "" {
			return usageError{errors.New("pod 不能为空白")}
		}
		if cmd.Flags().Changed("cluster-name") && clusterName == "" {
			return usageError{errors.New("cluster-name 不能为空白")}
		}
		if clusterName != "" && podName == "" {
			return usageError{errors.New("指定 --cluster-name 时必须同时指定 --pod")}
		}
		if len(args) == 0 && (podName == "" || clusterName == "") {
			return usageError{errors.New("请提供 SERVICE_ID，或同时指定 --pod 和 --cluster-name")}
		}
		if podName == "" || clusterName == "" {
			var err error
			podName, clusterName, err = resolveServiceHostTarget(cmd, api, args[0], podName, *noInput, "请指定 --pod 和 --cluster-name")
			if err != nil {
				return err
			}
			if clusterName == "" {
				return errors.New("主机缺少有效的集群名称，请通过 --cluster-name 指定")
			}
		}
		result, err := servicePost(cmd, api, containerPrefix+"queryPodEvent", map[string]any{
			"businessId":  api.BusinessID(),
			"podName":     podName,
			"clusterName": clusterName,
		})
		if err != nil {
			return err
		}
		events, err := responseRecords(result, "eventContents")
		if err != nil {
			return err
		}
		out := cmd.OutOrStdout()
		if format == "json" {
			return output.JSON(out, result)
		}
		cols := []recordColumn{
			{"类型", "type"},
			{"事件原因", "reason"},
			{"消息", "message"},
			{"最后更新时间", "lastTimestamp"},
			{"次数", "count"},
		}
		if err := renderRecordTable(out, cols, events, podEventValue); err != nil {
			return err
		}
		if len(events) == 0 {
			_, err = fmt.Fprintln(out, "暂无 Pod 事件")
			return err
		}
		return nil
	})
	return cmd
}

func newServiceHostLogStdout(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{
		Use:         "log-stdout [SERVICE_ID]",
		Short:       "查询指定主机的标准输出日志",
		Args:        optionalPositional(1),
		Annotations: map[string]string{"text_output": "true"},
	}
	pod := cmd.Flags().String("pod", "", "Pod 名称")
	container := cmd.Flags().StringP("container", "c", defaultPodLogContainer, "容器名称，例如 appcontainer 或 filebeat")
	noInput := cmd.Flags().Bool("no-input", false, "禁止交互选择")
	cmd.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		podName := strings.TrimSpace(*pod)
		containerName := strings.TrimSpace(*container)
		if cmd.Flags().Changed("pod") && podName == "" {
			return usageError{errors.New("pod 不能为空白")}
		}
		if containerName == "" {
			return usageError{errors.New("container 不能为空白")}
		}
		if len(args) == 0 && podName == "" {
			return usageError{errors.New("请提供 SERVICE_ID 或指定 --pod")}
		}
		if podName == "" {
			var err error
			podName, _, err = resolveServiceHostTarget(cmd, api, args[0], "", *noInput, "请指定 --pod")
			if err != nil {
				return err
			}
		}
		probe, err := queryPodStdout(cmd, api, podName, defaultPodLogContainer)
		if err != nil {
			return err
		}
		states, err := responseRecords(probe, "containerStates")
		if err != nil {
			return err
		}
		if !hasContainerState(states, containerName) {
			return fmt.Errorf("该容器没有%s类型日志，请确认容器类型是否正确！", containerName)
		}
		result := probe
		if containerName != defaultPodLogContainer {
			result, err = queryPodStdout(cmd, api, podName, containerName)
			if err != nil {
				return err
			}
			if latest, statesErr := responseRecords(result, "containerStates"); statesErr == nil {
				states = latest
			}
		}
		out := cmd.OutOrStdout()
		if format == "json" {
			return output.JSON(out, result)
		}
		return renderPodStdout(out, states, result)
	})
	return cmd
}

func optionalPositional(maximum int) cobra.PositionalArgs {
	return func(_ *cobra.Command, args []string) error {
		if len(args) > maximum {
			return usageError{fmt.Errorf("最多接受 %d 个位置参数", maximum)}
		}
		for index, value := range args {
			args[index] = strings.TrimSpace(value)
			if args[index] == "" {
				return usageError{errors.New("位置参数不能为空")}
			}
		}
		return nil
	}
}

func resolveServiceHostTarget(cmd *cobra.Command, api *platform.API, serviceID, podName string, noInput bool, nonInteractiveHint string) (string, string, error) {
	var host platform.Record
	var err error
	if podName != "" {
		host, err = findServiceHostByPod(cmd, api, serviceID, podName)
	} else {
		inFile, isFile := cmd.InOrStdin().(*os.File)
		interactive := !noInput && isFile && term.IsTerminal(int(inFile.Fd()))
		host, err = pickServiceHost(cmd, api, serviceID, interactive, bufio.NewReader(cmd.InOrStdin()), nonInteractiveHint)
	}
	if err != nil {
		return "", "", err
	}
	resolvedPod := strings.TrimSpace(host.Text("nodeName"))
	resolvedCluster := strings.TrimSpace(host.Text("clusterName"))
	if resolvedPod == "" {
		return "", "", errors.New("主机缺少有效的 Pod 名称")
	}
	if podName != "" && resolvedCluster == "" {
		return "", "", errors.New("主机缺少有效的集群名称，请通过 --cluster-name 指定")
	}
	return resolvedPod, resolvedCluster, nil
}

func findServiceHostByPod(cmd *cobra.Command, api *platform.API, serviceID, podName string) (platform.Record, error) {
	var matches []platform.Record
	for page := 1; ; page++ {
		items, count, err := serviceHosts(cmd, api, serviceID, "", page)
		if err != nil {
			return nil, err
		}
		for _, item := range items {
			if strings.TrimSpace(item.Text("nodeName")) == podName {
				matches = append(matches, item)
			}
		}
		if len(items) == 0 || page*10 >= count {
			break
		}
	}
	if len(matches) == 0 {
		return nil, fmt.Errorf("未在服务 %s 中找到 Pod %s，请核对 --pod", serviceID, podName)
	}
	if len(matches) > 1 {
		return nil, fmt.Errorf("服务 %s 中匹配到多个同名 Pod %s，请同时指定 --cluster-name", serviceID, podName)
	}
	return matches[0], nil
}

func pickServiceHost(cmd *cobra.Command, api *platform.API, serviceID string, interactive bool, input *bufio.Reader, hint string) (platform.Record, error) {
	for page := 1; ; {
		items, count, err := serviceHosts(cmd, api, serviceID, "", page)
		if err != nil {
			return nil, err
		}
		if len(items) == 0 {
			return nil, errors.New("主机列表为空")
		}
		if count == 1 && len(items) == 1 {
			return items[0], nil
		}
		if !interactive {
			return nil, fmt.Errorf("主机无法唯一确定，%s", hint)
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

func podEventValue(record platform.Record, key string) string {
	if key == "lastTimestamp" {
		return dateText(record[key])
	}
	return fieldText(record[key])
}

func queryPodStdout(cmd *cobra.Command, api *platform.API, podName, containerName string) (platform.Record, error) {
	return servicePost(cmd, api, containerPrefix+"queryPodLog", map[string]any{
		"businessId":    api.BusinessID(),
		"podName":       podName,
		"containerName": containerName,
	})
}

func hasContainerState(states []platform.Record, name string) bool {
	for _, state := range states {
		if strings.TrimSpace(state.Text("name")) == name {
			return true
		}
	}
	return false
}

func renderPodStdout(out io.Writer, states []platform.Record, result platform.Record) error {
	for _, state := range states {
		if _, err := fmt.Fprintf(out, "容器名称：%s，重启次数：%s，状态：%s\n",
			fieldText(state["name"]), fieldText(state["restartCount"]), fieldText(state["state"])); err != nil {
			return err
		}
	}
	if _, err := fmt.Fprintln(out, "详细日志："); err != nil {
		return err
	}
	data := result.Object("data")
	if data == nil {
		_, err := fmt.Fprintln(out, "暂无日志内容")
		return err
	}
	raw := data["content"]
	if len(raw) == 0 || string(raw) == "null" {
		_, err := fmt.Fprintln(out, "暂无日志内容")
		return err
	}
	var content string
	if err := json.Unmarshal(raw, &content); err != nil {
		return errors.New("日志响应缺少有效的 content")
	}
	if content == "" {
		_, err := fmt.Fprintln(out, "暂无日志内容")
		return err
	}
	if _, err := io.WriteString(out, content); err != nil {
		return err
	}
	if !strings.HasSuffix(content, "\n") {
		_, err := io.WriteString(out, "\n")
		return err
	}
	return nil
}
