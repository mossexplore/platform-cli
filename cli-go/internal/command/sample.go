package command

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newSample(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "sample-task", Short: "样本任务"}
	period := &cobra.Command{Use: "period", Short: "样本任务执行周期"}
	exec := &cobra.Command{Use: "execution", Short: "样本任务执行记录"}
	period.AddCommand(newSampleExecution(options, load, true))
	exec.AddCommand(newSampleExecution(options, load, false))
	group.AddCommand(newSampleList(options, load), period, exec)
	return group
}

func newSampleList(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "list", Short: "分页查询样本任务，默认使用旧任务管理", Args: positional(0),
		Annotations: map[string]string{"platform": "wiserec"}}
	source := cmd.Flags().String("source", "legacy", "legacy 或 new")
	page, size := pagination(cmd)
	name := cmd.Flags().String("name", "", "按任务名称查询")
	creator := cmd.Flags().String("creator", "", "按创建者查询")
	updater := cmd.Flags().String("updater", "", "按修改者查询")
	types := cmd.Flags().StringArray("type", nil, "任务类型，可重复指定")
	status := cmd.Flags().String("status", "", "旧版使用 all、stopped、started")
	sort := cmd.Flags().String("sort", "", "新版使用 desc")
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, _ []string, api *platform.API, format string) error {
		legacy := *source == "legacy"
		if (!legacy && *source != "new") || *page < 1 || *size < 1 {
			return usageError{errors.New("source 或分页参数无效")}
		}
		if legacy && cmd.Flags().Changed("sort") || !legacy && cmd.Flags().Changed("status") {
			return usageError{errors.New("旧版不支持 --sort，新版不支持 --status")}
		}
		if cmd.Flags().Changed("status") && *status != "all" && *status != "stopped" && *status != "started" ||
			cmd.Flags().Changed("sort") && *sort != "desc" {
			return usageError{errors.New("status 或 sort 无效")}
		}
		taskTypes := sampleNewTypes
		if legacy {
			taskTypes = sampleLegacyTypes
		}
		unique := map[string]bool{}
		keys := []string{}
		for _, kind := range *types {
			if _, ok := taskTypes[kind]; !ok {
				return usageError{fmt.Errorf("不支持的任务类型 %s", kind)}
			}
			if !unique[kind] {
				keys = append(keys, kind)
				unique[kind] = true
			}
		}
		body := map[string]any{"businessId": api.BusinessID(), "pageSize": *size}
		route, countKey, itemsKey := "/ai/backend/dpp/proxy/featureStore/v2/task/list", "total", "list"
		if legacy {
			route, countKey, itemsKey = "/ai/backend/dpp/proxy/schedule-service/task/list", "count", "taskInfos"
			body["pageIndex"] = *page
			body["category"] = labelOrID(strings.Join(keys, ","), "feature_preprocess_realtime,feature_preprocess_offline,feature_assemble,label_assemble")
			if value, ok := map[string]string{"stopped": "STOP", "started": "START"}[*status]; ok {
				body["taskStatusList"] = value
			}
			for flag, field := range map[string]string{"name": "taskName", "creator": "createUser", "updater": "updateUser"} {
				if cmd.Flags().Changed(flag) {
					body[field], _ = cmd.Flags().GetString(flag)
				}
			}
		} else {
			body["pageNo"], body["sortType"], body["taskName"], body["createBy"], body["updateBy"] = *page, "desc", *name, *creator, *updater
			if len(keys) > 0 {
				body["taskSubCategoryList"] = keys
			}
		}
		result, err := servicePost(cmd, api, route, sampleEnvelope(body))
		if err != nil {
			return err
		}
		if !legacy {
			result = result.Object("data")
		}
		total, err := sampleCount(result[countKey])
		if err != nil {
			return err
		}
		items, err := sampleItems(result[itemsKey], !legacy)
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), map[string]any{"source": *source, "page": *page, "pageSize": *size, "total": total, "items": items})
		}
		sourceName := "任务管理（新）"
		cols := []recordColumn{{"任务ID", "taskId"}, {"任务名称", "taskName"}, {"任务类型", "taskSubCategoryCn"},
			{"创建者", "createBy"}, {"修改者", "updateBy"}, {"创建时间", "createTime"}, {"开始执行时间", "latestRunTime"},
			{"最近修改时间", "updateTime"}, {"描述", "description"}, {"任务状态", "taskStateCn"}}
		if legacy {
			sourceName = "任务管理（旧）"
			cols = []recordColumn{{"任务ID", "taskId"}, {"任务名称", "taskName"}, {"任务类型", "category"}, {"创建者", "createUser"},
				{"修改者", "updateUser"}, {"最近修改时间", "updateTime"}, {"描述", "description"}}
		}
		fmt.Fprintln(cmd.OutOrStdout(), "来源："+sourceName)
		err = renderRecordTable(cmd.OutOrStdout(), cols, items, sampleTaskValue)
		if err != nil {
			return err
		}
		if len(items) == 0 {
			fmt.Fprintln(cmd.OutOrStdout(), "暂无样本任务")
		}
		return sampleFooter(cmd, *page, *size, total)
	})
	return cmd
}

func newSampleExecution(options Options, load loadConfig, periods bool) *cobra.Command {
	help := "分页查询样本任务的执行记录"
	if periods {
		help = "分页查询样本任务的执行周期"
	}
	cmd := &cobra.Command{Use: "list TASK_ID", Short: help, Args: positional(1), Annotations: map[string]string{"platform": "wiserec"}}
	page := cmd.Flags().Int("page", 1, "查询页码")
	defaultSize := 10
	if periods {
		defaultSize = 20
	}
	size := cmd.Flags().Int("page-size", defaultSize, "每页条数")
	var start, end string
	var states []string
	var history bool
	if periods {
		cmd.Flags().StringVar(&start, "start-time", "", "开始北京时间 YYYY-MM-DD HH:mm:ss")
		cmd.Flags().StringVar(&end, "end-time", "", "结束北京时间 YYYY-MM-DD HH:mm:ss")
		cmd.Flags().StringArrayVar(&states, "state", nil, "运行状态，可重复指定")
	} else {
		cmd.Flags().BoolVar(&history, "include-history", false, "包含历史执行实例")
	}
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if *page < 1 || *size < 1 {
			return usageError{errors.New("分页参数须为正整数")}
		}
		body := map[string]any{"pageIndex": *page, "pageSize": *size, "taskId": args[0]}
		var request any = body
		route, itemsKey := "/ai/backend/dpp/featuretask/queryScheduleTaskList", "jobs"
		if periods {
			route, itemsKey = "/ai/backend/dpp/proxy/schedule-service/task/instances/query", "instances"
			body["businessId"], body["latestFlag"], body["sortField"], body["taskClass"] = api.BusinessID(), true, "periodDate", 3
			for _, input := range []struct{ key, flag, value string }{{"periodStartTime", "start-time", start}, {"periodEndTime", "end-time", end}} {
				if !cmd.Flags().Changed(input.flag) {
					continue
				}
				instant, err := time.ParseInLocation("2006-01-02 15:04:05", input.value, beijing)
				if err != nil {
					return usageError{errors.New("时间必须为有效的北京时间，格式 YYYY-MM-DD HH:mm:ss")}
				}
				body[input.key] = instant.UnixMilli()
			}
			first, firstOK := body["periodStartTime"].(int64)
			last, lastOK := body["periodEndTime"].(int64)
			if firstOK && lastOK && first > last {
				return usageError{errors.New("start-time 不得晚于 end-time")}
			}
			seen := map[string]bool{}
			keys := []string{}
			for _, state := range states {
				if _, ok := sampleStates[state]; !ok {
					return usageError{fmt.Errorf("不支持的运行状态 %s", state)}
				}
				if !seen[state] {
					keys = append(keys, state)
					seen[state] = true
				}
			}
			if len(keys) > 0 {
				body["states"] = keys
			}
			request = sampleEnvelope(body)
		} else {
			body["source"], body["latestFlag"] = "history", "true"
			if history {
				body["latestFlag"] = "all"
			}
		}
		result, err := servicePost(cmd, api, route, request)
		if err != nil {
			return err
		}
		items, err := responseRecords(result, itemsKey)
		if err != nil {
			return err
		}
		total, err := sampleCount(result["count"])
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), map[string]any{"taskId": args[0], "page": *page, "pageSize": *size, "total": total, "items": items})
		}
		fmt.Fprintln(cmd.OutOrStdout(), "任务 ID："+args[0])
		if periods {
			for index, item := range items {
				state := fieldText(item["state"])
				fmt.Fprintf(cmd.OutOrStdout(), "%d %s %s\n", index+1, fieldText(item["period"]), labelOrID(sampleStates[state], state))
			}
			if len(items) == 0 {
				fmt.Fprintln(cmd.OutOrStdout(), "暂无执行周期")
			}
		} else if len(items) > 0 {
			cols := []recordColumn{{"JOB ID", "jobId"}, {"算法名称", "algorithmName"}, {"状态", "status"}, {"文件大小", "fileSize"},
				{"周期时间", "periodDate"}, {"执行时长", "runningTime"}, {"最新实例", "latestFlag"}, {"检查时间", "checkTime"},
				{"开始时间", "createTime"}, {"结束时间", "statusTime"}}
			err := renderRecordTable(cmd.OutOrStdout(), cols, items, func(row platform.Record, key string) string {
				if key == "status" {
					return labelOrID(trainStatus[row.Text(key)], fieldText(row[key]))
				}
				return catalogValue(row, key)
			})
			if err != nil {
				return err
			}
		} else {
			fmt.Fprintln(cmd.OutOrStdout(), "暂无执行记录")
		}
		return sampleFooter(cmd, *page, *size, total)
	})
	return cmd
}

func sampleEnvelope(body any) map[string]any {
	return map[string]any{"version": "1.0", "meta": map[string]string{"uuid": localstate.NewID()}, "data": body}
}

func sampleCount(raw json.RawMessage) (int, error) {
	var count *int
	if json.Unmarshal(raw, &count) != nil || count == nil || *count < 0 {
		return 0, errors.New("样本任务响应缺少有效总数")
	}
	return *count, nil
}

func sampleItems(raw json.RawMessage, allowNested bool) ([]platform.Record, error) {
	var items []json.RawMessage
	if json.Unmarshal(raw, &items) != nil || items == nil {
		return nil, errors.New("样本任务响应缺少有效任务数组")
	}
	withRows := []platform.Record{}
	for _, raw := range items {
		if allowNested && bytes.HasPrefix(raw, []byte("[")) {
			nested, err := sampleItems(raw, false)
			if err != nil {
				return nil, err
			}
			withRows = append(withRows, nested...)
			continue
		}
		var row platform.Record
		if json.Unmarshal(raw, &row) != nil || row == nil {
			return nil, errors.New("样本任务数组含无效条目")
		}
		withRows = append(withRows, row)
	}
	return withRows, nil
}

func sampleFooter(cmd *cobra.Command, page, size, total int) error {
	_, err := fmt.Fprintf(cmd.OutOrStdout(), "第 %d 页 · 每页 %d 条 · 共 %d 条\n", page, size, total)
	return err
}

func sampleTaskValue(row platform.Record, key string) string {
	value := fieldText(row[key])
	switch key {
	case "taskSubCategoryCn":
		if value == "-" {
			code := fieldText(row["taskSubCategory"])
			return labelOrID(sampleNewTypes[code], code)
		}
	case "taskStateCn":
		if value == "-" {
			code := labelOrID(row.Text("taskState"), fieldText(row["taskStatus"]))
			return labelOrID(map[string]string{"START": "启动", "STOP": "停止"}[code], code)
		}
	case "category":
		return labelOrID(sampleLegacyTypes[value], value)
	case "createTime", "updateTime", "latestRunTime":
		return dateText(row[key])
	}
	return value
}

var sampleLegacyTypes = map[string]string{
	"feature_preprocess_realtime": "特征预处理(实时)",
	"feature_preprocess_offline":  "特征预处理(离线)",
	"feature_assemble":            "特征装配",
	"label_assemble":              "标签装配",
	"feature_monitor":             "样本监控",
	"new_feature_assemble":        "新特征装配",
	"spark_jar":                   "spark_jar",
}

var sampleNewTypes = map[string]string{
	"FEATURE_ASSEMBLE":           "特征装配任务",
	"LABEL_ASSEMBLE":             "标签装配任务",
	"FEATURE_SYNC":               "特征同步任务",
	"FEATURE_IMPORT_OFFLINE":     "离线特征导入任务",
	"FEATURE_IMPORT_REALTIME":    "实时特征导入任务",
	"OFFLINE_FEATURE_SYNC":       "离线特征回流同步任务",
	"FEATURE_PREPROCESS_OFFLINE": "预处理任务",
	"FEATURE_QUALITY_MONITOR":    "监控任务",
	"OFFLINE_FEEDBACK":           "离线回流任务",
	"REAL_TIME_FEEDBACK":         "实时回流任务",
	"REALTIME_LABEL_CALC":        "实时标签计算任务",
	"SAMPLE_GENERATION_OFFLINE":  "样本生成离线任务",
	"SAMPLE_GENERATION_REALTIME": "样本生成实时任务",
}

var sampleStates = map[string]string{
	"INIT":                 "初始化",
	"CANCELED":             "已取消",
	"QUEUE":                "排队中",
	"APPLY_FOR_RESOURCE":   "申请资源",
	"WAIT_FOR_QUOTA_QUEUE": "等待中",
	"RUNNING":              "运行中",
	"COMPLETED":            "运行成功",
	"FAILED":               "执行失败",
	"LACK_RESOURCE":        "资源不足",
	"TIMEOUT":              "超时",
	"QUEUE_TIMEOUT":        "排队超时",
	"QUOTA_WAIT_TIMEOUT":   "配额等待失败",
	"FORCE_STOP":           "强制停止",
}
