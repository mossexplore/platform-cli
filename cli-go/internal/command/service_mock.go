package command

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"unicode/utf8"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const servicePrefix = "/ai/backend/mep/services/"
const containerPrefix = servicePrefix + "rtcContainer/"

func servicePost(cmd *cobra.Command, api *platform.API, path string, body any) (platform.Record, error) {
	raw, err := api.JSON(cmd.Context(), http.MethodPost, path, nil, body)
	if err != nil {
		return nil, err
	}
	return platform.Result(raw, cmd.Short, false)
}

func serviceHosts(cmd *cobra.Command, api *platform.API, id, ip string, page int) ([]platform.Record, int, error) {
	record, err := servicePost(cmd, api, containerPrefix+"queryServiceHostList", map[string]any{
		"businessId": api.BusinessID(), "serviceId": id, "status": "", "hostIp": ip, "clusterName": "",
		"preheatStatus": "ALL", "quotaType": nil, "pageIndex": page, "pageSize": 10,
	})
	if err != nil {
		return nil, 0, err
	}
	rows, err := responseRecords(record, "data")
	var total *int
	if err != nil {
		return nil, 0, err
	}
	if json.Unmarshal(record["count"], &total) != nil || total == nil || *total < 0 {
		return nil, 0, errors.New("主机列表缺少有效的 count")
	}
	return rows, *total, nil
}

func responseRecords(record platform.Record, key string) ([]platform.Record, error) {
	var rows []platform.Record
	if json.Unmarshal(record[key], &rows) != nil || rows == nil {
		return nil, fmt.Errorf("响应缺少有效的 %s 列表", key)
	}
	for _, row := range rows {
		if row == nil {
			return nil, fmt.Errorf("响应 %s 包含无效条目", key)
		}
	}
	return rows, nil
}

func newServiceMock(options Options, load loadConfig, host bool) *cobra.Command {
	short := "使用样例报文测试服务响应"
	if host {
		short = "使用样例报文测试指定主机"
	}
	cmd := &cobra.Command{Use: "mock SERVICE_ID", Short: short, Args: positional(1)}
	tag := cmd.Flags().Int("transmission-tag", 0, "0 为直接调用，1 为透传")
	file := cmd.Flags().String("request-sample-file", "", "本地 UTF-8 JSON 样例报文文件")
	ip := ""
	if host {
		cmd.Flags().StringVar(&ip, "pod-ip", "", "用于匹配目标主机的 Pod IP")
		_ = cmd.MarkFlagRequired("pod-ip")
	}
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if *tag != 0 && *tag != 1 {
			return usageError{errors.New("transmission-tag 仅支持 0 或 1")}
		}
		sample := ""
		if *file != "" {
			raw, err := os.ReadFile(*file)
			if err != nil {
				return err
			}
			sample = strings.TrimPrefix(string(raw), "\ufeff")
			if !utf8.Valid(raw) || !json.Valid([]byte(sample)) {
				return usageError{errors.New("样例报文须为 UTF-8 JSON")}
			}
		}
		var node map[string]string
		if host {
			if strings.TrimSpace(ip) == "" {
				return usageError{errors.New("Pod IP 不能为空")}
			}
			items, count, err := serviceHosts(cmd, api, args[0], strings.TrimSpace(ip), 1)
			if err != nil {
				return err
			}
			if count != 1 || len(items) != 1 {
				return errors.New("无法唯一匹配主机，请核对 --pod-ip")
			}
			id := fieldText(items[0]["nodeId"])
			address := items[0].Text("nodeHost")
			if id == "-" || strings.TrimSpace(address) == "" {
				return errors.New("主机缺少有效的 nodeId 或 nodeHost")
			}
			node = map[string]string{"hostId": id, "hostAddress": address}
		}
		body := map[string]string{"serviceId": args[0]}
		base, err := servicePost(cmd, api, containerPrefix+"queryServiceBaseInfoDetail", body)
		if err != nil {
			return err
		}
		info := base.Object("serviceInfo")
		name, version, business := info.Text("serviceName"), info.Text("serviceVersion"), base.Object("modelInfo").Text("businessId")
		if strings.TrimSpace(name) == "" || strings.TrimSpace(version) == "" || strings.TrimSpace(business) == "" {
			return errors.New("服务基本信息缺少有效的服务名称、版本或租户")
		}
		if sample == "" {
			doc, err := servicePost(cmd, api, servicePrefix+"queryServiceDoc", body)
			if err != nil {
				return err
			}
			document := doc.Object("serviceDocument")
			if document == nil {
				return errors.New("响应缺少有效的服务文档 serviceDocument")
			}
			for key, expected := range map[string]string{"serviceId": args[0], "businessId": business} {
				if _, exists := document[key]; exists && document.Text(key) != expected {
					return fmt.Errorf("服务文档 %s 与目标服务不一致", key)
				}
			}
			sample, err = serviceDocumentSample(document)
			if err != nil {
				return err
			}
		}
		request := map[string]any{"requestSample": sample, "serviceName": name, "serviceVersion": version, "serviceId": args[0],
			"lmsServiceId": "", "algoType": "field-npy", "transmissionTag": *tag, "businessId": business}
		if node != nil {
			request["node"] = node
		}
		raw, err := api.Mutation(cmd.Context(), http.MethodPost, servicePrefix+"serviceMock", nil, map[string]any{"data": request})
		if err != nil {
			return err
		}
		result, err := platform.Result(raw, "测试服务", false)
		if err != nil {
			return err
		}
		return renderServiceMock(cmd, raw, result, format, host)
	})
	return cmd
}

func serviceDocumentSample(document platform.Record) (string, error) {
	raw := bytes.TrimSpace(document["requestContent"])
	if len(raw) == 0 || bytes.Equal(raw, []byte("null")) {
		return "", errors.New("服务文档缺少有效的 requestContent")
	}
	var sample string
	switch raw[0] {
	case '"':
		if err := json.Unmarshal(raw, &sample); err != nil {
			return "", errors.New("服务文档 requestContent 无法解码为 JSON 文本")
		}
		sample = strings.TrimPrefix(sample, "\ufeff")
		if strings.TrimSpace(sample) == "" {
			return "", errors.New("服务文档输入报文为空，请在该服务中补充相关信息后再次调用！")
		}
	case '{', '[':
		// Preserve numbers and formatting when the platform sends structured JSON.
		sample = string(raw)
	default:
		return "", errors.New("服务文档 requestContent 须为 JSON 文本、对象或数组")
	}
	if !json.Valid([]byte(sample)) {
		return "", errors.New("服务文档 requestContent 不是有效 JSON")
	}
	return sample, nil
}

func renderServiceMock(cmd *cobra.Command, raw json.RawMessage, result platform.Record, format string, vertical bool) error {
	nodes, err := responseRecords(result, "nodeList")
	if err != nil {
		return err
	}
	var issues []string
	if len(nodes) == 0 {
		issues = append(issues, "未返回可测试节点")
	}
	for i, node := range nodes {
		name := labelOrID(node.Text("hostName"), fmt.Sprintf("第 %d 个节点", i+1))
		var code *int
		if json.Unmarshal(node["retCode"], &code) != nil || code == nil || *code != 0 {
			issues = append(issues, name+"：节点测试未成功")
		}
		node["mockResponseRaw"] = node["mockResponse"]
		if raw := node.Text("mockResponse"); json.Valid([]byte(raw)) {
			node["mockResponse"] = json.RawMessage(raw)
		} else {
			issues = append(issues, name+"：结果报文无法解析为标准 JSON，保留原文")
		}
	}
	out := cmd.OutOrStdout()
	cols := []recordColumn{{"主机名称", "hostName"}, {"机器规格", "scope"}, {"站点", "domain"},
		{"结果码", "retCode"}, {"结果报文", "mockResponse"}, {"耗时(ms)", "cost"}}
	if format == "json" {
		var envelope platform.Record
		if err := json.Unmarshal(raw, &envelope); err != nil {
			return err
		}
		if err := result.Put("nodeList", nodes); err != nil {
			return err
		}
		if err := envelope.Put("result", result); err != nil {
			return err
		}
		if err := output.JSON(out, envelope); err != nil {
			return err
		}
	} else if vertical {
		for _, node := range nodes {
			fields := output.Fields{}
			for _, col := range cols {
				fields = append(fields, output.Field{Key: col.title, Value: fieldText(node[col.key])})
			}
			if err := fields.Table(out); err != nil {
				return err
			}
		}
	} else if err := renderRecordTable(out, cols, nodes, catalogValue); err != nil {
		return err
	}
	if len(issues) != 0 {
		for _, issue := range issues {
			fmt.Fprintln(cmd.ErrOrStderr(), "[错误]", issue)
		}
		return silentExit(1)
	}
	return nil
}
