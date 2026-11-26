package command

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/jupyter"
	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newStudio(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "webstudio", Short: "Web Studio 查询、启动、停止与 Jupyter 动态登录"}
	list := &cobra.Command{Use: "list", Short: "查询当前业务的实例列表", Args: positional(0)}
	page, size := pagination(list)
	name := list.Flags().String("name", "", "名称模糊匹配")
	status := list.Flags().String("status", "", "实例状态")
	relator := list.Flags().String("relator", "", "实例关联方")
	envID := list.Flags().String("env-id", "", "实例 ID")
	id := list.Flags().String("business-id", "", "须与当前业务一致")
	format := list.Flags().StringP("output", "o", "table", "输出格式为 table 或 json")
	addAllBusinessFlag(list)
	list.Args = func(cmd *cobra.Command, args []string) error {
		if cmd.Flags().Changed(allBusinessFlag) && cmd.Flags().Changed("business-id") {
			return usageError{errors.New("--all-business 与 --business-id 不能同时使用")}
		}
		return positional(0)(cmd, args)
	}
	list.RunE = authorized(options, load, func(cmd *cobra.Command, _ []string, api *platform.API, _ string) error {
		if *page < 1 || *size < 1 {
			return usageError{errors.New("page 和 page-size 必须为正整数")}
		}
		if cmd.Flags().Changed("business-id") && *id != api.BusinessID() {
			return usageError{errors.New("business-id 须与当前选择一致，请先运行 ml business use")}
		}
		body := jupyter.StudioListBody(api.BusinessID(), *name, *status, *relator, *envID, *page, *size)
		setListBusiness(body, cmd, api.BusinessID())
		payload, err := api.JSON(cmd.Context(), http.MethodPost, jupyter.StudioPrefix+"queryEnvList", nil, body)
		if err != nil {
			return err
		}
		result, err := platform.Result(payload, "查询 Web Studio", false)
		if err != nil {
			return err
		}
		var items []platform.Record
		var count *int
		if json.Unmarshal(result["envs"], &items) != nil || items == nil || json.Unmarshal(result["count"], &count) != nil || count == nil || *count < 0 {
			return errors.New("Web Studio 列表结构无效")
		}
		for _, row := range items {
			if row == nil {
				return errors.New("Web Studio 列表包含无效记录")
			}
		}

		cols := []recordColumn{{"envId", "envId"}, {"名称", "labelName"}, {"集群类型", "clusterType"}, {"资源规格", "imageSpecific"},
			{"状态", "status"}, {"创建者", "operator"}, {"修改者", "modifier"}, {"启动时间", "accessTime"}}
		if agentMode(cmd) {
			columns := allBusinessColumns(cols, allBusinessRequested(cmd))
			return agentResult(cmd, output.AgentList(agentRows(items, columns), agentFields(columns, nil), "paged", *page, *size, count))
		}
		if strings.EqualFold(*format, "json") {
			return output.JSON(cmd.OutOrStdout(), payload)
		}
		err = renderRecordTable(cmd.OutOrStdout(), allBusinessColumns(cols, allBusinessRequested(cmd)), items, func(item platform.Record, key string) string {
			if key == "accessTime" {
				return dateText(item[key])
			}
			return fieldText(item[key])
		})
		if err != nil {
			return err
		}
		_, err = fmt.Fprintf(cmd.OutOrStdout(), "第 %d 页 · 本页 %d 条 · 总计 %d 条\n", *page, len(items), *count)
		return err
	})
	login := &cobra.Command{Use: "login ENV_ID", Short: "重新建立并验证 Jupyter 连接，保存默认实例", Args: positional(1)}
	login.Flags().Bool("refresh", false, "强制重新获取连接凭据和会话")
	login.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		if err := jupyter.StudioLogin(cmd.Context(), api, paths, cfg, args[0]); err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"envId": args[0], "status": "loggedIn"})
		}
		_, err = fmt.Fprintln(cmd.ErrOrStderr(), "[成功] Web Studio 登录成功，默认实例："+args[0])
		return err
	})
	show := &cobra.Command{Use: "show", Short: "显示当前环境、账号与业务绑定的选择", Args: positional(0)}
	show.RunE = authorized(options, load, func(cmd *cobra.Command, _ []string, api *platform.API, _ string) error {
		paths, cfg, err := load()
		if err != nil {
			return err
		}
		saved, err := jupyter.StudioStatus(paths, cfg, api)
		if err != nil {
			return err
		}
		return output.JSON(cmd.OutOrStdout(), saved)
	})
	group.AddCommand(list, login, show)
	for action, chinese := range map[string]string{"start": "启动", "stop": "停止"} {
		cmd := &cobra.Command{Use: action + " ENV_ID", Short: chinese + "指定 Web Studio", Args: positional(1)}
		cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
			body := map[string]string{"businessId": api.BusinessID(), "envId": args[0]}
			if action == "start" {
				api.SetMinimumTimeout(60 * time.Second)
				body["operator"] = api.Username()
			}
			payload, err := api.Mutation(cmd.Context(), http.MethodPost, jupyter.StudioPrefix+action, nil, body)
			if err != nil {
				return err
			}
			if _, err := platform.Result(payload, chinese+" Web Studio", false); err != nil {
				return err
			}
			if agentMode(cmd) {
				return agentResult(cmd, map[string]string{"envId": args[0], "action": action, "status": "accepted"})
			}
			_, err = fmt.Fprintf(cmd.ErrOrStderr(), "[成功] Web Studio %s成功：%s\n", chinese, args[0])
			return err
		})
		group.AddCommand(cmd)
	}
	return group
}
