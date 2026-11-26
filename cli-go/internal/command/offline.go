package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

const offlinePrefix = "/ai/backend/experiment"

func newOffline(options Options, load loadConfig) *cobra.Command {
	root := &cobra.Command{Use: "offline", Short: "离线业务管理"}
	experiment := &cobra.Command{Use: "experiment", Short: "离线实验管理"}
	trial := &cobra.Command{Use: "trial", Short: "离线实验 trial 管理"}
	trial.AddCommand(newOfflineList(options, load, true))
	experiment.AddCommand(newOfflineList(options, load, false), newOfflineClone(options, load), trial)
	root.AddCommand(experiment)
	return root
}

func newOfflineList(options Options, load loadConfig, trial bool) *cobra.Command {
	use, short, count, route := "list", "分页查询离线实验", 0, offlinePrefix+"/project/list"
	type filter struct{ field, description string }
	params := map[string]filter{
		"name":         {"projectName", "按离线实验名称筛选，也可使用 --project-name"},
		"project-name": {"projectName", "按离线实验名称筛选，与 --name 同时使用时优先采用 --name"},
		"description":  {"description", "按离线实验描述筛选"},
		"create-user":  {"createUser", "按创建者账号筛选"},
		"update-user":  {"updateUser", "按修改者账号筛选"},
		"team-id":      {"teamId", "按团队 ID 筛选"},
	}
	cols := []recordColumn{{"projectId", "projectId"}, {"实验名称", "projectName"}, {"描述", "description"}, {"创建者", "createUser"},
		{"修改者", "updateUser"}, {"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"运行配置模板", "configName"}}
	if trial {
		use, short, count, route = "list PROJECT_ID", "分页查询某个离线实验下的 trial", 1, offlinePrefix
		params = map[string]filter{
			"name":      {"experimentNameRef", "按 trial 名称筛选"},
			"type":      {"experimentType", "按 trial 类型筛选，例如 batch 或 stream"},
			"creator":   {"creator", "按创建者账号筛选"},
			"updater":   {"updater", "按修改者账号筛选"},
			"ai-module": {"aimodule", "按 AI 模块筛选"},
		}
		cols = []recordColumn{{"trial名称", "experimentName"}, {"类型", "experimentType"}, {"创建者", "creator"}, {"修改者", "updater"},
			{"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"调度状态", "cronIntervalStartFlag"}, {"描述", "description"}}
	}
	cmd := &cobra.Command{Use: use, Short: short, Args: positional(count), Annotations: map[string]string{"platform": "wiserec"}}
	page, pageSize := pagination(cmd)
	outputFlag(cmd)
	if !trial {
		addAllBusinessFlag(cmd)
	}
	for flag, filter := range params {
		cmd.Flags().String(flag, "", filter.description)
	}
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if *page < 1 || *pageSize < 1 {
			return usageError{errors.New("page 和 page-size 必须为正整数")}
		}
		query := url.Values{"businessId": {api.BusinessID()}, "pageIndex": {strconv.Itoa(*page)}, "pageSize": {strconv.Itoa(*pageSize)}}
		allBusiness := allBusinessRequested(cmd)
		if allBusiness {
			query.Set("businessId", "ALL")
		}
		columns := allBusinessColumns(cols, allBusiness)
		if trial {
			query.Set("projectId", args[0])
		}
		for flag, filter := range params {
			if flag == "project-name" && cmd.Flags().Changed("name") {
				continue
			}
			if cmd.Flags().Changed(flag) {
				value, _ := cmd.Flags().GetString(flag)
				query.Set(filter.field, value)
			}
		}
		raw, err := api.JSON(cmd.Context(), http.MethodGet, route, query, nil)
		if err != nil {
			return err
		}
		result, err := platform.Result(raw, short, false)
		if err != nil {
			return err
		}
		items, err := swanItems(result["data"])
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			v := output.AgentList(agentRows(items, columns, "experimentId", "projectId"), "paged", *page, *pageSize, nil)
			if raw := result["total"]; len(raw) > 0 && string(raw) != "null" {
				v["total"] = raw
			}
			return agentResult(cmd, v)
		}
		if format == "json" {
			filtered := make([]platform.Record, 0, len(items))
			for _, item := range items {
				record := platform.Record{}
				for _, column := range columns {
					value, ok := item[column.key]
					if !ok {
						value = json.RawMessage(`""`)
					}
					record[column.key] = value
				}
				filtered = append(filtered, record)
			}
			count, total := any(len(items)), any(len(items))
			if len(result["count"]) > 0 {
				count = result["count"]
			}
			if len(result["total"]) > 0 {
				total = result["total"]
			}
			return output.JSON(cmd.OutOrStdout(), map[string]any{"pageIndex": *page, "pageSize": *pageSize, "count": count, "total": total, "items": filtered})
		}
		return renderRecordTable(cmd.OutOrStdout(), columns, items, func(row platform.Record, key string) string {
			switch key {
			case "experimentType":
				if row.Text(key) == "batch" {
					return "批式"
				}
				return "流式"
			case "cronIntervalStartFlag":
				switch string(row[key]) {
				case "true":
					return "调度开启"
				case "false":
					return "调度停止"
				}
			}
			return catalogValue(row, key)
		})
	})
	return cmd
}

func newOfflineClone(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "clone PROJECT_ID", Short: "查询源实验详情并同步克隆，仅修改实验名称", Args: positional(1),
		Annotations: map[string]string{"platform": "wiserec"}}
	name := cmd.Flags().String("name", "", "克隆后的实验名称")
	_ = cmd.MarkFlagRequired("name")
	dry := cmd.Flags().Bool("dry-run", false, "仅展示请求内容")
	cmd.Flags().BoolP("yes", "y", false, "跳过克隆确认")
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		selected := strings.TrimSpace(*name)
		if selected == "" {
			return usageError{errors.New("克隆后的实验名称不能为空")}
		}
		ctx := cmd.Context()
		raw, err := api.JSON(ctx, http.MethodGet, offlinePrefix+"/project/"+url.PathEscape(args[0]), url.Values{"businessId": {api.BusinessID()}}, nil)
		if err != nil {
			return err
		}
		result, err := platform.Result(raw, "查询离线实验详情", false)
		if err != nil {
			return err
		}
		detail := result.Object("data")
		if detail.Text("projectId") != args[0] || detail.Text("businessId") != api.BusinessID() {
			return errors.New("源实验 ID 或当前业务与详情不一致")
		}
		data := map[string]any{"projectId": "", "projectName": selected, "businessId": api.BusinessID(), "createUser": api.Username(), "updateUser": api.Username()}
		for _, name := range strings.Fields("description region subDomain serviceChannel teamId clusterName configId configName") {
			value := detail[name]
			if len(value) == 0 || string(value) == "null" {
				value = json.RawMessage(`""`)
			}
			data[name] = value
		}
		id := localstate.NewID()
		body := map[string]any{"version": "1.0", "meta": map[string]string{"uuid": id}, "data": data}
		if *dry {
			return showOfflineResult(cmd, format, map[string]any{"dryRun": true, "request": body})
		}
		if yes, _ := cmd.Flags().GetBool("yes"); !yes {
			fmt.Fprintf(cmd.ErrOrStderr(), "源实验名称：%s\n新实验名称：%s\n运行配置模板：%s\nbusinessId：%s\n团队 ID：%s\n",
				labelOrID(detail.Text("projectName"), "-"), selected, labelOrID(detail.Text("configName"), "-"),
				api.BusinessID(), labelOrID(detail.Text("teamId"), "-"))
		}
		approved, err := approve(cmd, "确认克隆？")
		if !approved || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消克隆")
			return err
		}
		raw, err = api.Mutation(ctx, http.MethodPost, offlinePrefix+"/project", nil, body)
		if err != nil {
			return err
		}
		result, err = platform.Result(raw, "克隆离线实验", false)
		if err != nil {
			return err
		}
		return showOfflineResult(cmd, format, map[string]any{"sourceProjectId": args[0], "projectName": selected,
			"projectId": labelOrID(result.Object("data").Text("projectId"), "-"), "uuid": id, "message": labelOrID(result.Text("des"), "ok")})
	})
	return cmd
}

func showOfflineResult(cmd *cobra.Command, format string, value any) error {
	if format == "json" {
		return output.JSON(cmd.OutOrStdout(), value)
	}
	raw, err := json.Marshal(value)
	if err != nil {
		return err
	}
	return output.ResultTable(cmd.OutOrStdout(), raw)
}
