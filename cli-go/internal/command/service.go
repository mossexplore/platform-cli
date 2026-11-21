package command

import (
	"errors"
	"fmt"
	"math"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
	"github.com/spf13/cobra"
)

func newService(options Options, load loadConfig) *cobra.Command {
	group := &cobra.Command{
		Use: "service", Short: "服务查询、模拟调用与主机诊断",
		RunE: func(cmd *cobra.Command, args []string) error {
			if len(args) > 0 {
				return usageError{fmt.Errorf("unknown command %q for %q", args[0], cmd.CommandPath())}
			}
			return cmd.Help()
		},
	}
	host := &cobra.Command{Use: "host", Short: "服务主机查询、测试与诊断"}
	deploy := &cobra.Command{Use: "deployment", Short: "服务部署视图查询"}
	const prefix = "/ai/backend/mep/services/"
	fixed := defaultFields("teamId", "inferenceType env selectService selectModelName infraType owner status isAccess noAccessDays isLowLoad lowLoadDays clusterId isCluster dailTestTaskStatus scaleFlag", "tags noticeTime")
	list := catalogQuery{route: prefix + "queryList", command: "list", summary: "分页查询当前业务的服务", paged: true, allowAllBusiness: true, appendBusinessColumn: true,
		nameHelp: "按服务名称筛选，也可使用 --service-name", nullable: []string{"name", "model-name", "model-version"}, fixed: fixed,
		assign: map[string]string{"name": "serviceName", "model-name": "modelName", "model-version": "modelVersion"},
		body: func(body map[string]any, cmd *cobra.Command, _ []string, api *platform.API) (any, error) {
			if cmd.Flags().Changed("service-name") {
				alias, _ := cmd.Flags().GetString("service-name")
				if !cmd.Flags().Changed("name") {
					body["serviceName"] = alias
				}
			}
			for _, key := range []string{"serviceName", "modelName", "modelVersion"} {
				if value, ok := body[key].(string); ok {
					value = strings.TrimSpace(value)
					if value == "" {
						return nil, usageError{errors.New("筛选条件不能为空白")}
					}
					body[key] = value
				}
			}
			body["clusterBusinessId"] = api.BusinessID()
			return withBusiness(body, cmd, nil, api)
		}, items: "services", total: "count", totalJSON: "total", empty: "暂无服务记录", value: serviceValue,
		columns: []recordColumn{{"服务 ID", "serviceId"}, {"服务名称", "serviceName"}, {"服务版本", "serviceVersion"},
			{"环境", "env"}, {"状态", "status"}, {"服务实例", "instance"}, {"模型名称", "modelName"}, {"归属者", "owner"}},
	}.build(options, load)
	list.Flags().String("service-name", "", "--name 的别名，二者同传以 --name 为准")
	list.Flags().Lookup(allBusinessFlag).Usage = "查询当前环境的全部租户\n需超级管理员或超级管理员只读权限"
	hostList := catalogQuery{route: prefix + "rtcContainer/queryServiceHostList", command: "list SERVICE_ID", summary: "查询指定服务的主机视图", args: 1,
		strings: []string{"pod-ip"}, assign: map[string]string{"pod-ip": "hostIp"},
		fixed: map[string]any{"status": "", "clusterName": "", "preheatStatus": "ALL", "quotaType": nil, "pageIndex": 1, "pageSize": 10},
		body: func(body map[string]any, cmd *cobra.Command, args []string, api *platform.API) (any, error) {
			ip := strings.TrimSpace(body["hostIp"].(string))
			if ip == "" && cmd.Flags().Changed("pod-ip") {
				return nil, usageError{errors.New("Pod IP 不能为空")}
			}
			body["serviceId"], body["businessId"], body["hostIp"] = args[0], api.BusinessID(), ip
			return body, nil
		}, items: "data", total: "count", totalJSON: "total", empty: "暂无服务主机记录", value: serviceValue,
		columns: []recordColumn{{"集群", "clusterName"}, {"pod名称", "nodeName"}, {"podIP", "nodeHost"},
			{"主机IP", "hostIp"}, {"规格", "spec"}, {"状态", "health_status"}, {"最大并发数", "execute_limit"}, {"超时时间(ms)", "service_timeout"},
			{"CPU", "cpuUsage"}, {"GPU", "gpuUsage"}, {"内存", "memUsage"}, {"NPU", "npuUsage"}, {"创建时间", "create_time"}, {"更新时间", "update_time"}},
	}
	deployList := catalogQuery{route: prefix + "rtcContainer/queryDetail", command: "list SERVICE_ID", summary: "查询指定服务的部署视图", args: 1,
		body: func(_ map[string]any, _ *cobra.Command, args []string, api *platform.API) (any, error) {
			return map[string]any{"pageIndex": 1, "pageSize": 10, "serviceId": args[0], "businessId": api.BusinessID()}, nil
		}, items: "data", total: "count", totalJSON: "total", optionalTotal: true, empty: "暂无服务部署记录", value: serviceValue,
		columns: []recordColumn{{"blockId", "blockId"}, {"区域", "region"}, {"站点", "domain"}, {"集群名称", "clusterName"},
			{"镜像", "image"}, {"规格", "resourceSpec"}, {"推理框架", "framework"}, {"yaml模板", "yamlId"}, {"创建时间", "createTime"}, {"更新时间", "updateTime"}},
	}
	host.AddCommand(hostList.build(options, load), newServiceMock(options, load, true), newServiceLogs(options, load), newServiceHostPodEvent(options, load), newServiceHostLogStdout(options, load))
	deploy.AddCommand(deployList.build(options, load))
	group.AddCommand(list, host, deploy, newServiceMock(options, load, false))
	return group
}

func serviceValue(record platform.Record, key string) string {
	switch key {
	case "image":
		return combinedFields(record, " ", "imageName", "imageVersion")
	case "framework":
		return combinedFields(record, "@", "wiseEyeName", "wiseEyeVersion")
	case "resourceSpec":
		spec := ""
		for _, part := range []struct{ key, unit string }{{"cpuLimit", "C"}, {"memoryLimit", "G"}, {"gpuLimit", "GPU"}, {"npuLimit", "NPU"}} {
			value := fieldText(record[part.key])
			if number, err := strconv.ParseFloat(value, 64); err == nil && number == 0 {
				continue
			}
			if value != "-" {
				spec += value + part.unit
			}
		}
		return labelOrID(spec, "-")
	case "create_time", "update_time", "createTime", "updateTime":
		return dateText(record[key])
	}
	value := fieldText(record[key])
	if value == "-" {
		return value
	}
	switch key {
	case "cpuUsage", "gpuUsage", "memUsage", "npuUsage":
		if num, err := strconv.ParseFloat(value, 64); err == nil && !math.IsInf(num, 0) {
			if num == -1 {
				return "-"
			}
			if num >= 0 {
				return fmt.Sprintf("%.2f%%", num*100)
			}
		}
	case "status":
		if name := map[string]string{"0": "正常", "1": "异常"}[value]; name != "" {
			return name
		}
	case "health_status":
		if value == "0" {
			return "正常"
		}
		return "异常"
	}
	return value
}

func combinedFields(record platform.Record, separator string, keys ...string) string {
	var values []string
	for _, key := range keys {
		if value := fieldText(record[key]); value != "-" {
			values = append(values, value)
		}
	}
	return labelOrID(strings.Join(values, separator), "-")
}
