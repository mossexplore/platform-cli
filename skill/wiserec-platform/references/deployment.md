# 模板与模型部署

先按 SKILL.md 核对环境、认证、业务和用户目标；只使用 CLI，不自行调用发布接口。完整选项见 [命令索引](commands.md)，以已安装 CLI 的 `--help` 为准。

## 定位目标

```powershell
ml model list --name MODEL_NAME -o json
ml deployment template list --name TEMPLATE_NAME -o json
```

模型在 `result.models`，取 `modelId`；部署模板在 `result.deployTemplates`，取 `deployTemplateId`。名称查询不保证唯一，核对名称、版本、环境和业务，需要时翻页或请用户选择，不默认取首条。已有准确 ID 时直接使用。

需要查看配置时用 `ml deployment template detail DEPLOY_TEMPLATE_ID -o json`；模板在 `deploymentTemplate.result.template`，关联资源在 `resourceTemplates`，每项包含 `exactMatches` 和 `error`。资源详情使用 `ml resource template detail RESOURCE_TEMPLATE_ID -o json`，结果为 `resourceTemplate` 和 `frameworkPackage`。不同对象的 ID 不混用。

## 预览与补填

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run -o json
```

部署模板必须关联有效资源模板，每个关联名称必须精确匹配唯一资源。全部关联资源参与部署，不能选择部分区域；各区域实例数固定为 1，不继承模板实例数，弹性伸缩停用。服务名称和版本沿用模型名称和版本。

模板未配置调用超时或最大并发数时，CLI 会列出缺少的参数。向用户获取数值，再补充 `--service-timeout MILLISECONDS`（正整数，毫秒）、`--execute-limit COUNT`（非负整数，并发数）；不要猜值。显式参数优先于模板。`--qps` 是每秒请求数上限，不能替代并发数。

预览 JSON 是完整待提交请求，业务字段在 `data`。核对模型、目标环境、全部区域、实际实例数和用户指定参数。框架参数及 Secret 原样出现，只提取必要字段，不转发完整响应或写入共享日志。

## 提交与核验

用户授权已明确覆盖具体部署目标和参数后，非交互提交：

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes -o json
```

正式命令保留补填参数和用户指定的其他选项。`--yes` 仅跳过 CLI 确认，不替代用户授权；只要求查询或预览时不发布，也不为输入 y 分配 PTY。

正式 JSON 模式 stdout 为发布响应，摘要在 stderr；dry-run 的 stdout 为请求，两者不可混淆。`result.code` 为整数 0 判成功，非零判失败，不解析 des 文本猜结果。取得 `result.serviceId` 后核验：

```powershell
ml service list --model-name MODEL_NAME --model-version MODEL_VERSION -o json
ml service deployment list SERVICE_ID -o json
```

发布成功不等于已验证服务健康或推理成功。超时、连接中断、认证拒绝或缺少有效 code 时，先查询远端状态，不自动重放发布请求；同名服务存在也不能直接判为本次成功。CLI 没有部署 `--wait` 或取消命令，不虚构选项。
