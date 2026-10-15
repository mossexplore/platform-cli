# 模板与模型部署

用于资源模板、部署模板查询，以及将已有模型部署为服务。先按 SKILL.md 核对当前环境、认证、业务和用户目标；只使用 CLI，不手工拼接发布 HTTP 请求。

## 定位模型及模板

```powershell
ml model list --name MODEL_NAME -o json
ml deployment template list --name TEMPLATE_NAME -o json
```

模型列表在 `result.models`，取 `modelId`；部署模板列表在 `result.deployTemplates`，取 `deployTemplateId`。名称筛选不保证唯一，核对名称、模型版本、模板环境及业务；必要时翻页或请用户选定，不能默认取首条。用户已提供准确 ID 时直接使用。

需要查看模板时：

```powershell
ml deployment template detail DEPLOY_TEMPLATE_ID -o json
ml resource template list --name RESOURCE_TEMPLATE_NAME -o json
ml resource template detail RESOURCE_TEMPLATE_ID -o json
```

部署模板详情在 `deploymentTemplate.result.template`；`resourceTemplates` 每项含 `requestedName`、完整 `response`、`exactMatches`、`error`。关联查询不分页，必须按名称完全相等匹配；缺失或多个同名项导致失败，CLI 保留其余结果但返回非零。不要继续使用含 error 的详情部署。

资源模板列表在 `result.resourceTemplateInfoList`，资源 ID 字段为 `dockerId`。资源详情在 `resourceTemplate.result`，框架包在 `frameworkPackage.result.data`；未关联框架时后者可为 null。不要将资源 ID、模板名称、部署模板 ID、框架包 ID 混用。详情会查询框架，若只需定位资源 ID，优先使用列表。

## 预览及参数补填

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run -o json
```

模板必须关联至少一个有效容器资源模板。关联几个就部署几个区域，不能选择部分区域，无部署配置覆盖文件。预览 JSON 为完整发布请求，业务数据在 `data`，包含 `modelInfo`、`serviceInfo`、`comptPkgs`、`extendConfiguration`、`serviceBlocks`、`serviceDocument`，外层另有 `eFlowInfo`。框架参数和 Secret 原样出现，不将完整预览送入共享记录或回复；只提取核验所需字段。

| 选项 | 规则 |
| --- | --- |
| `--service-timeout MILLISECONDS` | 对应 serviceTimeout，正整数，单位毫秒；显式参数优先，否则读取模板 |
| `--execute-limit COUNT` | 对应 executeLimit，非负整数，单实例最大并发数；显式参数优先，否则读取模板 |
| `--qps COUNT` | 单实例每秒请求数上限，正整数；不等于并发数；未指定时请求省略 requestLimit，人工预览显示 `-` |
| `--update-mode rolling` / `in-place` | 滚动更新 / 原地更新，默认 rolling |
| `--health-check-mode default` / `response-code` / `response-code-and-data` | Default / RespCodeMatch / RespCodeAndDataMatch；默认 default，不需额外响应匹配参数 |
| `--health-port PORT` | 默认 18090，范围 1 至 65535 |
| `--description TEXT` | 服务文档描述，默认空字符串，不替代区域描述 |
| `--request-file FILE` / `--response-file FILE` | 本地 UTF-8 文件，路径相对于当前工作目录；文本原样提交，未指定时为空字符串 |

模板和命令均未提供调用超时或最大并发数时，CLI 一次列出缺少的选项和命令格式；向用户获取数值后补齐，不猜测或把示例值当作业务要求。重试前保留原模型、模板及其他用户选项。例如：

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --service-timeout MILLISECONDS --execute-limit COUNT --dry-run -o json
```

核对实际部署内容：

- 服务名称与服务版本分别使用模型名称及模型版本，不提供独立覆盖参数。
- 每个 `serviceBlocks` 是一个区域，实例数固定为字符串 `"1"`，不继承资源模板实例数，弹性伸缩停用。不能宣称已经沿用模板中的多实例数量或伸缩策略。
- 镜像、资源、框架配置、环境变量、Hosts、调度、启动参数和自定义启动命令来自对应资源模板。框架配置必须为有效非空 JSON 对象，不能自行补成空对象绕过校验。
- 可选主机标签、Hosts、环境变量、启动参数缺失或为 null 时使用空数组；自定义启动命令、SFS 路径使用空字符串。GPU/NPU 缺失、为 null 或空字符串时使用 `"0"`，非零已有值保留；CPU、内存和框架存储标识仍须有效。
- 模型来源环境、团队缺失或 null 时为空字符串，标签、历史副本和组件包列表为空数组。可选字段的默认值由 CLI 处理，不要求用户在 Web 补填空值；错误类型仍需修复。
- 健康检查优先使用模板，缺失、null 或空字符串时默认：类型 httpGet、方法 health、检查超时 5 秒、拉起超时 120 秒、首次检查延迟 120 秒、间隔 10 秒、阈值 3、优雅下线 10 秒。告警领域取当前业务所属真实租户的首个 serviceGroup，不能拿团队业务 ID 代替租户 ID。

人工预览分为基本信息、部署区域、扩展参数、服务文档。基本信息仅展示模型名称及版本、部署方式、更新模式、环境、推理类型、QPS、最大并发数、调用超时、自定义及公共组件包；区域标题使用集群名称，逐区展开框架和扩展配置，文档显示完整报文。标题青色加粗、带层级编号，表格内不编号。

## 提交与结果核验

用户授权已明确覆盖当前模型、模板及部署目标时，按其意图提交；如果仅要求查询、预览或设计，不发布。参数和目标未明确时先补齐。Agent 使用非交互调用：

```powershell
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes -o json
```

`--yes` 只跳过 CLI 交互确认，不替代用户授权。需要补填的参数同样传入正式命令。不要为输入 y 分配 PTY。交互终端可不传 --yes，CLI 展示配置后确认。

正式 JSON 模式的 stdout 是完整发布响应，摘要和确认在 stderr；dry-run 的 stdout 是待提交请求，两者不可混淆。发布返回 `result.code` 为整数 0 时按接口约定成功，展示 `result.serviceId` 及结果；非零即失败，即使 des 同时含 success 字样也不能判成功。缺少有效 code 时结果未确认。

取得服务 ID 后可核验：

```powershell
ml service list --model-name MODEL_NAME --model-version MODEL_VERSION -o json
ml service deployment list SERVICE_ID -o json
```

服务列表及部署视图的分页限制见命令索引。发布成功不等于已验证服务健康或真实推理成功，仅报告实际观察到的状态。CLI 没有部署 `--wait` 或取消命令，不虚构参数。

发布不自动重放。超时、连接中断、认证拒绝或响应异常时，先查服务及区域状态，不直接重复部署；同名服务存在时不能自行视为本次成功，需核对版本、环境、状态及用户目标。只读查询可在会话有效时有限重试。补填参数失败发生在正式提交前，区分这种校验失败与“提交结果未确认”。
