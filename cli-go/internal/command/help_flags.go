package command

import (
	"strings"

	"github.com/spf13/pflag"
)

func helpFlagValue(path string, flag *pflag.Flag, value string) string {
	if strings.HasPrefix(path, "service ") {
		if label := serviceFlagPlaceholders[flag.Name]; label != "" {
			return label
		}
	}
	if flag.Name == "name" {
		group, _, _ := strings.Cut(path, " ")
		if label := helpNameValues[group]; label != "" {
			return label
		}
	}
	if label := helpFlagValues[flag.Name]; label != "" {
		return label
	}
	switch flag.Value.Type() {
	case "int", "int64", "uint", "uint64":
		return "整数"
	case "float32", "float64":
		return "数值"
	case "string", "stringArray", "stringSlice":
		return "文本"
	}
	return value
}

var helpNameValues = map[string]string{
	"algorithm": "算法仓名称", "dataset": "数据集名称", "deployment": "模板名称",
	"feature-task": "任务名称", "featureset": "特征集名称", "model": "模型名称",
	"offline": "实验名称", "resource": "模板名称", "sample-task": "任务名称",
	"train": "任务名称", "webstudio": "实例名称",
}

var helpFlagValues = map[string]string{
	"algorithm-name": "算法仓名称", "before": "北京时间", "bucket-name": "存储桶名称",
	"business-id": "业务 ID", "category": "任务类别", "create-user": "创建人", "creator": "创建者",
	"customize-config": "自定义参数", "cwd": "远端目录", "dataset-name": "数据集名称",
	"definition-id": "样本定义 ID", "department": "部门 ID", "dir": "数据集目录",
	"directory": "本地目录", "download": "本地目录", "end-line": "行号", "end-time": "北京时间",
	"env-id": "实例 ID", "execute-limit": "并发数", "file": "本地文件", "framework-name": "框架名称",
	"framework-type": "框架类型", "from-file": "本地文件", "health-check-mode": "检查模式",
	"health-port": "端口号", "indicator-type": "指标类型", "kernel": "Kernel 名称",
	"keyword": "关键词", "lang": "语言", "limit": "条数", "max-output": "字节数",
	"model-name": "模型名称", "model-version": "模型版本", "output": "格式", "owner": "所有者",
	"page": "页码", "page-size": "条数", "project-name": "项目名称", "qps": "每秒请求数",
	"request-file": "本地文件", "resource-type": "资源类型", "response-file": "本地文件",
	"role-job-id": "角色作业 ID", "scope": "A|B|C", "scope-lines": "行数", "select": "编号或 all",
	"service-timeout": "毫秒", "set-id": "特征集 ID", "start-line": "行号", "start-time": "北京时间",
	"startup-timeout": "秒数", "state": "运行状态", "status": "状态", "studio-id": "实例 ID",
	"table-name": "表名", "tag": "指标名称", "team-id": "团队 ID", "template": "部署模板 ID",
	"template-type": "模板类型", "tenant": "租户 ID", "timeout": "秒数", "update-mode": "更新模式",
	"updater": "修改者", "version": "版本号",
}
