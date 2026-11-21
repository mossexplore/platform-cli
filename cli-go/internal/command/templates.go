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

const resourcePrefix = "/ai/backend/mep/resourcetemp/"
const deployTemplatePrefix = "/ai/backend/mep/scm/deploytemplate/"

func newTemplateGroup(options Options, load loadConfig, deployment bool) *cobra.Command {
	name, heading := "resource", "资源管理"
	var query catalogQuery
	var detail *cobra.Command
	if deployment {
		name, heading = "deployment", "部署管理"
		query = catalogQuery{route: deployTemplatePrefix + "queryList", command: "list", summary: "查询部署模板列表", allowAllBusiness: true,
			nameHelp: "按部署模板名称筛选", paged: true, nullable: []string{"name", "env", "framework-type"}, strings: []string{"framework-name"},
			assign: map[string]string{"name": "deployTemplateName", "env": "env", "framework-type": "frameworkType", "framework-name": "frameworkPkgName"},
			fixed:  defaultFields("frameworkPkgId", "inferenceType gatewayName isSystem deployTemplateType componentName componentVersion", ""),
			body:   withBusiness, preserve: true, items: "deployTemplates", total: "count", empty: "暂无部署模板", value: templateValue,
			columns: []recordColumn{{"部署模板 ID", "deployTemplateId"}, {"模板名称", "deployTemplateName"}, {"环境", "env"},
				{"业务编码", "businessId"}, {"组件包", "comptPkgInfoList"}, {"模板类型", "deployTemplateType"}, {"资源模板", "dockerResourceTemplate"},
				{"推理类型", "inferenceType"}, {"是否默认模板", "defaultFlag"}, {"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"是否系统模板", "isSystem"}},
		}
		detail = newDeploymentDetail(options, load)
	} else {
		query = catalogQuery{route: resourcePrefix + "queryList", command: "list", summary: "查询资源模板列表", allowAllBusiness: true,
			nameHelp: "按资源模板名称筛选", paged: true, nullable: []string{"env", "framework-type"}, strings: []string{"name", "framework-name", "resource-type", "template-type"},
			defaults: map[string]string{"resource-type": "docker", "template-type": "docker"},
			assign: map[string]string{"env": "env", "framework-type": "frameworkType", "name": "dockerResourceTemplateName",
				"framework-name": "frameworkPkgName", "resource-type": "resourceType", "template-type": "templateType"},
			fixed: defaultFields("frameworkPkgId gatewayName", "quotaType clusterName dockerType containerSpec appImageName imageTag domain", ""),
			body:  withBusiness, preserve: true, items: "resourceTemplateInfoList", total: "count", empty: "暂无容器资源模板", value: templateValue,
			columns: []recordColumn{{"资源模板 ID", "dockerId"}, {"模板名称", "dockerResourceTemplateName"}, {"环境", "env"}, {"YAML 模板名", "containerSpec"},
				{"镜像名称", "appImageName"}, {"镜像标签", "imageTag"}, {"业务编码", "businessId"}, {"集群名称", "clusterName"},
				{"创建时间", "createTime"}, {"更新时间", "updateTime"}, {"状态", "status"}},
		}
		detail = newResourceDetail(options, load)
	}
	group := &cobra.Command{Use: name, Short: heading}
	template := &cobra.Command{Use: "template", Short: strings.TrimSuffix(heading, "管理") + "模板查询"}
	template.AddCommand(query.build(options, load), detail)
	group.AddCommand(template)
	return group
}

func newResourceDetail(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "detail TEMPLATE_ID", Short: "查询资源模板详情", Args: positional(1)}
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		ctx := cmd.Context()
		data, err := api.JSON(ctx, http.MethodPost, resourcePrefix+"queryDetail", nil, map[string]string{"dockerId": args[0]})
		if err != nil {
			return err
		}
		record, err := platform.Result(data, "查询资源模板详情", false)
		if err != nil {
			return err
		}
		frameworkID := record.Text("frameworkPkgId")
		frameworkText := "未关联推理框架"
		var frameworkData json.RawMessage
		var frameworkErr error
		if raw := record["frameworkPkgId"]; len(raw) != 0 && fieldText(raw) != "-" {
			frameworkText = "框架信息不可用"
			if strings.TrimSpace(frameworkID) == "" {
				frameworkErr = errors.New("frameworkPkgId 应为非空字符串")
			} else {
				frameworkData, frameworkErr = api.JSON(ctx, http.MethodPost, "/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail", nil,
					map[string]string{"frameworkPkgId": frameworkID})
				if frameworkErr == nil {
					check, err := platform.Result(frameworkData, "查询推理框架", false)
					frameworkErr = err
					pkg := check.Object("data")
					if frameworkErr == nil && (strings.TrimSpace(pkg.Text("name")) == "" || strings.TrimSpace(pkg.Text("version")) == "") {
						frameworkErr = errors.New("框架响应缺少名称或版本")
					}
					if frameworkErr == nil {
						frameworkText = pkg.Text("name") + "@" + pkg.Text("version")
					}
				}
				if frameworkErr != nil {
					frameworkData = nil
				}
			}
		}
		out := cmd.OutOrStdout()
		if format == "json" {
			if err := output.JSON(out, map[string]json.RawMessage{"resourceTemplate": data, "frameworkPackage": frameworkData}); err != nil {
				return err
			}
		} else {
			fmt.Fprintln(out, "1、基本信息")
			spec := combinedFields(record, "/", "cpu", "memory", "npu")
			fields := output.Fields{
				{Key: "容器资源模板名称", Value: fieldText(record["dockerResourceTemplateName"])},
				{Key: "资源类型", Value: templateValue(record, "templateType")}, {Key: "环境", Value: fieldText(record["env"])},
				{Key: "集群名称", Value: fieldText(record["clusterName"])}, {Key: "镜像", Value: combinedFields(record, " ", "appImageName", "imageTag")},
				{Key: "自定义 YAML", Value: fieldText(record["containerSpec"])}, {Key: "配额类型", Value: fieldText(record["quotaType"])},
				{Key: "框架类型", Value: fieldText(record["frameworkType"])}, {Key: "默认资源规格", Value: spec},
				{Key: "挂载 SFS 标识", Value: fieldText(record["sfsLocation"])}, {Key: "实例数", Value: fieldText(record["replicas"])},
			}
			if err := fields.Table(out); err != nil {
				return err
			}
			fmt.Fprintf(out, "2、推理框架\n2.1、推理框架名称：%s\n2.2、参数配置\n", frameworkText)
			params := record["frameworkConfiguration"]
			if value := record.Text("frameworkConfiguration"); value != "" {
				params = json.RawMessage(value)
			}
			if fieldText(params) == "-" {
				fmt.Fprintln(out, "暂无参数配置")
			} else {
				var valid platform.Record
				if json.Unmarshal(params, &valid) != nil || valid == nil {
					return errors.New("frameworkConfiguration 参数配置解析失败")
				}
				if err := output.ResultTable(out, params); err != nil {
					return err
				}
			}
			fmt.Fprintln(out, "3、扩展信息")
			for i, section := range []struct {
				title, key string
				cols       []recordColumn
			}{
				{"环境变量", "envs", []recordColumn{{"变量名", "envKey"}, {"变量值", "envValue"}}},
				{"Hosts 映射", "hostIpNames", []recordColumn{{"域名", "hostName"}, {"映射 IP", "hostIp"}}},
				{"主机调度", "hostLabels", []recordColumn{{"主机标签键", "hostLabelKey"}, {"主机标签值", "hostLabelValue"}}},
			} {
				fmt.Fprintf(out, "3.%d、%s\n", i+1, section.title)
				rows := recordList(record[section.key])
				if len(rows) == 0 {
					fmt.Fprintln(out, "暂无")
					continue
				}
				if err := renderRecordTable(out, section.cols, rows, catalogValue); err != nil {
					return err
				}
			}
			fmt.Fprintf(out, "3.4、启动参数\n%s\n3.5、自定义启动命令：%s\n", fieldText(record["args"]), fieldText(record["customStartupCommand"]))
		}
		if frameworkErr != nil {
			return fmt.Errorf("推理框架查询失败：%w", frameworkErr)
		}
		return nil
	})
	return cmd
}

func newDeploymentDetail(options Options, load loadConfig) *cobra.Command {
	cmd := &cobra.Command{Use: "detail TEMPLATE_ID", Short: "查询部署模板详情", Args: positional(1)}
	outputFlag(cmd)
	cmd.RunE = authorized(options, load, func(cmd *cobra.Command, args []string, api *platform.API, format string) error {
		ctx, out := cmd.Context(), cmd.OutOrStdout()
		payload, err := api.JSON(ctx, http.MethodPost, deployTemplatePrefix+"queryDetail", nil, map[string]string{"deployTemplateId": args[0]})
		if err != nil {
			return err
		}
		result, err := platform.Result(payload, "查询部署模板详情", false)
		if err != nil {
			return err
		}
		template := result.Object("template")
		if template == nil {
			return errors.New("部署模板详情缺少有效的 result.template")
		}
		var names []string
		if value := template["dockerResourceTemplate"]; len(value) > 0 && (json.Unmarshal(value, &names) != nil || names == nil) {
			return errors.New("dockerResourceTemplate 应为名称列表")
		}
		entries := []map[string]any{}
		var matches []platform.Record
		var linkedErrors []string
		for _, name := range names {
			if strings.TrimSpace(name) == "" || strings.TrimSpace(template.Text("deployTemplateType")) == "" ||
				strings.TrimSpace(template.Text("businessId")) == "" {
				return errors.New("关联资源查询缺少模板名称、类型或业务 ID")
			}
			entry := map[string]any{"requestedName": name, "response": nil, "exactMatches": []platform.Record{}, "error": nil}
			raw, err := api.JSON(ctx, http.MethodPost, resourcePrefix+"queryList", nil, map[string]string{
				"templateType": template.Text("deployTemplateType"), "businessId": template.Text("businessId"), "dockerResourceTemplateName": name,
			})
			if err == nil {
				var resources platform.Record
				resources, err = platform.Result(raw, "查询关联资源模板", false)
				if err == nil {
					entry["response"] = raw
					items := recordList(resources["resourceTemplateInfoList"])
					exact := []platform.Record{}
					for _, item := range items {
						if item.Text("dockerResourceTemplateName") == name {
							exact = append(exact, item)
						}
					}
					entry["exactMatches"] = exact
					matches = append(matches, exact...)
					if len(exact) != 1 {
						err = fmt.Errorf("找到 %d 个名称完全相同的资源模板", len(exact))
					}
				}
			}
			if err != nil {
				entry["error"] = err.Error()
				linkedErrors = append(linkedErrors, name+"："+err.Error())
			}
			entries = append(entries, entry)
		}
		if format == "json" {
			if err := output.JSON(out, map[string]any{"deploymentTemplate": payload, "resourceTemplates": entries}); err != nil {
				return err
			}
		} else if err := renderDeploymentTemplate(cmd, template, matches, linkedErrors); err != nil {
			return err
		}
		if len(linkedErrors) != 0 {
			return errors.New("关联资源模板查询存在失败、缺失或同名歧义，请核对详情输出")
		}
		return nil
	})
	return cmd
}

func renderDeploymentTemplate(cmd *cobra.Command, template platform.Record, resources []platform.Record, linkedErrors []string) error {
	out := cmd.OutOrStdout()
	for _, section := range []struct {
		title string
		cols  []recordColumn
	}{
		{"1、基本信息", []recordColumn{{"租户", "businessId"}, {"是否默认模板", "defaultFlag"}, {"部署模板名称", "deployTemplateName"},
			{"环境", "env"}, {"资源模板类型", "deployTemplateType"}, {"组件包", "customComponents"}, {"公共组件包（平台提供）", "commonComponents"},
			{"工作进程数", "workNum"}, {"单个工作进程线程数", "threadNum"}, {"最大并发数", "executeLimit"}, {"超时时间（ms）", "serviceTimeout"},
			{"是否系统模板", "isSystem"}, {"推理类型", "inferenceType"}, {"描述", "description"}}},
		{"2、健康检查参数", []recordColumn{{"健康检查类型", "healthType"}, {"健康检查方法", "healthPath"}, {"服务拉起超时时间（s）", "startTimeOut"},
			{"健康检查超时时间（s）", "healthCheckTimeout"}, {"开始健康检查（s）", "initialDelaySeconds"}, {"健康检查间隔（s）", "periodSeconds"},
			{"不健康阈值", "failureThreshold"}, {"优雅下线时间（s）", "terminationGracePeriodSeconds"}}},
	} {
		fmt.Fprintln(out, section.title)
		fields := output.Fields{}
		for _, column := range section.cols {
			fields = append(fields, output.Field{Key: column.title, Value: templateValue(template, column.key)})
		}
		if err := fields.Table(out); err != nil {
			return err
		}
	}
	fmt.Fprintln(out, "3、容器资源模板")
	if len(resources) > 0 {
		if err := renderRecordTable(out, []recordColumn{{"模板名称", "dockerResourceTemplateName"}, {"YAML 模板名", "containerSpec"},
			{"镜像名称", "appImageName"}, {"镜像标签", "imageTag"}, {"集群名称", "clusterName"}, {"实例数", "replicas"}, {"状态", "status"}}, resources, templateValue); err != nil {
			return err
		}
	} else {
		fmt.Fprintln(out, "暂无匹配的容器资源模板")
	}
	for _, message := range linkedErrors {
		fmt.Fprintln(cmd.ErrOrStderr(), "[警告]", message)
	}
	return nil
}

func templateValue(record platform.Record, field string) string {
	value := catalogValue(record, field)
	switch field {
	case "templateType", "deployTemplateType":
		if value == "docker" {
			return "容器"
		}
		if value != "-" {
			return "虚拟机"
		}
	case "status":
		if value == "0" {
			return "在用"
		}
		if value != "-" {
			return "停用"
		}
	case "defaultFlag", "isSystem":
		if value == "0" {
			return "否"
		}
		if value != "-" {
			return "是"
		}
	case "healthType":
		return labelOrID(map[string]string{"httpGet": "http", "tcpSocket": "tcp"}[value], value)
	case "dockerResourceTemplate":
		var names []string
		_ = json.Unmarshal(record[field], &names)
		return labelOrID(strings.Join(names, ","), "-")
	case "comptPkgInfoList", "customComponents", "commonComponents":
		var names []string
		for _, item := range recordList(record["comptPkgInfoList"]) {
			common := item.Text("businessId") == "common"
			if field == "commonComponents" && !common || field == "customComponents" && common {
				continue
			}
			names = append(names, fieldText(item["name"])+"@"+fieldText(item["version"]))
		}
		return labelOrID(strings.Join(names, ","), "-")
	}
	return value
}
