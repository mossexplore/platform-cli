package command

import (
	"encoding/json"
	"fmt"
	"io"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func renderTrainDetail(out io.Writer, data platform.Record, format string) error {
	if format == "json" {
		return output.JSON(out, data)
	}
	info := data.Object("taskInfo")
	parameter := info.Object("parameter")
	resource := info.Object("resource")
	environment := info.Object("environment")
	config := info.Object("taskConfig")
	base := info.Object("baseInfo")
	mode := trainAlias(base["trainMode"], "singleNodeSingleGpu", "单机单卡")
	region := trainAlias(environment["region"], "cn-north-2", "北京二")
	source := trainAlias(info["source"], "wisemlops", "WiseMLOps")
	timeout := config["cronTimeOut"]
	if fieldText(timeout) == "-" {
		timeout = config.Object("scheduling")["cronTimeOut"]
	}
	fmt.Fprintln(out, "基本信息")
	fields := output.Fields{
		{Key: "租户", Value: fieldText(data["businessId"])}, {Key: "团队", Value: fieldText(info["teamId"])},
		{Key: "任务名称", Value: fieldText(data["name"])}, {Key: "任务类型", Value: fieldText(info["category"])},
		{Key: "配额内等待", Value: yesNo(resource["acceptQueue"])}, {Key: "训练模式", Value: mode},
		{Key: "区域", Value: region}, {Key: "分布式框架", Value: fieldText(info["distFramework"])},
		{Key: "业务子场景", Value: fieldText(info["subScene"])}, {Key: "领域", Value: fieldText(info["scope"])},
		{Key: "镜像", Value: fieldText(environment["imagePackageId"])}, {Key: "资源规格", Value: fieldText(resource["imageSpecificInfo"])},
		{Key: "敏感", Value: yesNo(config["isSensitive"])}, {Key: "节点数", Value: fieldText(resource["infraSize"])},
		{Key: "历史记录数目", Value: fieldText(config["maxHistoryNum"])}, {Key: "排队时间(min)", Value: fieldText(config["maxQueueTime"])},
		{Key: "超时时间(s)", Value: fieldText(timeout)}, {Key: "输出归档", Value: yesNo(config["autoArchive"])},
		{Key: "入口脚本", Value: fieldText(parameter["startScript"])}, {Key: "算法", Value: fieldText(environment["algorithmName"])},
		{Key: "算法版本", Value: fieldText(environment["algorithmVersion"])}, {Key: "执行引擎", Value: fieldText(info["trainEngine"])},
		{Key: "创建者", Value: fieldText(info["createUser"])}, {Key: "创建时间", Value: dateText(data["createTime"])},
		{Key: "DMQ Topic名称", Value: fieldText(info["dmq"])}, {Key: "基线/共享", Value: "-"},
		{Key: "来源", Value: source}, {Key: "最大重试次数", Value: fieldText(config["maxRetryTimes"])},
		{Key: "过期时间（天）", Value: fieldText(info["expireDate"])},
	}
	if err := fields.Table(out); err != nil {
		return err
	}
	var sample platform.Record
	if samples := recordList(info["samples"]); len(samples) > 0 {
		sample = samples[0]
	}
	sections := []struct {
		title string
		data  json.RawMessage
		cols  []recordColumn
	}{
		{"数据集", sample["dataSets"], []recordColumn{{"数据集目录", "dataSetDirectory"}, {"数据集名称", "dataSetName"}, {"区域", "region"}, {"来源", ""}}},
		{"输出引用", info["quoteModels"], []recordColumn{{"输出目录", "modelDirectory"}, {"输出名称", "modelName"}}},
		{"组合配置引用", sample["mutiGroupRefInfos"], []recordColumn{{"文件名", "mutiGroupRefName"}, {"组合配置名称", "mutiGroupName"}}},
		{"特征集引用", sample["featureSetRefInfos"], []recordColumn{{"文件名", "setRefName"}, {"特征集名称", "setName"}}},
		{"参数", parameter["algorithmConfig"], []recordColumn{{"参数", "paramKey"}, {"值", "paramValue"}}},
	}
	for _, section := range sections {
		fmt.Fprintln(out, section.title)
		items := recordList(section.data)
		if len(items) == 0 {
			fmt.Fprintln(out, "-")
			continue
		}
		if err := renderRecordTable(out, section.cols, items, func(item platform.Record, key string) string {
			if key == "" {
				return source
			}
			return fieldText(item[key])
		}); err != nil {
			return err
		}
	}
	fmt.Fprintln(out, "自定义参数")
	value := parameter.Text("customizeConfig")
	if strings.TrimSpace(value) == "" {
		value = "-"
	}
	if json.Valid([]byte(value)) {
		return output.JSON(out, json.RawMessage(value))
	}
	_, err := fmt.Fprintln(out, strings.ReplaceAll(value, `\n`, "\n"))
	return err
}

func trainAlias(value json.RawMessage, source, translated string) string {
	if text := fieldText(value); text == source {
		return translated
	}
	return fieldText(value)
}

func yesNo(value json.RawMessage) string {
	switch string(value) {
	case "true":
		return "是"
	case "false":
		return "否"
	}
	return fieldText(value)
}

func recordList(raw json.RawMessage) []platform.Record {
	var items []json.RawMessage
	_ = json.Unmarshal(raw, &items)
	records := []platform.Record{}
	for _, item := range items {
		var row platform.Record
		if json.Unmarshal(item, &row) == nil && row != nil {
			records = append(records, row)
		}
	}
	return records
}
