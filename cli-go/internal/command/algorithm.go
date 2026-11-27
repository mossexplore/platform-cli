package command

import (
	"errors"
	"fmt"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newAlgorithm(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "algorithm", Short: "算法仓查询、下载与克隆"}
	const prefix = "/ai/backend/modelDev/algorithmWarehouse/"
	fixed := defaultFields("updater creator visualTag algorithmVersion region algorithmPurpose enableFlag teamId", "beginTime endTime", "tagsList noticeTime")
	list := catalogQuery{route: prefix + "list", command: "list", summary: "分页查询当前业务的算法仓", paged: true, wiseref: true, allowAllBusiness: true, allowExactName: true, appendBusinessColumn: true,
		nameHelp: "按算法仓名称筛选，也可使用 --algorithm-name；配合 --exact 可精确查询", strings: []string{"name", "bucket-name"}, fixed: fixed, assign: map[string]string{"name": "algorithmName", "bucket-name": "bucketName"},
		body: func(body map[string]any, cmd *cobra.Command, _ []string, api *platform.API) (any, error) {
			if cmd.Flags().Changed("algorithm-name") && !cmd.Flags().Changed("name") {
				body["algorithmName"], _ = cmd.Flags().GetString("algorithm-name")
			}
			setListBusiness(body, cmd, api.BusinessID())
			return map[string]any{"data": body, "meta": map[string]string{"uuid": localstate.NewID()}, "version": "1.0"}, nil
		}, selectData: dataRecord, items: "list", total: "total", totalJSON: "total", empty: "暂无算法仓记录", value: algorithmValue,
		columns: []recordColumn{{"算法仓 ID", "id"}, {"算法仓名称", "name"}, {"版本", "version"}, {"区域", "algorithmRegion"}, {"修改者", "modifier"},
			{"修改时间", "modifyTime"}, {"大小", "fileSize"}, {"描述", "description"}, {"禁用", "enableFlag"}, {"归档状态", "archiveToNspStatus"}},
	}.build(options, load)
	list.Flags().String("algorithm-name", "", "算法仓名称条件")
	download := &cobra.Command{Use: "download ALGORITHM_ID", Short: "下载算法仓文件", Args: positional(1),
		Annotations: map[string]string{"platform": "wiserec"}}
	file := download.Flags().String("file", "", "本地保存路径")
	download.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		ctx := cmd.Context()
		if err := requireParent(*file); err != nil {
			return err
		}
		raw, err := api.JSON(ctx, http.MethodGet, "/ai/backend/mtp/algorithm/downloadurl",
			url.Values{"businessId": {api.BusinessID()}, "algorithmId": {args[0]}}, nil)
		if err != nil {
			return err
		}
		result, err := platform.Result(raw, "获取算法仓下载地址", false)
		if err != nil {
			return err
		}
		target, size, err := api.SignedDownload(ctx, result.Text("url"), *file, "algorithm", true)
		if err != nil {
			return err
		}
		if agentMode(cmd) {
			return agentResult(cmd, map[string]any{"file": target, "bytes": size})
		}
		_, err = fmt.Fprintf(cmd.ErrOrStderr(), "[成功] 算法仓已下载：%s（%d 字节）\n", target, size)
		return err
	})
	clone := &cobra.Command{Use: "clone SOURCE_ID", Short: "按指定名称和版本克隆算法仓", Args: positional(1),
		Annotations: map[string]string{"platform": "wiserec"}}
	name := clone.Flags().String("name", "", "新算法仓名称")
	version := clone.Flags().String("version", "", "新算法仓版本")
	clone.Flags().BoolP("yes", "y", false, "跳过克隆确认")
	_ = clone.MarkFlagRequired("name")
	_ = clone.MarkFlagRequired("version")
	clone.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, _ string) error {
		if strings.TrimSpace(*name) == "" || strings.TrimSpace(*version) == "" {
			return usageError{errors.New("名称和版本均不能为空")}
		}
		fmt.Fprintf(cmd.ErrOrStderr(), "源算法仓：%s；新名称：%s；新版本：%s\n", args[0], *name, *version)
		ok, err := approve(cmd, "确认克隆算法仓？")
		if !ok || err != nil {
			if err == nil && agentMode(cmd) {
				return agentResult(cmd, map[string]string{"status": "cancelled"})
			}
			fmt.Fprintln(cmd.ErrOrStderr(), "已取消克隆")
			return err
		}
		body := map[string]string{"srcId": args[0], "businessId": api.BusinessID(), "operator": api.Username(), "tarName": *name, "tarVersion": *version}
		raw, err := api.Mutation(cmd.Context(), http.MethodPost, prefix+"copy", nil, map[string]any{"data": body})
		if err != nil {
			return err
		}
		result, err := platform.Result(raw, "克隆算法仓", false)
		if err != nil {
			return err
		}
		fmt.Fprintln(cmd.ErrOrStderr(), "[成功] 克隆算法仓成功")
		if agentMode(cmd) {
			return agentResult(cmd, map[string]string{"id": result.Object("data").Text("id"), "sourceId": args[0]})
		}
		if id := result.Object("data").Text("id"); id != "" {
			fmt.Fprintln(cmd.OutOrStdout(), "新算法仓 ID："+id)
		}
		return nil
	})
	group.AddCommand(list, download, clone)
	return group
}

func requireParent(file string) error {
	if file != "" {
		info, err := os.Stat(filepath.Dir(file))
		if err != nil || !info.IsDir() {
			return errors.New("目标目录不存在")
		}
	}
	return nil
}

func algorithmValue(row platform.Record, field string) string {
	switch field {
	case "enableFlag":
		switch string(row[field]) {
		case "true":
			return "否"
		case "false":
			return "是"
		}
	case "archiveToNspStatus":
		switch string(row[field]) {
		case "0":
			return "未归档"
		case "1":
			return "归档成功"
		}
	}
	return catalogValue(row, field)
}
