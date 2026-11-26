# 模型查询、模板与模型部署

只用 CLI，不自行调用发布接口；查询与操作默认使用 `--agent` 获取紧凑 JSON（不要与 `-o json` 同传）。完整选项以 `ml model deploy --help` 为准。

## 标准部署流程

1. **查模型**：已知完整模型名时优先用 `ml model list --name 'MODEL_NAME,MODEL_NAME' --agent` 精确查 `modelId`（未命中再回退 `--name MODEL_NAME`；如需确认来源训练任务，查 `ml model source MODEL_ID --agent`）。
2. **查模板**：`ml deployment template list --name TEMPLATE_NAME --agent` 取得 `deployTemplateId`。
3. **预览检查**：`ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run --agent`，核对区域/实例及是否缺少 `--service-timeout` / `--execute-limit`。
4. **用户确认并提交**：向用户复述模型、模板、环境及参数（`product` 环境必须二次确认），授权后加 `--yes --agent` 提交，以返回对象中的 `code == 0` 判成功。
5. **结果核验**：用 `ml service list --agent` 和 `ml service deployment list SERVICE_ID --agent` 确认服务状态。

## 模型查询与溯源

```powershell
ml model list --name 'MODEL_NAME,MODEL_NAME' --agent
ml model list --name MODEL_NAME --agent
ml model detail MODEL_ID --agent
ml model source MODEL_ID --agent
ml model source MODEL_ID --train-task --agent
```

- `--agent` 模式下模型列表项在顶层 `items`，ID 为 `modelId`。
- `model source MODEL_ID --agent` 直接返回溯源输出版本核心字段（含 `modelName`、`modelVersion`、`sourceId`、`jobId` 等）；加 `--train-task --agent` 直接返回关联训练任务核心字段（含 `jobId`、`taskId`、`taskName` 等）。需要完整原始接口响应时改用 `-o json`。
- 溯源中的模型版本读 `modelVersion`，不是详情中的 `modelTag`。
- 来源标识缺失时，CLI 会停止溯源。显式使用 `--train-task` 时，缺少 `jobId` 会报错。

## 定位模板

```powershell
ml deployment template list --name TEMPLATE_NAME --agent
ml deployment template list -A --name TEMPLATE_NAME --agent
ml deployment template detail DEPLOY_TEMPLATE_ID --agent
ml resource template detail RESOURCE_TEMPLATE_ID --agent
```

- `--agent` 模式下列表项均在顶层 `items`：部署模板 ID 为 `deployTemplateId`，资源模板 ID 为 `dockerId`。
- 部署模板详情包含 `deploymentTemplate` 与全部关联资源 `resourceTemplates`；资源模板详情包含 `resourceTemplate` 与 `framework`（需要完整 `frameworkPackage` 原始响应时改用 `-o json`）。
- `--env` 只筛选模板所属环境，不切换 CLI 连接的环境。
- 名称匹配由平台决定，核对名称、版本、环境和业务，不唯一时请用户选择。

## 预览与补填

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run --agent
```

- 部署模板必须关联有效资源模板，每个关联名称必须精确匹配唯一资源。全部关联资源参与部署，不能只选部分区域；各区域实例数固定为 1，弹性伸缩停用。服务名称和版本沿用模型的名称和版本。
- 模板缺少调用超时或最大并发数时，CLI 会列出缺少的参数。向用户要数值后补充 `--service-timeout MILLISECONDS`（毫秒）和 `--execute-limit COUNT`（并发数），不要猜值；`--qps` 不能替代并发数。显式参数优先于模板。
- 预览 JSON 是完整的待提交请求，业务字段在 `data`。核对模型、目标环境、全部区域、实例数和用户指定的参数。其中的框架参数和 Secret 未脱敏，只提取必要字段。

## 提交与核验

用户授权明确覆盖具体模型、模板和参数后提交，保留预览时使用的全部参数：

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes --agent
```

- `--yes` 只跳过 CLI 确认，不替代用户授权；`product` 环境提交前必须再次向用户确认。
- 正式提交时 stdout 是发布响应、摘要在 stderr；dry-run 的 stdout 是请求，两者不要混淆。`--agent` 模式直接返回 `result` 对象，以 `code` 为整数 `0` 判成功（`-o json` 为 `result.code == 0`），非零判失败，不根据描述文本猜结果。
- 取得 `serviceId` 后核验：

```powershell
ml service list --model-name MODEL_NAME --model-version MODEL_VERSION --agent
ml service deployment list SERVICE_ID --agent
```

发布成功不等于服务健康或推理可用。超时、连接中断、认证拒绝或没有有效 code 时，先查询服务，不自动重放发布请求；已存在同名服务也不能直接认定为本次成功。CLI 没有部署等待或取消命令。
