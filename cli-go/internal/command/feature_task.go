package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newFeatureTask(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "feature-task", Short: "特征任务"}
	const taskPrefix = "/ai/backend/mtp/traintask/"
	fixed := defaultFields("taskType scene subScene cronFlag depTask teamId noRunDays updateUser trainEngine trainMode distFramework region scope subDataZoneId",
		"", "noticeTime jobStatus taskTags tags reverseTaskTags reverseTags")
	fixed["taskType1"], fixed["private"], fixed["running"] = "ALL", false, false
	list := catalogQuery{route: taskPrefix + "queryList", command: "list", summary: "分页查询当前业务下的特征任务", paged: true,
		nameHelp: "按特征任务名称筛选（模糊查询；传入 '名称,名称' 可精确查询）", strings: []string{"name", "category", "create-user"}, defaults: map[string]string{"category": "dpp-all"},
		fixed: fixed, assign: map[string]string{"name": "taskName", "category": "category", "create-user": "createUser"},
		body: func(body map[string]any, cmd *cobra.Command, args []string, api *platform.API) (any, error) {
			if _, supported := featureTaskTypes[body["category"].(string)]; !supported {
				return nil, usageError{errors.New("不支持的 category")}
			}
			return withBusiness(body, cmd, args, api)
		},
		items: "taskInfos", total: "count", totalJSON: "count", empty: "暂无特征任务", value: featureTaskValue,
		columns: []recordColumn{{"任务 ID", "taskId"}, {"任务名称", "taskName"}, {"任务类型", "taskType"}, {"业务场景", "scene"},
			{"状态", "jobStatus"}, {"创建者", "createUser"}, {"修改者", "updateUser"}, {"更新时间", "updateTime"}, {"大小", "fileSize"}, {"描述", "description"}},
	}
	detail := &cobra.Command{Use: "detail TASK_ID", Short: "查询特征任务详情", Args: positional(1)}
	outputFlag(detail)
	detail.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		payload, err := api.JSON(cmd.Context(), http.MethodPost, taskPrefix+"queryDetail", nil, map[string]string{"taskId": args[0], "teamId": ""})
		if err != nil {
			return err
		}
		record, err := platform.Result(payload, "查询特征任务详情", false)
		if err != nil {
			return err
		}
		if record.Object("taskInfo") == nil {
			return errors.New("特征任务详情缺少有效的 taskInfo")
		}
		if format == "json" && !agentMode(cmd) {
			return output.JSON(cmd.OutOrStdout(), record)
		}
		return renderFeatureTask(cmd.OutOrStdout(), record)
	})
	executions := &cobra.Command{Use: "execution", Short: "特征任务执行记录"}
	executionList := catalogQuery{route: "/ai/backend/dpp/featuretask/queryScheduleTaskList", command: "list TASK_ID",
		summary: "分页查询特征任务的执行记录", paged: true, args: 1,
		body: func(body map[string]any, cmd *cobra.Command, args []string, _ *platform.API) (any, error) {
			history, _ := cmd.Flags().GetBool("include-history")
			body["taskId"], body["source"], body["latestFlag"] = args[0], "history", "true"
			if history {
				body["latestFlag"] = "all"
			}
			return body, nil
		},
		items: "jobs", total: "count", totalJSON: "count", empty: "暂无执行记录",
		columns: []recordColumn{{"job ID", "jobId"}, {"算法名称", "algorithmName"}, {"CPU", "cpuSize"}, {"GPU", "gpuSize"}, {"内存", "memorySize"},
			{"状态", "status"}, {"集群", "poolName"}, {"节点数", "infraSize"}, {"大小", "fileSize"}, {"执行时长", "runningTime"},
			{"最新实例", "latestFlag"}, {"检查时间", "checkTime"}, {"开始时间", "createTime"}, {"结束时间", "statusTime"}},
	}.build(options, load)
	executionList.Flags().Bool("include-history", false, "包含历史执行实例")
	logs := &cobra.Command{Use: "logs", Short: "执行记录日志"}
	logs.AddCommand(newFeatureLogs(options, load))
	executions.AddCommand(executionList, logs)
	group.AddCommand(list.build(options, load), detail, executions)
	return group
}

func newFeatureLogs(options Options, load loadConfig) *cobra.Command {
	search := &cobra.Command{Use: "search JOB_ID", Short: "查询和搜索训练日志", Args: positional(1)}
	start := search.Flags().Int("start-line", 1, "起始行")
	end := search.Flags().Int("end-line", 2000, "结束行")
	keywords := search.Flags().StringArray("keyword", nil, "搜索关键词，可重复指定")
	scope := search.Flags().String("scope", "", "A 关键词后，B 关键词前，C 关键词前后")
	lines := search.Flags().Int("scope-lines", 0, "搜索范围行数")
	format := search.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
	search.Annotations = map[string]string{"text_output": "true"}
	search.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if *start < 1 || *end < *start {
			return usageError{errors.New("起始行和结束行范围无效")}
		}
		for _, key := range *keywords {
			if strings.TrimSpace(key) == "" {
				return usageError{errors.New("keyword 不能为空白")}
			}
		}
		data := map[string]any{"jobId": args[0], "businessId": api.BusinessID(), "searchStartLine": *start, "searchEndLine": *end}
		if len(*keywords) > 0 {
			data["keywords"] = *keywords
		}
		if cmd.Flags().Changed("scope") {
			if *scope != "A" && *scope != "B" && *scope != "C" {
				return usageError{errors.New("scope 仅支持 A、B、C")}
			}
			data["searchScope"] = *scope
		}
		if cmd.Flags().Changed("scope-lines") {
			if *lines < 1 {
				return usageError{errors.New("scope-lines 必须为正数")}
			}
			data["searchScopeLine"] = *lines
		}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, "/ai/backend/mtp/traintask/advancedLogSearch", nil,
			map[string]any{"version": "1.0", "meta": map[string]string{"uuid": localstate.NewID()}, "data": data})
		if err != nil {
			return err
		}
		record, err := platform.Result(payload, "查询特征任务日志", false)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			logs, err := responseRecords(record, "logs")
			if err != nil {
				return err
			}
			return agentResult(cmd, map[string]any{"logs": logs})
		}
		if strings.EqualFold(*format, "json") {
			return output.JSON(cmd.OutOrStdout(), payload)
		}
		var logs []json.RawMessage
		if json.Unmarshal(record["logs"], &logs) != nil || logs == nil {
			return errors.New("日志响应缺少有效的 logs 数组")
		}
		if len(logs) == 0 {
			return nil
		}
		var first platform.Record
		var log *string
		if json.Unmarshal(logs[0], &first) != nil || json.Unmarshal(first["log"], &log) != nil || log == nil {
			return errors.New("日志响应缺少有效的 logs[0].log 文本")
		}
		_, err = io.WriteString(cmd.OutOrStdout(), *log)
		return err
	})
	return search
}

func featureTaskValue(record platform.Record, field string) string {
	if field == "taskType" {
		if value := featureTaskTypes[record.Text(field)]; value != "" {
			return value
		}
	}
	return catalogValue(record, field)
}

func renderFeatureTask(out io.Writer, result platform.Record) error {
	info := result.Object("taskInfo")
	algorithm := result.Object("algorithmInfo")
	cols := []recordColumn{{"租户", "businessId"}, {"团队", "teamId"}, {"任务名称", "taskName"}, {"任务类型", "taskType"},
		{"配额内等待", "acceptQueue"}, {"训练模式", "trainMode"}, {"区域", "region"}, {"分布式框架", "distFramework"},
		{"业务子场景", "subScene"}, {"领域", "scope"}, {"资源规格", "imageSpecificInfo"}, {"敏感", "isSensitive"},
		{"镜像", "imagePackageId"}, {"节点数", "infraSize"}, {"历史记录数目", "maxHistoryNum"}, {"排队时间(min)", "maxQueueTime"},
		{"超时时间(s)", "cronTimeOut"}, {"输出归档", "autoArchive"}, {"入口脚本", "startScript"}, {"算法", "algorithmName"},
		{"算法版本", "algorithmVersion"}, {"执行引擎", "trainEngine"}, {"创建者", "createUser"}, {"创建时间", "createTime"},
		{"DMQ Topic名称", "dmq"}, {"基线/共享", ""}, {"来源", "source"}}
	if output.IsAgent(out) {
		r := agentRecord(info, columnKeys(cols, "taskId", "dataSets", "featureSetRefInfos", "params", "trainTaskCron", "customizeConfig")...)
		result := map[string]any{"taskInfo": r}
		if projected := agentRecord(algorithm, "algorithmName", "algorithmVersion", "algorithmId"); len(projected) > 0 {
			result["algorithmInfo"] = projected
		}
		return output.JSON(out, result)
	}
	fields := output.Fields{}
	for _, field := range cols {
		value := catalogValue(info, field.key)
		switch field.key {
		case "acceptQueue", "isSensitive", "autoArchive":
			value = yesNo(info[field.key])
		case "taskType":
			value = trainAlias(info[field.key], "train_fi", "Train Fi")
		case "region":
			value = trainAlias(info[field.key], "cn-north-2", "北京二")
		case "source":
			value = trainAlias(info[field.key], "wisemlops", "WiseMLOps")
		case "algorithmName", "algorithmVersion":
			value = fieldText(algorithm[field.key])
		case "cronTimeOut":
			value = fieldText(info.Object("trainTaskCron")[field.key])
		}
		fields = append(fields, output.Field{Key: field.title, Value: value})
	}
	fmt.Fprintln(out, "基本信息")
	if err := fields.Table(out); err != nil {
		return err
	}
	for _, section := range []struct {
		title, key string
		cols       []recordColumn
	}{
		{"数据集", "dataSets", []recordColumn{{"数据集目录", "dir"}, {"数据集名称", "dataSetList"}}},
		{"特征集引用", "featureSetRefInfos", []recordColumn{{"文件名", "setRefName"}, {"特征集名称", "setName"}, {"特征集版本", "version"}}},
		{"参数", "params", []recordColumn{{"参数", "paramKey"}, {"值", "paramValue"}}},
	} {
		fmt.Fprintln(out, section.title)
		items := recordList(info[section.key])
		if len(items) == 0 {
			fmt.Fprintln(out, "-")
			continue
		}
		err := renderRecordTable(out, section.cols, items, func(item platform.Record, field string) string {
			if field == "dataSetList" {
				var names []string
				for _, dataset := range recordList(item[field]) {
					names = append(names, fieldText(dataset["dataSetName"]))
				}
				return strings.Join(names, ",")
			}
			return fieldText(item[field])
		})
		if err != nil {
			return err
		}
	}
	fmt.Fprintln(out, "自定义参数")
	custom := labelOrID(info.Text("customizeConfig"), "-")
	if json.Valid([]byte(custom)) {
		return output.JSON(out, json.RawMessage(custom))
	}
	_, err := fmt.Fprintln(out, strings.ReplaceAll(custom, `\n`, "\n"))
	return err
}

var featureTaskTypes = map[string]string{
	"dpp-all":                     "全部",
	"feature_preprocess_realtime": "特征预处理(实时)",
	"train_fi":                    "FI直连任务",
	"data_sync":                   "数据同步任务",
	"data-preproc":                "数据预处理任务",
	"feature_generate":            "特征生成任务",
	"feature_evaluation":          "特征评估任务",
	"feature_improve":             "特征加工任务",
	"work_flow":                   "特征工作流任务",
	"feature-push":                "特征同步任务",
	"train_spark":                 "Spark训练任务",
	"train_fi_sync_hdfs":          "FI直连同步HDFS任务",
	"train_fi_data_monitor":       "FI直连数据监控任务",
	"generate_samples":            "样本生成任务",
	"sample-monitor":              "样本监控任务",
	"online_storage":              "在线存储任务",
	"streaming_feature":           "流特征任务",
}
