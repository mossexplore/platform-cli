# 模型查询、模板与模型部署

默认使用 `--agent`（不与 `-o json` 同传），无需预先执行 `--help`。

## 标准部署最短链路

```powershell
ml model list --name 'MODEL_NAME,MODEL_NAME' --agent                                         # 1. 取 modelId
ml deployment template list --name TEMPLATE_NAME --agent                                     # 2. 取 deployTemplateId
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run --agent                     # 3. 预览核对
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes --agent                         # 4. 确认后提交（保留预览全部参数）
ml service list --model-name MODEL_NAME --model-version MODEL_VERSION --agent                # 5. 核验服务与部署
ml service deployment list SERVICE_ID --agent
```

## 模型查询与溯源

```powershell
ml model detail MODEL_ID --agent
ml model source MODEL_ID --agent
ml model source MODEL_ID --train-task --agent
```

- `model source --agent` 返回输出版本核心字段（版本读 `modelVersion`，非详情中的 `modelTag`）；加 `--train-task` 直接返回关联训练任务核心字段（`jobId` / `taskId`）。来源标识缺失会停止溯源；`--train-task` 缺少 `jobId` 会报错。需要完整原始接口响应时改用 `-o json`。

## 定位资源与部署模板

```powershell
ml deployment template list --name TEMPLATE_NAME --agent
ml deployment template detail DEPLOY_TEMPLATE_ID --agent
ml resource template list --name TEMPLATE_NAME --agent
ml resource template detail RESOURCE_TEMPLATE_ID --agent
```

- 列表项均在顶层 `items`（部署模板 ID 为 `deployTemplateId`，资源模板 ID 为 `dockerId`）。`--env` 仅筛选模板环境，不切换 CLI 环境；名称匹配不唯一时请用户选择。
- 详情：`deployment template detail` 含 `deploymentTemplate` 与关联 `resourceTemplates`；`resource template detail` 含 `resourceTemplate` 与 `framework`（需完整 `frameworkPackage` 时改用 `-o json`）。

## 预览、补填与提交规则

- **资源约束**：部署模板关联的每个资源模板名必须精确匹配唯一资源，全部关联区域均参与部署；各区域实例数固定为 `1`、停用弹性伸缩；服务名与版本沿用模型。
- **缺参补填**：预览提示缺少调用超时或最大并发数时，向用户确认数值后补传 `--service-timeout MS`（毫秒）和 `--execute-limit COUNT`（并发数），**禁止猜值**，`--qps` 不能替代并发数；显式参数优先于模板。
- **预览核对**：`--dry-run` 输出完整待提交请求（业务字段在 `data`），核对模型、环境、全部区域、实例数与参数；框架参数/Secret 未脱敏，仅提取必要字段。
- **提交与判成**：`--yes` 不替代用户授权（`product` 环境须二次确认）。正式提交 `--agent` 直接返回 `result` 对象，**以 `code == 0` 判成功**（非零判失败，不凭描述猜）。发布成功不等于服务健康；超时/断连/无有效 `code` 时先查服务，**不自动重放**（已存在同名服务也不代表本次成功）；CLI 无部署等待或取消命令。
