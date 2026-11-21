package command

const exampleServiceID = "7b8f2a16-3d9c-4e51-8a72-6f04b9d1c305"
const examplePod = "demo-inference-5d6b8d9f7c-k2m9x"
const serviceIDNote = "示例中的服务 ID 为演示值。从 ml service list 的结果复制当前业务的服务 ID 后执行。"

var serviceFlagPlaceholders = map[string]string{
	"name": "服务名称", "service-name": "服务名称", "model-name": "模型名称",
	"model-version": "模型版本", "page": "页码", "page-size": "条数", "output": "格式",
	"pod-ip": "Pod IP", "pod": "Pod 名称", "cluster-name": "集群名称",
	"container": "容器名称", "request-sample-file": "文件路径", "transmission-tag": "0|1",
	"type": "日志类别", "file": "文件名", "keyword": "关键词", "lines": "行数",
	"search-order": "顺序", "grep-scope": "范围", "grep-line": "行数",
}

var serviceHelpPages = map[string]helpPage{
	"service": {
		examples: []string{"ml service list --name demo", "ml service host --help"},
	},
	"service list": {
		intro: "分页查询服务，默认范围为当前选中的业务。",
		examples: []string{
			"# 查询当前业务中名称匹配 demo 的服务",
			"ml service list --name demo",
			"# 在当前环境的全部租户中查询，输出 JSON",
			"ml service list -A --name demo -o json",
		},
	},
	"service mock": {
		note:     serviceIDNote + "\n执行时会实际调用服务。未指定样例文件时使用服务文档中的样例。",
		examples: []string{"ml service mock " + exampleServiceID + " --request-sample-file ./sample.json -o json"},
	},
	"service host": {
		examples: []string{"ml service host list --help", "ml service host log-search --help"},
	},
	"service host list": {
		intro: "查询指定服务的主机视图，显示第 1 页的 10 条记录。",
		note:  serviceIDNote,
		examples: []string{
			"ml service host list " + exampleServiceID,
			"ml service host list " + exampleServiceID + " --pod-ip 192.0.2.14 -o json",
		},
	},
	"service host mock": {
		note:     serviceIDNote + "\nPod IP 可从主机列表取得。执行时会实际调用指定主机。",
		examples: []string{"ml service host mock " + exampleServiceID + " --pod-ip 192.0.2.14 -o json"},
	},
	"service host pod-event": {
		argumentUsage: "SERVICE_ID", alternateTarget: "--pod <Pod 名称> --cluster-name <集群名称>",
		note: serviceIDNote + "\n直接按 Pod 查询时须同时提供集群名称。Pod 名称和集群可从主机列表取得。",
		examples: []string{
			"ml service host pod-event " + exampleServiceID,
			"ml service host pod-event --pod " + examplePod + " --cluster-name cluster-dev -o json",
		},
	},
	"service host log-stdout": {
		argumentUsage: "SERVICE_ID", alternateTarget: "--pod <Pod 名称>",
		note: serviceIDNote + "\nPod 名称可从主机列表取得。可查询的容器名称由平台返回。",
		examples: []string{
			"ml service host log-stdout " + exampleServiceID,
			"ml service host log-stdout --pod " + examplePod + " -c filebeat -o json",
		},
	},
	"service host log-search": {
		note: serviceIDNote + "\n--list 不能与正文检索选项同时使用。",
		examples: []string{
			"ml service host log-search " + exampleServiceID + " --type interface --list",
			"ml service host log-search " + exampleServiceID + " --type interface --file interface.log -k error -n 100",
		},
	},
	"service deployment": {examples: []string{"ml service deployment list --help"}},
	"service deployment list": {
		intro:    "查询指定服务的部署视图，显示第 1 页的 10 条记录。",
		note:     serviceIDNote,
		examples: []string{"ml service deployment list " + exampleServiceID + " -o json"},
	},
}
