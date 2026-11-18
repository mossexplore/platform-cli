package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"net/http"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const qualityPrefix = "/ai/backend/dpp/proxy/featurestore/quality-visualization/features"

var qualityTypes = map[string]string{"CONTINUOUS": "连续", "DISCRETE": "离散", "ORDINAL": "有序", "CATEGORICAL": "分类", "SEQUENCE": "序列", "LONG_SEQUENCE": "长序列", "VECTOR": "向量"}

func newQuality(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "quality", Short: "质量监控"}
	feature := &cobra.Command{Use: "feature", Short: "特征质量查询"}
	wide := &cobra.Command{Use: "wide-featureset", Short: "宽表特征集质量查询"}
	list := catalogQuery{route: qualityPrefix, command: "list", summary: "分页查询特征质量记录", paged: true, maxPage: 100, wiseref: true,
		strings: []string{"name", "table-name", "feature-value-type", "indicator-type"},
		assign:  map[string]string{"name": "featureName", "table-name": "tableName"},
		body: func(body map[string]any, cmd *cobra.Command, _ []string, _ *platform.API) (any, error) {
			for flag, key := range map[string]string{"feature-value-type": "featureValueType", "indicator-type": "indicatorType"} {
				if !cmd.Flags().Changed(flag) {
					continue
				}
				value, _ := cmd.Flags().GetString(flag)
				value = strings.ToUpper(strings.TrimSpace(value))
				for code, label := range qualityTypes {
					if value == label {
						value = code
						break
					}
				}
				if _, ok := qualityTypes[value]; !ok {
					return nil, usageError{fmt.Errorf("%s 不支持指定的类型", flag)}
				}
				body[key] = value
			}
			return body, nil
		}, items: "featureList", total: "totalCount", totalJSON: "count", paginationFromServer: true,
		empty: "暂无特征质量记录", value: qualityValue,
		columns: []recordColumn{{"特征id", "featureId"}, {"特征名", "featureName"}, {"特征表名", "featTableName"}, {"特征类型", "featureType"},
			{"特征值类型", "featureValueType"}, {"指标类型", "indicatorType"}, {"创建人", "creator"}, {"特征产出时间", "latestCycleTime"},
			{"时效性", "freshnessValue"}, {"空值率", "nullValueRate"}},
	}
	wideList := catalogQuery{route: qualityPrefix + "/wide-feature-sets", command: "list", summary: "分页查询宽表特征集质量记录", paged: true, maxPage: 100, wiseref: true,
		strings: []string{"name"}, assign: map[string]string{"name": "setName"},
		items: "featureSetList", total: "totalCount", totalJSON: "count", paginationFromServer: true, empty: "暂无宽表特征集质量记录",
		columns: []recordColumn{{"特征集id", "setId"}, {"特征集名称", "setName"}, {"版本", "version"}, {"特征装配输出表名", "outTableName"},
			{"场景", "scene"}, {"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"创建人", "creator"}, {"更新人", "modifier"}},
	}
	feature.AddCommand(list.build(options, load))
	wide.AddCommand(wideList.build(options, load))
	wide.AddCommand(newAssembly(options, load, "feature-assemble", "特征装配"), newAssembly(options, load, "label-assemble", "标签装配"))
	group.AddCommand(feature, wide)
	return group
}

func newAssembly(options Options, load loadConfig, kind, label string) *cobra.Command {
	group := &cobra.Command{Use: kind, Short: label + "质量信息"}
	child := &cobra.Command{Use: "feature", Short: label + "特征列表"}
	list := &cobra.Command{Use: "list", Short: "查询" + label + "样本定义列表", Args: positional(0), Annotations: map[string]string{"platform": "wiserec"}}
	setID := list.Flags().String("set-id", "", "宽表特征集 ID")
	_ = list.MarkFlagRequired("set-id")
	outputFlag(list)
	list.RunE = authorized(options, load, func(cmd *cobra.Command, _ []string, api *platform.API, format string) error {
		set := strings.TrimSpace(*setID)
		if set == "" {
			return usageError{errors.New("set-id 不能为空")}
		}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, qualityPrefix+"/feature-sets/query", nil,
			map[string]string{"setId": set, "type": strings.ReplaceAll(kind, "-", "_")})
		if err != nil {
			return err
		}
		result, err := platform.Result(payload, "查询装配样本定义", false)
		if err != nil {
			return err
		}
		var items []platform.Record
		if json.Unmarshal(result["sampleDefinitionList"], &items) != nil || items == nil {
			return errors.New("响应缺少有效的 sampleDefinitionList")
		}
		for _, item := range items {
			if item == nil {
				return errors.New("sampleDefinitionList 包含无效条目")
			}
		}
		if format == "json" {
			data := map[string]any{"items": items, "count": len(items)}
			if id := result["featureSetId"]; len(id) != 0 {
				data["featureSetId"] = id
			}
			return output.JSON(cmd.OutOrStdout(), data)
		}
		if id := result.Text("featureSetId"); id != "" && id != set {
			fmt.Fprintf(cmd.ErrOrStderr(), "[提示] 接口返回 featureSetId=%s，与请求 setId=%s 不同\n", id, set)
		}
		if err := renderRecordTable(cmd.OutOrStdout(), []recordColumn{
			{"样本定义ID", "definitionId"}, {"样本定义名称", "definitionName"}, {"装配输出表名", "outputTable"},
			{"装配最新周期", "latestCycle"}, {"正负样本比例", "latestRatio"},
		}, items, assemblyValue); err != nil {
			return err
		}
		if len(items) == 0 {
			fmt.Fprintln(cmd.OutOrStdout(), "暂无"+label+"样本定义")
		}
		_, err = fmt.Fprintf(cmd.OutOrStdout(), "本次返回 %d 条\n", len(items))
		return err
	})
	features := catalogQuery{route: qualityPrefix + "/feature-sets/query/feature-indicators", command: "list", summary: "分页查询" + label + "特征", paged: true, maxPage: 100, wiseref: true,
		strings: []string{"set-id", "definition-id"}, assign: map[string]string{"set-id": "setId", "definition-id": "definitionId"},
		body: func(body map[string]any, _ *cobra.Command, _ []string, _ *platform.API) (any, error) {
			for _, key := range []string{"setId", "definitionId"} {
				value := strings.TrimSpace(body[key].(string))
				if value == "" {
					return nil, usageError{fmt.Errorf("%s 不能为空", key)}
				}
				body[key] = value
			}
			body["type"] = strings.ReplaceAll(kind, "-", "_")
			return body, nil
		}, items: "featureList", total: "totalCount", totalJSON: "count", paginationFromServer: true, empty: "暂无特征记录", value: assemblyValue,
		columns: []recordColumn{{"特征ID", "featureId"}, {"特征名", "featureName"}, {"特征类型", "featureType"},
			{"特征值类型", "featureValueType"}, {label + "最新周期", "latestCycleTime"}, {"空值率", "nullValueRate"}},
	}.build(options, load)
	_ = features.MarkFlagRequired("set-id")
	_ = features.MarkFlagRequired("definition-id")
	child.AddCommand(features)
	group.AddCommand(list, child)
	return group
}

func qualityValue(record platform.Record, field string) string {
	text := catalogValue(record, field)
	switch field {
	case "featureValueType", "indicatorType":
		return labelOrID(qualityTypes[text], text)
	case "nullValueRate":
		if value, err := strconv.ParseFloat(text, 64); err == nil && !math.IsInf(value, 0) && !math.IsNaN(value) {
			return strconv.FormatFloat(value*100, 'f', -1, 64) + "%"
		}
	case "latestCycleTime":
		return dateText(record[field])
	}
	return text
}

func assemblyValue(record platform.Record, field string) string {
	if field == "latestRatio" || field == "nullValueRate" {
		text := fieldText(record[field])
		if value, err := strconv.ParseFloat(text, 64); err == nil && !math.IsInf(value, 0) && !math.IsNaN(value) {
			return strconv.FormatFloat(math.Round(value*100), 'f', 0, 64) + "%"
		}
	}
	if field == "latestCycleTime" {
		return dateText(record[field])
	}
	return fieldText(record[field])
}
