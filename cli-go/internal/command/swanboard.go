package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"sort"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const swanPrefix = "/ai/backend/mtp/swanboard/"

func newSwanBoard(options Options, load loadConfig) *cobra.Command {
	mtp := &cobra.Command{Use: "mtp", Short: "MTP 管理"}
	board := &cobra.Command{Use: "swanboard", Short: "训练看板管理"}
	project := &cobra.Command{Use: "project", Short: "训练看板项目管理"}
	namespaces := &cobra.Command{Use: "namespace", Short: "训练看板项目空间管理"}
	projectExperiments := &cobra.Command{Use: "experiment", Short: "训练看板项目实验管理"}
	experiment := &cobra.Command{Use: "experiment", Short: "训练看板实验数据查询"}
	features := &cobra.Command{Use: "feature", Short: "训练看板实验特性"}
	environments := &cobra.Command{Use: "environment", Short: "训练看板实验环境"}
	configs := &cobra.Command{Use: "config", Short: "训练看板实验配置"}
	newLeaf := func(use, name string, args int, f func(*cobra.Command, []string, *platform.API, string) error) *cobra.Command {
		cmd := &cobra.Command{Use: use, Short: name, Args: positional(args), Annotations: map[string]string{"platform": "wiserec"}}
		outputFlag(cmd)
		cmd.RunE = authorized(options, load, f)
		return cmd
	}
	projectList := newLeaf("list", "分页查询训练看板项目", 0, func(cmd *cobra.Command, _ []string, api *platform.API, format string) error {
		page, size, err := swanPagination(cmd)
		if err != nil {
			return err
		}
		team, _ := cmd.Flags().GetString("team-id")
		creator, _ := cmd.Flags().GetString("creator")
		result, err := swanCall(cmd, api, http.MethodPost, "project/list", nil,
			map[string]any{"pageNum": page, "pageSize": size, "businessId": api.BusinessID(), "teamId": team, "creator": creator})
		if err != nil {
			return err
		}
		return showSwanPage(cmd.OutOrStdout(), result, format, page, size, []recordColumn{
			{"项目id", "projectId"}, {"项目名称", "name"}, {"项目描述", "description"}, {"创建者", "creator"}, {"创建时间", "createTime"},
		})
	})
	pagination(projectList)
	projectList.Flags().String("team-id", "", "团队 ID 模糊查询")
	projectList.Flags().String("creator", "", "创建者模糊查询")
	namespaceList := newLeaf("list PROJECT_ID", "查询训练看板项目下的全部项目空间", 1, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		team, _ := cmd.Flags().GetString("team-id")
		result, err := swanCall(cmd, api, http.MethodGet, "namespace/query/"+url.PathEscape(args[0]),
			url.Values{"projectId": {args[0]}, "teamId": {team}, "businessId": {api.BusinessID()}}, nil)
		if err != nil {
			return err
		}
		return showSwanPage(cmd.OutOrStdout(), result, format, 1, 0, []recordColumn{
			{"项目空间id", "namespaceId"}, {"实验id", "projectId"}, {"实验名称", "namespaceName"}, {"描述", "description"}, {"创建时间", "createTime"},
		})
	})
	namespaceList.Flags().String("team-id", "", "团队 ID 模糊查询")
	experimentList := newLeaf("list PROJECT_ID NAMESPACE_ID", "查询项目空间下的全部实验", 2, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		team, _ := cmd.Flags().GetString("team-id")
		result, err := swanCall(cmd, api, http.MethodPost, "experiment/page", nil,
			map[string]string{"projectId": args[0], "namespaceId": args[1], "teamId": team, "businessId": api.BusinessID()})
		if err != nil {
			return err
		}
		data := result.Object("data")
		items, err := swanItems(data["list"])
		if err != nil {
			return err
		}
		if format == "json" {
			total := any(data["total"])
			if len(data["total"]) == 0 {
				total = len(items)
			}
			return output.JSON(cmd.OutOrStdout(), map[string]any{"pageNum": data["pageNum"], "pageSize": data["pageSize"],
				"total": total, "totalPages": data["totalPages"], "items": items})
		}
		return renderRecordTable(cmd.OutOrStdout(), []recordColumn{{"项目实验id", "experimentId"}, {"实验名称", "name"}, {"创建时间", "createTime"}}, items, catalogValue)
	})
	experimentList.Flags().String("team-id", "", "团队 ID 模糊查询")
	featureList := newLeaf("list EXPERIMENT_ID", "查询实验特性", 1, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		page, size, err := swanPagination(cmd)
		if err != nil {
			return err
		}
		result, err := swanFeatures(cmd, api, args[0], page, size)
		if err != nil {
			return err
		}
		return showSwanPage(cmd.OutOrStdout(), result, format, page, size, swanFeatureColumns)
	})
	pagination(featureList)
	environment := newLeaf("get EXPERIMENT_ID", "查询实验环境", 1, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		data, err := swanEnvironment(cmd, api, args[0])
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), data)
		}
		return renderSwanEnvironment(cmd.OutOrStdout(), data)
	})
	metrics := newLeaf("metrics EXPERIMENT_ID", "查询实验指标统计，默认查询 loss 和 accuracy", 1, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		tags, _ := cmd.Flags().GetStringArray("tag")
		data, err := swanMetrics(cmd, api, args[0], tags)
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), data)
		}
		return renderSwanMetrics(cmd.OutOrStdout(), data)
	})
	metrics.Flags().StringArray("tag", []string{"loss", "accuracy"}, "指标名称，可重复传入")
	config := newLeaf("list EXPERIMENT_ID", "查询实验配置", 1, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		data, err := swanConfig(cmd, api, args[0])
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), data)
		}
		return renderSwanConfig(cmd.OutOrStdout(), data)
	})
	inspect := newLeaf("inspect EXPERIMENT_ID", "一次性查询实验的特性、环境、指标和配置", 1, swanInspect)
	namespaces.AddCommand(namespaceList)
	projectExperiments.AddCommand(experimentList)
	project.AddCommand(projectList, namespaces, projectExperiments)
	features.AddCommand(featureList)
	environments.AddCommand(environment)
	configs.AddCommand(config)
	experiment.AddCommand(features, environments, configs, metrics, inspect)
	board.AddCommand(project, experiment)
	mtp.AddCommand(board)
	return mtp
}

var swanFeatureColumns = []recordColumn{{"特征名", "featureName"}, {"扩展参数", "featuresConfig"}}

func swanPagination(cmd *cobra.Command) (int, int, error) {
	page, _ := cmd.Flags().GetInt("page")
	size, _ := cmd.Flags().GetInt("page-size")
	if page < 1 || size < 1 {
		return 0, 0, usageError{errors.New("page 和 page-size 必须为正整数")}
	}
	return page, size, nil
}

func swanCall(cmd *cobra.Command, api *platform.API, method, route string, query url.Values, body any) (platform.Record, error) {
	raw, err := api.JSON(cmd.Context(), method, swanPrefix+route, query, body)
	if err != nil {
		return nil, err
	}
	return platform.Result(raw, "查询训练看板", false)
}

func swanFeatures(cmd *cobra.Command, api *platform.API, id string, page, size int) (platform.Record, error) {
	return swanCall(cmd, api, http.MethodGet, "experiment/"+url.PathEscape(id)+"/feature",
		url.Values{"experimentId": {id}, "businessId": {api.BusinessID()}, "pageIndex": {strconv.Itoa(page)}, "pageSize": {strconv.Itoa(size)}}, nil)
}

func swanEnvironment(cmd *cobra.Command, api *platform.API, id string) (platform.Record, error) {
	result, err := swanCall(cmd, api, http.MethodGet, "label/experiment/"+url.PathEscape(id),
		url.Values{"experimentId": {id}, "businessId": {api.BusinessID()}}, nil)
	if err != nil {
		return nil, err
	}
	var array []json.RawMessage
	if json.Unmarshal(result["data"], &array) == nil && array != nil && len(array) == 0 {
		return platform.Record{}, nil
	}
	return dataRecord(result)
}

func swanConfig(cmd *cobra.Command, api *platform.API, id string) (platform.Record, error) {
	result, err := swanCall(cmd, api, http.MethodGet, "experiment/"+url.PathEscape(id)+"/config",
		url.Values{"businessId": {api.BusinessID()}}, nil)
	if err != nil {
		return nil, err
	}
	if len(result["data"]) == 0 {
		return platform.Record{}, nil
	}
	return dataRecord(result)
}

func swanMetrics(cmd *cobra.Command, api *platform.API, id string, tags []string) ([]platform.Record, error) {
	metrics := []platform.Record{}
	for _, tag := range tags {
		tag = strings.TrimSpace(tag)
		if tag == "" {
			return nil, usageError{errors.New("指标名称不能为空")}
		}
		result, err := swanCall(cmd, api, http.MethodGet, "tag/experiment/"+url.PathEscape(id)+"/"+url.PathEscape(tag)+"/stats",
			url.Values{"businessId": {api.BusinessID()}}, nil)
		if err != nil {
			return nil, err
		}
		data, err := dataRecord(result)
		if err != nil {
			return nil, err
		}
		metrics = append(metrics, data)
	}
	return metrics, nil
}

func swanItems(raw json.RawMessage) ([]platform.Record, error) {
	var source []json.RawMessage
	if json.Unmarshal(raw, &source) != nil || source == nil {
		return nil, errors.New("响应缺少有效列表")
	}
	return recordList(raw), nil
}

func swanPage(record platform.Record, page, size int) (map[string]any, []platform.Record, error) {
	items, err := swanItems(record["data"])
	if err != nil {
		return nil, nil, err
	}
	count := any(len(items))
	if raw := record["count"]; len(raw) > 0 {
		count = raw
	}
	return map[string]any{"page": page, "pageSize": size, "count": count, "items": items}, items, nil
}

func showSwanPage(out io.Writer, record platform.Record, format string, page, size int, columns []recordColumn) error {
	result, items, err := swanPage(record, page, size)
	if err != nil {
		return err
	}
	if format == "json" {
		return output.JSON(out, result)
	}
	return renderRecordTable(out, columns, items, catalogValue)
}

func renderSwanEnvironment(out io.Writer, data platform.Record) error {
	requirements := fieldText(data["requirements"])
	var packages []string
	if json.Unmarshal(data["requirements"], &packages) == nil && packages != nil {
		requirements = labelOrID(strings.Join(packages, "\n"), "-")
	}
	return output.Table(out, []string{"Python版本", "系统硬件CPU", "系统硬件Memory", "Python库名称"},
		[][]string{{fieldText(data["python"]), fieldText(data.Object("cpu")["brand"]), fieldText(data["memory"]), requirements}})
}

func renderSwanMetrics(out io.Writer, items []platform.Record) error {
	return renderRecordTable(out, []recordColumn{{"指标名称", "tagName"}, {"最大值", "max"}, {"最小值", "min"}, {"平均值", "avg"}}, items,
		func(row platform.Record, key string) string {
			if key == "tagName" {
				return fieldText(row[key])
			}
			value, err := strconv.ParseFloat(string(row[key]), 64)
			if err != nil {
				return "-"
			}
			return fmt.Sprintf("%.4f", value)
		})
}

func renderSwanConfig(out io.Writer, data platform.Record) error {
	keys := make([]string, 0, len(data))
	for name := range data {
		keys = append(keys, name)
	}
	sort.Strings(keys)
	rows := [][]string{}
	for _, name := range keys {
		raw := data[name]
		if obj := data.Object(name); obj != nil {
			raw = obj["value"]
		}
		rows = append(rows, []string{name, fieldText(raw)})
	}
	return output.Table(out, []string{"配置项", "值"}, rows)
}

func swanInspect(cmd *cobra.Command, args []string, api *platform.API, format string) error {
	id, out := args[0], cmd.OutOrStdout()
	feature, err := swanFeatures(cmd, api, id, 1, 10)
	if err != nil {
		return err
	}
	features, rows, err := swanPage(feature, 1, 10)
	if err != nil {
		return err
	}
	environment, err := swanEnvironment(cmd, api, id)
	if err != nil {
		return err
	}
	metrics, err := swanMetrics(cmd, api, id, []string{"loss", "accuracy"})
	if err != nil {
		return err
	}
	config, err := swanConfig(cmd, api, id)
	if err != nil {
		return err
	}
	if format == "json" {
		return output.JSON(out, map[string]any{"features": features, "environment": environment, "metrics": metrics, "config": config})
	}
	fmt.Fprintln(out, "实验特性")
	if err := renderRecordTable(out, swanFeatureColumns, rows, catalogValue); err != nil {
		return err
	}
	fmt.Fprintln(out, "实验环境")
	if err := renderSwanEnvironment(out, environment); err != nil {
		return err
	}
	fmt.Fprintln(out, "指标信息")
	if err := renderSwanMetrics(out, metrics); err != nil {
		return err
	}
	fmt.Fprintln(out, "实验配置")
	return renderSwanConfig(out, config)
}
