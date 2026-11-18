package command

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"strconv"

	"github.com/mossexplore/platform-cli/cli-go/internal/output"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newFeatureSet(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "featureset", Short: "特征集"}
	const prefix = "/ai/backend/dpp/proxy/featureStore/featureset/"
	for _, set := range []struct{ name, label string }{{"wide", "宽表特征集查询"}, {"model", "模型特征集查询"}} {
		child := &cobra.Command{Use: set.name, Short: set.label}
		fixed := defaultFields("teamId scene subscene operator modifier tagIdList", "", "")
		fixed["setType"] = set.name
		list := catalogQuery{
			route: prefix + "names", command: "list", summary: "分页查询当前业务下的特征集", paged: true, wiseref: true,
			strings: []string{"name"}, fixed: fixed, assign: map[string]string{"name": "setName"}, body: withBusiness,
			items: "featureSetInfoList", total: "totalCount", totalJSON: "count", empty: "暂无特征集",
			columns: []recordColumn{{"特征集 ID", "setId"}, {"特征集名称", "setName"}, {"特征集类型", "setType"}, {"场景", "scene"},
				{"创建者", "creator"}, {"创建时间", "createTime"}, {"修改者", "modifier"}, {"修改时间", "updateTime"}},
		}
		config := &cobra.Command{Use: "config SET_ID", Short: "查询特征集配置，固定输出解析后的 JSON 对象",
			Args: positional(1), Annotations: map[string]string{"platform": "wiserec"}}
		config.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
			body := map[string]string{"businessId": api.BusinessID(), "setId": args[0]}
			raw, err := api.JSON(cmd.Context(), http.MethodPost, prefix+"config", nil, body)
			if err != nil {
				return err
			}
			result, err := platform.Result(raw, "查询特征集配置", true)
			if err != nil {
				return err
			}
			config := bytes.TrimSpace([]byte(result.Text("featureJson")))
			if len(config) == 0 || config[0] != '{' || !json.Valid(config) {
				return errors.New("featureJson 必须是有效的 JSON 对象")
			}
			return output.JSON(cmd.OutOrStdout(), json.RawMessage(config))
		})
		child.AddCommand(list.build(options, load), config, newFeatureExport(options, load))
		group.AddCommand(child)
	}
	return group
}

func newFeatureExport(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "export SET_ID", Short: "导出特征集中的特征为 CSV 文件", Args: positional(1),
		Annotations: map[string]string{"platform": "wiserec", "text_output": "true"}}
	lang := cmd.Flags().String("lang", "zh_cn", "zh_cn 或 en_us")
	file := cmd.Flags().String("file", "", "本地 CSV 保存路径")
	cmd.Flags().StringP("output", "o", "text", "输出格式为 text 或 json")
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		if *lang != "zh_cn" && *lang != "en_us" {
			return usageError{errors.New("lang 仅支持 zh_cn 或 en_us")}
		}
		if err := requireParent(*file); err != nil {
			return err
		}
		target, size, err := api.ExportFeatures(cmd.Context(), args[0], *lang, *file)
		if err != nil {
			return err
		}
		if format == "json" {
			return output.JSON(cmd.OutOrStdout(), map[string]any{"setId": args[0], "lang": *lang, "file": target, "bytes": size})
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 导出成功")
		_, err = fmt.Fprintf(cmd.OutOrStdout(), "文件：%s\n大小：%s\n", target, readableBytes(strconv.FormatInt(size, 10)))
		return err
	})
	return cmd
}
