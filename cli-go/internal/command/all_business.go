package command

import (
	"slices"

	"github.com/spf13/cobra"
)

const allBusinessFlag = "all-business"

func addAllBusinessFlag(cmd *cobra.Command) {
	cmd.Flags().BoolP(allBusinessFlag, "A", false, "在当前环境的全部租户中查询（需超级管理员或超级管理员只读权限）")
}

func allBusinessRequested(cmd *cobra.Command) bool {
	value, _ := cmd.Flags().GetBool(allBusinessFlag)
	return value
}

func setListBusiness(body map[string]any, cmd *cobra.Command, selected string) {
	body["businessId"] = selected
	if allBusinessRequested(cmd) {
		body["businessId"] = nil
	}
}

func allBusinessColumns(columns []recordColumn, enabled bool) []recordColumn {
	if !enabled {
		return columns
	}
	return append(slices.Clone(columns), recordColumn{title: "业务编码", key: "businessId"})
}
