package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
	"golang.org/x/term"
)

func newDeployModel(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "deploy MODEL_ID", Short: "使用部署模板将模型部署为服务", Args: positional(1)}
	template := cmd.Flags().String("template", "", "部署模板 ID")
	_ = cmd.MarkFlagRequired("template")
	serviceTimeout := cmd.Flags().Int("service-timeout", 0, "调用方最大容忍超时时间（ms）")
	limit := cmd.Flags().Int("execute-limit", 0, "单实例最大并发数")
	qps := cmd.Flags().Int("qps", 0, "单实例最大 QPS")
	update := cmd.Flags().String("update-mode", "rolling", "rolling 或 in-place")
	health := cmd.Flags().String("health-check-mode", "default", "健康检查模式")
	port := cmd.Flags().Int("health-port", 18090, "容器健康检查端口")
	description := cmd.Flags().String("description", "", "服务文档描述")
	requestFile := cmd.Flags().String("request-file", "", "UTF-8 输入报文文件")
	responseFile := cmd.Flags().String("response-file", "", "UTF-8 输出报文文件")
	dry := cmd.Flags().Bool("dry-run", false, "仅查询并预览完整部署配置")
	yes := cmd.Flags().Bool("yes", false, "跳过提交确认")
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		id := strings.TrimSpace(*template)
		if id == "" {
			return usageError{errors.New("部署模板 ID 不能为空")}
		}
		if !*dry && !*yes {
			in, ok := cmd.InOrStdin().(*os.File)
			if !ok || !term.IsTerminal(int(in.Fd())) {
				return errors.New("非交互环境提交部署必须指定 --yes，可先使用 --dry-run 预览")
			}
		}
		opts := platform.DeployOptions{UpdateMode: *update, HealthMode: *health, HealthPort: *port, Description: *description}
		for key, binding := range map[string]struct {
			value *int
			field **int
			min   int
		}{
			"service-timeout": {serviceTimeout, &opts.Timeout, 1}, "execute-limit": {limit, &opts.Limit, 0}, "qps": {qps, &opts.QPS, 1},
		} {
			if cmd.Flags().Changed(key) {
				if *binding.value < binding.min {
					return usageError{fmt.Errorf("%s 超出范围", key)}
				}
				*binding.field = binding.value
			}
		}
		for _, doc := range []struct {
			path  string
			value *string
		}{{*requestFile, &opts.RequestContent}, {*responseFile, &opts.ResponseContent}} {
			if doc.path != "" {
				data, err := os.ReadFile(doc.path)
				if err != nil || !utf8.Valid(data) {
					return errors.New("无法读取 UTF-8 服务报文文件")
				}
				*doc.value = string(data)
			}
		}
		body, err := api.PrepareDeploy(cmd.Context(), args[0], id, opts)
		if err != nil {
			return err
		}
		if *dry && format == "json" {
			return output.JSON(cmd.OutOrStdout(), body)
		}
		out := cmd.OutOrStdout()
		if format == "json" {
			out = cmd.ErrOrStderr()
		}
		if err := renderDeployPreview(out, body); err != nil {
			return err
		}
		if *dry {
			_, err = fmt.Fprintln(cmd.ErrOrStderr(), "预览完成，未提交部署")
			return err
		}
		approved, err := approve(cmd, "确认提交以上部署配置？")
		if !approved || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消部署")
			return err
		}
		response, err := api.Mutation(cmd.Context(), http.MethodPost, platform.PublishPath, nil, body)
		if err != nil {
			return err
		}
		var envelope platform.Record
		var code *int
		if json.Unmarshal(response, &envelope) != nil || json.Unmarshal(envelope.Object("result")["code"], &code) != nil || code == nil {
			return errors.New("部署提交结果未确认，请先查询服务状态再决定是否重试")
		}
		result := envelope.Object("result")
		if format == "json" {
			var value any = response
			if agentMode(cmd) {
				value = result
			}
			if err := output.JSON(cmd.OutOrStdout(), value); err != nil {
				return err
			}
		} else if *code == 0 {
			fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 部署成功")
			fmt.Fprintf(cmd.OutOrStdout(), "服务 ID：%s\n结果：%s\n", labelOrID(result.Text("serviceId"), "-"), result.Text("des"))
		}
		if *code != 0 {
			return fmt.Errorf("部署失败：code=%d", *code)
		}
		return nil
	})
	return cmd
}

func renderDeployPreview(out io.Writer, payload map[string]any) error {
	data := payload["data"].(map[string]any)
	sections := []struct {
		title string
		value any
	}{
		{"1、基本信息", data["serviceInfo"]}, {"2、部署区域", data["serviceBlocks"]},
		{"3、扩展参数", data["extendConfiguration"]}, {"4、服务文档", data["serviceDocument"]},
	}
	for _, section := range sections {
		fmt.Fprintln(out, section.title)
		raw, err := json.Marshal(section.value)
		if err != nil {
			return err
		}
		if err := output.ResultTable(out, raw); err != nil {
			return err
		}
	}
	return nil
}
