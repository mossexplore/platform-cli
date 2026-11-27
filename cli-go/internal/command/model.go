package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const modelPrefix = "/ai/backend/mep/models/"

func newModel(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "model", Short: "模型查询与部署"}
	fixed := defaultFields("sfsId selectModel scene subScene", "modelStatus sourceEnv source approvalStrategy", "tags noticeTime")
	fixed["modelUsage"] = "cloud"
	list := catalogQuery{
		route: modelPrefix + "queryList", command: "list", summary: "查询当前业务的模型列表", paged: true, allowAllBusiness: true, allowExactName: true,
		nameHelp: "按模型名称筛选，配合 --exact 可精确查询", strings: []string{"name", "team-id"}, nullable: []string{"type", "owner"},
		fixed: fixed, assign: map[string]string{"name": "modelName", "team-id": "teamId", "type": "modelType", "owner": "owner"},
		body: withBusiness, items: "models", total: "count", preserve: true, optionalCode: true, empty: "暂无模型",
		columns: []recordColumn{{"模型 ID", "modelId"}, {"模型名称", "name"}, {"模型版本", "version"}, {"业务编码", "businessId"},
			{"类型", "type"}, {"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"归属者", "owner"}, {"团队", "teamId"}},
	}
	detail := &cobra.Command{Use: "detail MODEL_ID", Short: "查询模型详情", Args: positional(1)}
	outputFlag(detail)
	detail.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		cols := []recordColumn{{"算法类型", "algorithm"}, {"版本标签", "modelTag"}, {"模型大小", "pkgSize"}, {"存储方式", "storeType"},
			{"SFS标识", "sfsId"}, {"数据源", "source"}, {"数据源标签", "sourceId"}, {"更新方式", "contentMode"}, {"模型来源环境", "sourceEnv"}}
		payload, err := api.JSON(cmd.Context(), http.MethodPost, modelPrefix+"queryDetail", nil, map[string]string{"modelId": args[0]})
		if err != nil {
			return err
		}
		record, err := platform.Result(payload, "查询模型详情", false)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			r := agentRecord(record, columnKeys(cols)...)
			_ = r.Put("modelId", args[0])
			return agentResult(cmd, r)
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), payload)
		}
		for _, col := range cols {
			value := catalogValue(record, col.key)
			if col.key == "pkgSize" && value != "-" {
				value = readableBytes(value)
			}
			if _, err := fmt.Fprintf(cmd.OutOrStdout(), "%s：%s\n", col.title, value); err != nil {
				return err
			}
		}
		return nil
	})
	group.AddCommand(list.build(options, load), detail, newModelSource(options, load), newDeployModel(options, load))
	return group
}

func newModelSource(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "source MODEL_ID", Short: "查询模型溯源或关联训练任务信息", Args: positional(1)}
	train := cmd.Flags().Bool("train-task", false, "查询关联训练任务")
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		ctx, out := cmd.Context(), cmd.OutOrStdout()
		post := func(path, key, value string) (platform.Record, []byte, error) {
			payload, err := api.JSON(ctx, http.MethodPost, path, nil, map[string]string{key: value})
			if err != nil {
				return nil, nil, err
			}
			record, err := platform.Result(payload, "查询模型溯源", false)
			return record, payload, err
		}
		detail, _, err := post(modelPrefix+"queryDetail", "modelId", args[0])
		if err != nil {
			return err
		}
		sourceID := detail.Text("sourceId")
		if strings.TrimSpace(sourceID) == "" {
			return errors.New("模型详情缺少有效的 result.sourceId，无法查询模型溯源")
		}
		source, rawSource, err := post("/ai/backend/mtp/offlinemodel/version/queryDetail", "versionId", sourceID)
		if err != nil {
			return err
		}
		if agentMode(cmd) && !*train {
			return agentResult(cmd, agentRecord(source, strings.Fields("modelName modelVersion sourceId jobId sensitive businessId status createTime description source bucketName")...))
		}
		if format == "json" && !*train {
			return output.JSON(out, json.RawMessage(rawSource))
		}
		var task platform.Record
		job := source.Text("jobId")
		if *train || strings.TrimSpace(job) != "" {
			if strings.TrimSpace(job) == "" {
				return errors.New("模型溯源缺少有效的 result.jobId，无法查询训练任务")
			}
			linked, raw, err := post("/ai/backend/mtp/traintask/queryModelTaskDetail", "jobId", job)
			if err != nil {
				return err
			}
			task = linked.Object("jobHistoryDetail")
			if task == nil {
				return errors.New("训练任务响应缺少有效的 result.jobHistoryDetail")
			}
			if format == "json" {
				if agentMode(cmd) {
					return agentResult(cmd, agentRecord(task, strings.Fields("jobId taskId taskName businessId jobType image imageSpecificInfo maxHistoryNum")...))
				}
				return output.JSON(out, json.RawMessage(raw))
			}
		}
		taskFields := []recordColumn{{"任务名称", "taskName"}, {"业务编码", "businessId"}, {"业务场景", "scene"}, {"业务子场景", "subScene"},
			{"任务类型", "jobType"}, {"镜像", "image"}, {"资源规格", "imageSpecificInfo"}, {"工作节点数", "infraSize"}, {"执行时间", "createTime"},
			{"历史记录数目", "maxHistoryNum"}, {"超时时间(s)", "taskMaxTime"}}
		if *train {
			taskFields = []recordColumn{{"jobId", "jobId"}, {"任务Id", "taskId"}, {"任务名称", "taskName"}, {"业务编码", "businessId"},
				{"任务类型", "jobType"}, {"镜像", "image"}, {"资源规格", "imageSpecificInfo"}, {"历史记录数目", "maxHistoryNum"}}
			for _, col := range taskFields {
				fmt.Fprintf(out, "%s：%s\n", col.title, catalogValue(task, col.key))
			}
			return nil
		}
		fields := output.Fields{}
		for _, col := range []recordColumn{{"输出名称", "modelName"}, {"模型版本", "modelVersion"}, {"敏感", "sensitive"}, {"业务编码", "businessId"},
			{"状态", "status"}, {"创建时间", "createTime"}, {"描述", "description"}, {"来源", "source"}, {"存储桶", "bucketName"}} {
			value := catalogValue(source, col.key)
			if col.key == "sensitive" {
				value = "否"
				if string(source[col.key]) == "1" {
					value = "是"
				}
			}
			if col.key == "status" {
				value = "未发布"
				if string(source[col.key]) == "1" {
					value = "已发布"
				}
			}
			fields = append(fields, output.Field{Key: col.title, Value: value})
		}
		fmt.Fprintln(out, "输出版本基本信息")
		if err := fields.Table(out); err != nil {
			return err
		}
		if task != nil {
			fields = output.Fields{}
			for _, col := range taskFields {
				fields = append(fields, output.Field{Key: col.title, Value: catalogValue(task, col.key)})
			}
			fmt.Fprintln(out, "任务基本信息")
			return fields.Table(out)
		}
		return nil
	})
	return cmd
}
