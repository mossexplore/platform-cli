package command

import (
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newDataset(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{Use: "dataset", Short: "数据集管理"}
	const prefix = "/ai/backend/mtp/dataSet/"
	listCols := []recordColumn{
		{"数据集 ID", "dataSetId"}, {"数据集名称", "dataSetName"}, {"租户", "businessId"}, {"数据类型", "dataSetType"},
		{"修改者", "updateUser"}, {"大小", "fileSize"}, {"更新时间", "modifyTime"}, {"最近使用", "useTime"},
		{"区域", "region"}, {"存储桶", "bucketName"}, {"描述", "description"},
	}
	detailCols := []recordColumn{
		{"租户", "businessId"}, {"团队", "teamId"}, {"创建者", "createUser"}, {"创建时间", "createTime"},
		{"更新时间", "modifyTime"}, {"业务子场景", "subScene"}, {"数据集 ID", "bucketFileId"}, {"存储桶名称", "bucketName"},
		{"存储方式", "storageType"}, {"文件名称", "fileName"}, {"来源", "source"}, {"描述", "description"},
	}
	fixed := defaultFields("dataSetId teamId scene subScene dataSetType origin notUsedDays subDatazoneId tags isDeleted inputName inputId region commonTabTitle algorithmVersion",
		"expireStatus", "noticeTime updateNoticeTime")
	fixed["private"], fixed["sharing"] = false, false
	list := catalogQuery{
		route: prefix + "queryList", command: "list", summary: "分页查询当前业务下的数据集", paged: true, allowAllBusiness: true,
		nameHelp: "按数据集名称筛选，也可使用 --dataset-name（模糊查询；传入 '名称,名称' 可精确查询）", strings: []string{"name", "create-user", "update-user"}, nullable: []string{"bucket-name"},
		fixed: fixed, assign: map[string]string{"name": "dataSetName", "create-user": "createUser", "update-user": "updateUser", "bucket-name": "bucketName"},
		body: func(body map[string]any, cmd *cobra.Command, args []string, api *platform.API) (any, error) {
			if !cmd.Flags().Changed("name") && cmd.Flags().Changed("dataset-name") {
				body["dataSetName"], _ = cmd.Flags().GetString("dataset-name")
			}
			return withBusiness(body, cmd, args, api)
		}, items: "data", total: "totalSize", totalJSON: "total", columns: listCols, empty: "暂无数据集记录",
	}
	detail := catalogQuery{
		route: prefix + "queryDetail", command: "detail DATASET_ID", summary: "查询数据集详情", args: 1,
		body: func(_ map[string]any, _ *cobra.Command, args []string, api *platform.API) (any, error) {
			return map[string]string{"dataSetId": args[0], "businessId": api.BusinessID(), "teamId": ""}, nil
		},
		selectData: dataRecord, fields: detailCols,
	}
	listCommand := list.build(options, load)
	listCommand.Flags().String("dataset-name", "", "数据集名称条件")
	group.AddCommand(listCommand, detail.build(options, load), newDatasetFiles(options, load))
	return group
}
