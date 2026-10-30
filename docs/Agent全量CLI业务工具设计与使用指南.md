# Agent 全量 CLI 业务工具设计与使用指南

## 目标与实现范围

在网页对话中完成现有 CLI 的业务操作：查询、克隆、启动、停止、取消、删除、配置更新、模型部署、数据集文件操作、文件下载导出，以及 Web Studio/Jupyter 文件、命令、Notebook 和终端操作。

复用 `wiserec_cli.services`、文件协议与 Jupyter 协议实现，不执行拼接的本机 Shell 命令，不向模型开放任意 HTTP 请求入口。业务工具注册、参数 Schema、CLI 权限命令、操作类型集中管理。后续新增 CLI 业务命令时，独立命令树覆盖测试会检查是否遗漏 Agent 映射。

当前实现为本地单进程 Agent 工作台；没有将其改成可直接公网部署的多人云服务。原有登录、数据库和模型配置方式继续使用。新增 CLI 业务命令须同步工具注册、发现目录、参数 Schema 和权限映射。本次增加质量监控查询工具，不改变 Agent 数据库表结构或正式发布流程。

## 质量监控报告

通过“质量监控”“质量报告”“特征质量”“特征列表”“空值率”“时效性”或领域 `quality` 发现工具，也可按精确工具名加载。

| 工具 | CLI 权限命令 | 参数 |
| --- | --- | --- |
| `list_quality_features` | `ml quality feature list` | `name`、`table_name`、`feature_value_type`、`indicator_type`、`page`、`page_size` |
| `list_quality_wide_featuresets` | `ml quality wide-featureset list` | `name`、`page`、`page_size` |
| `list_feature_null_rates` | `ml quality feature list` | 与 `list_quality_features` 相同，只返回空值率 |

名称和表名默认空字符串；类型默认 null，在实际请求体中省略。两个类型参数独立筛选，均接受连续/CONTINUOUS、离散/DISCRETE、有序/ORDINAL、分类/CATEGORICAL、序列/SEQUENCE、长序列/LONG_SEQUENCE、向量/VECTOR，英文忽略大小写。

默认第 1 页、每页 10 条；页码范围为 1～10000，每页条数为 1～100，并继续受管理员 `runtime.max_page_size` 限制。每次只取一页，返回 `items`、`count`、`pageIndex`、`pageSize`，分页优先采用响应值。完整保留记录的原始字段及数值，例如空值率 0.125，不把 CLI 表格的百分比文本写入工具数据。特征周期原值保留；Agent 公共输出边界继续沿用现有的时间规范化规则。

三个工具均为只读，无新增网页确认。身份、环境、业务与凭据由会话确定，不允许模型传入业务 ID 或接口 URL。权限拒绝时不调用质量监控接口。宽表质量查询与 `list_featuresets` 的普通宽表列表用途不同。

### 只查询空值率

需要统计空值率分布、阈值占比时，优先使用 `list_feature_null_rates`，避免完整特征记录占用工具输出预算。它复用特征质量接口和权限，不接受模型指定业务、身份或 URL。

```json
{"name":"list_feature_null_rates","arguments":{"page":1,"page_size":10,"table_name":"TABLE_NAME"}}
```

工具结果的 `data` 示例：

```json
{"nullValueRates":[0,0.125,1,null],"count":300,"pageIndex":1,"pageSize":10}
```

`nullValueRates` 中每个元素对应本页一条特征，保留服务端顺序和重复值，不附带 ID、名称或其他特征字段。0～1 数值直接参与统计，0.125 表示 12.5%；缺失或 null 保留为 null，不当作 0，也不直接丢弃。字符串、布尔值、非有限数值或超出 0～1 的值报错，不静默修正。提取发生在 Agent 输出预算检查之前。

`count` 是筛选后的全部特征数，数组长度是本页记录数，`pageIndex` 和 `pageSize` 优先采用响应值。一次只取一页，不自动宣称全量；全量占比须按相同筛选条件翻页收集，统计有效空值率分布时排除 null，并单独报告未知数量。该工具仅提供数值，不预先计算占比或平均值。

## 工具发现与渐进加载

每条消息创建独立工具加载集合。先根据问题选取一个领域的前四个工具；无法判断时只提供 `discover_tools`。模型可请求目录、按领域分页或按完整工具名加载。

```json
{"query":""}
```

```json
{"domain":"jupyter_files","offset":0}
```

```json
{"domain":"jupyter_files","offset":4}
```

```json
{"query":"publish_model_deployment"}
```

一次发现最多四个工具；`next_offset` 为下一页位置，空值表示结束。默认每轮最多加载 16 个业务工具，发现 4 次、总工具调用 20 次、模型请求轮次 12 次。达到上限时拆分对话请求，不能把未加载理解为没有该能力。领域目录见本文末尾覆盖表。

## 身份与权限链路

1. 网页登录后，服务端确定平台账号、环境、Cookie 和 CSRF 凭据。
2. 对话绑定选定业务。工具参数不接受 Cookie、用户名、businessid、tenant_id 或任意接口 URL。
3. 业务调用前复核平台身份和登录会话；每次平台业务 HTTP 请求向权限服务发送对应的真实 CLI 命令，沿用 CLI 版本准入。
4. `businessid` 来自会话已验证的业务目录，不能由模型替换。操作者字段来自登录用户。模型部署所需真实租户 ID 来自同一业务选择。
5. 文件流、Multipart 上传、Jupyter HTTP、WebSocket 建连和发送也经过权限检查。取消、退出、过期及权限拒绝会阻止后续业务请求。
6. 模型工具发现仅访问静态目录，不返回业务数据，也不授予权限。确认执行同样不授予业务权限。

管理员在现有权限服务中给相应账号和环境授权；网关 URL、服务端网关 Token 使用原 `access_control` 配置。具体命令以覆盖表为准，例如启动开发环境检查 `ml webstudio start`，主机推理测试检查 `ml service host mock`，模型特征集查询检查 `ml featureset model list`，不能用另一个只读或相邻命令替代。

同一工具调用的权限请求共享 invocation ID，各请求另有独立 request ID。工具名、参数、完成状态、耗时，以及确认请求和决定写入现有 ToolCall/Event 审计记录。鉴权失败不会因为 CLI 服务包装异常而被吞掉后继续执行。

## 写入与执行确认

所有有副作用的工具，包括推理测试、远端命令、Notebook 执行、终端输入、上传、文件写入/删除，都必须通过网页确认卡片。对话中说“同意”或工具参数中的布尔值不能代替该卡片。

卡片显示当前环境、业务、工具、具体参数；涉及附件时显示文件名、大小及 SHA-256；涉及部署和批量取消时显示不可变计划内容。确认 API 只接收 `approved: true/false`，不能同时修改目标和参数。

确认凭据绑定会话、运行、业务、工具及完整参数，只能消费一次。重复点击、另一个会话、变更参数、已停止运行不能复用。等待确认计入该轮 `run_timeout_seconds`，默认 180 秒；超时需重新发起。服务重启会中断运行、销毁内存确认凭据，不自动恢复或重放待执行操作。数据库结构不变，仍只支持一个 worker。

已发出的远端请求无法撤回。网络断开、超时或停止后，如果结果未知，先查询任务、服务、文件或实例状态，再决定是否重新操作；不自动重放写入。命令/Notebook 会尽力释放专用 Kernel，若权限已撤销而清理失败，需要管理员核对返回的 Kernel 信息。关闭网页连接不会自动关闭持久终端。

### 模型部署

1. 查询模型与部署模板。
2. 调用 `preview_model_deployment`，使用服务端真实租户、模型、模板及资源信息生成部署计划附件。
3. 审核预览或下载 `deployment-plan.json`。
4. 调用 `publish_model_deployment`，只传计划 `artifact_id`。
5. 网页确认后发布保存的同一份 payload；不会重新解析成另一份模板配置。只有服务端生成的部署计划可发布，用户上传的同名 JSON 不具备计划类型。

### 取消训练任务

可用 `cancel_train_instance` 精确取消一个已验证属于任务的实例。需要取消全部时，先用 `preview_train_cancellation` 枚举任务实例，再用 `cancel_train_task` 提交计划并确认。计划固定实例 ID，不包含预览后新增的实例。分页未取全、重复或超过上限时拒绝生成“全部取消”计划。部分执行失败时停止，返回已完成列表与结果待确认的实例，避免自动重复提交。

## 文件上传、下载与保留

输入框旁的附件选择器支持单文件上传。上传成功后自动把 `artifact_id` 加入输入框，再说明用途，例如“把这个附件追加到数据集 DATASET_ID 的 /training 目录”。工具只接受附件 ID，不接受 Agent 主机上的本地文件路径。

附件按登录会话及业务隔离；相同账号的另一登录会话也不能下载旧会话附件。文件名去除路径和危险字符，文件以随机 ID 保存，不覆盖已有附件。下载响应使用 attachment、no-store、nosniff，不能作为网页脚本直接运行。

单文件限制为 20 MiB（含上传、流式下载与保存的输出附件）。数据集原 CLI 支持的格式和文件名规则继续生效。附件保存在 `runtime.state_dir/artifacts`，默认随事件保留 24 小时；过期或撤销会话的附件由每分钟清理任务删除。部署计划和取消计划也属于附件，需要在有效期内使用。此限制与 CLI 本地文件能力不同，大文件仍可直接用 CLI。

算法包及训练日志来自平台返回的下载地址。服务端只访问管理员在当前环境明确配置的 HTTPS 主机；不转发平台 Cookie/Authorization，不跟随重定向，也不把签名下载地址交给模型。

特征集导出保持 CLI 的 CSV 导出协议，支持 `zh_cn`、`en_us`；训练配置导出保持 YAML 内容，不把配置重新拼装为模型生成的文本。

## 新增环境配置

保留现有 `config.local.json` 内容，仅在需要文件下载和 Jupyter 的环境条目中增加字段：

```json
{
  "id": "dev",
  "name": "开发环境",
  "enabled": true,
  "api_endpoint": "https://PLATFORM_HOST/ai/",
  "verify_ssl": true,
  "download_hosts": ["ALGORITHM_FILE_HOST", "TRAIN_LOG_FILE_HOST"],
  "jupyter_gateways": {
    "REGION_FROM_PLATFORM": "https://JUPYTER_GATEWAY_HOST"
  }
}
```

这是单个环境的配置示例，放在已有 `environments` 数组中。`download_hosts` 填主机名，不带协议或路径；默认空列表，算法/日志外部文件下载会拒绝并提示配置。网关按平台实例 `region` 精确选择；地址必须是无路径、无凭据、无查询参数的 HTTP(S) 源站，通常使用 HTTPS。默认没有 Jupyter 网关，需要配置后才能连接。

Jupyter 连接复用平台 Web Studio 实例查询和 accessUrl 协议：校验实例在线、业务归属、区域与可信网关，解析实例 `/lab?token=...` 路由。平台登录 Cookie 不转发给 Jupyter；Jupyter Token 留在服务端，工具结果不返回连接 Token。每次操作显式传 `studio_id`，不存在多个用户共享的全局默认实例。

## 网页使用示例

- “查询算法仓里名称包含推荐的算法，列出 ID。”
- “克隆算法 ALGORITHM_ID，名称为演示算法，版本为 DEMO_VERSION。”随后核对确认卡片。
- “列出样本任务 TASK_ID 的最近执行周期和失败记录。”
- “查询训练任务 TASK_ID 的执行实例，把实例 JOB_ID 的日志下载为附件。”
- “把上传的 notebook 在 Web Studio STUDIO_ID 执行，并给出执行结果附件。”
- “在 STUDIO_ID 的 work 目录执行参数数组 `["python", "train.py", "--epochs", "1"]`。”确认卡片展示数组及目录。
- “在 STUDIO_ID 创建终端；向刚创建的终端发送 `pwd\n`；完成后关闭终端。”每个有副作用的步骤分别确认。

终端 attach 的网页等价能力是发送一次输入并读取有界输出，不是浏览器全屏 TTY。终端保持远端状态；可再次连接读取，不承诺补齐完整历史。读取窗口最多约 3 秒、输出最多 20000 字符；读取后不会自动重发之前的输入。`jupyter_exec` 更适合需要退出码与 stdout/stderr 的非交互任务。

CLI 的本地登录/退出、环境、业务选择、认证状态、保活、命令树和本地历史管理，分别由网页登录页、顶部环境/业务区域、会话管理、后台保活、工具目录和历史对话承担；不向模型开放修改服务端全局登录配置的工具。`webstudio show/login` 在 Agent 中使用显式实例查询/连接验证，没有隐式全局选中项。表格/JSON 输出选项由结构化工具结果和网页渲染承担。

## 测试与后续维护

`test_business_coverage.py` 从真实 Typer 命令树提取所有业务叶子命令，与注册表权限映射对比；新增命令遗漏映射或拼写错误都会失败。它同时验证完整目录可分页发现、每页不超过四个工具及参数不能注入账号/任意 URL。

新增测试覆盖：网页确认前不发送写请求，确认参数不可变、一次性消费、跨会话拒绝、CSRF/Origin、权限撤销/取消/拒绝；文件大小和路径限制、隔离下载、Multipart 与流式权限检查、不可伪造部署计划、附件清理；Jupyter 网关、凭据隔离、HTTP/WebSocket 权限，以及真实本机文件、命令、Notebook 和终端联调。完整测试命令和结果见 [Agent CLI 业务能力测试记录](AgentCLI业务能力测试记录.md)。

正式业务平台、真实模型服务及 Windows Edge 登录仍须按原部署验收清单联调。本地测试使用隔离数据、HTTP 测试桩和本机 Jupyter，没有对生产任务、数据或权限配置执行变更。

## CLI 与 Agent 覆盖表

以下表由当前注册表生成。多个工具可以共同覆盖一个交互式 CLI 命令；“需确认”指网页人工确认，不表示权限已放行。

当前共有 **90 个业务工具 + 1 个发现工具**，覆盖 **80 个 CLI 业务叶子命令**。其中 25 个工具需要网页确认。

| CLI 命令 | Agent 工具 | 领域 | 需确认 |
| --- | --- | --- | --- |
| `ml algorithm clone` | `clone_algorithm` | `algorithms` | 是 |
| `ml algorithm download` | `download_algorithm` | `algorithms` | 否 |
| `ml algorithm list` | `list_algorithms` | `algorithms` | 否 |
| `ml dataset detail` | `get_dataset` | `datasets` | 否 |
| `ml dataset files list` | `list_dataset_files` | `datasets` | 否 |
| `ml dataset files upload` | `upload_dataset_file` | `datasets` | 是 |
| `ml dataset list` | `list_datasets` | `datasets` | 否 |
| `ml deployment template detail` | `get_deployment_template` | `templates` | 否 |
| `ml deployment template list` | `list_deployment_templates` | `templates` | 否 |
| `ml feature-task execution list` | `list_feature_executions` | `feature_tasks` | 否 |
| `ml feature-task execution logs search` | `search_feature_logs` | `feature_tasks` | 否 |
| `ml feature-task list` | `list_feature_tasks` | `feature_tasks` | 否 |
| `ml featureset model config` | `get_model_featureset_config` | `featuresets` | 否 |
| `ml featureset model export` | `export_model_featureset` | `featuresets` | 否 |
| `ml featureset model list` | `list_model_featuresets` | `featuresets` | 否 |
| `ml featureset wide config` | `get_featureset_config` | `featuresets` | 否 |
| `ml featureset wide export` | `export_featureset` | `featuresets` | 否 |
| `ml featureset wide list` | `list_featuresets` | `featuresets` | 否 |
| `ml quality feature list` | `list_quality_features` | `quality` | 否 |
| `ml quality feature list` | `list_feature_null_rates` | `quality` | 否 |
| `ml quality wide-featureset list` | `list_quality_wide_featuresets` | `quality` | 否 |
| `ml jupyter doctor` | `jupyter_doctor` | `jupyter` | 否 |
| `ml jupyter exec` | `jupyter_exec` | `jupyter` | 是 |
| `ml jupyter files copy` | `jupyter_files_copy` | `jupyter_files` | 是 |
| `ml jupyter files delete` | `jupyter_files_delete` | `jupyter_files` | 是 |
| `ml jupyter files download` | `jupyter_files_download` | `jupyter_files` | 否 |
| `ml jupyter files list` | `jupyter_files_list` | `jupyter_files` | 否 |
| `ml jupyter files mkdir` | `jupyter_files_mkdir` | `jupyter_files` | 是 |
| `ml jupyter files move` | `jupyter_files_move` | `jupyter_files` | 是 |
| `ml jupyter files read` | `jupyter_files_read` | `jupyter_files` | 否 |
| `ml jupyter files stat` | `jupyter_files_stat` | `jupyter_files` | 否 |
| `ml jupyter files upload` | `jupyter_files_upload` | `jupyter_files` | 是 |
| `ml jupyter files write` | `jupyter_files_write` | `jupyter_files` | 是 |
| `ml jupyter notebook run` | `jupyter_notebook_run` | `jupyter` | 是 |
| `ml jupyter terminal attach` | `jupyter_terminal_attach` | `jupyter_terminals` | 是 |
| `ml jupyter terminal close` | `jupyter_terminal_stop` | `jupyter_terminals` | 是 |
| `ml jupyter terminal list` | `jupyter_terminal_list` | `jupyter_terminals` | 否 |
| `ml jupyter terminal open` | `jupyter_terminal_create` | `jupyter_terminals` | 是 |
| `ml mep config get` | `get_mep_config` | `mep` | 否 |
| `ml model deploy` | `preview_model_deployment` | `deployment` | 否 |
| `ml model deploy` | `publish_model_deployment` | `deployment` | 是 |
| `ml model detail` | `get_model` | `models` | 否 |
| `ml model list` | `list_models` | `models` | 否 |
| `ml model source` | `get_model_source` | `models` | 否 |
| `ml model source` | `get_model_training` | `models` | 否 |
| `ml mtp swanboard experiment config list` | `get_swan_config` | `swanboard` | 否 |
| `ml mtp swanboard experiment environment get` | `get_swan_environment` | `swanboard` | 否 |
| `ml mtp swanboard experiment feature list` | `list_swan_features` | `swanboard` | 否 |
| `ml mtp swanboard experiment inspect` | `inspect_swan_experiment` | `swanboard` | 否 |
| `ml mtp swanboard experiment metrics` | `get_swan_metrics` | `swanboard` | 否 |
| `ml mtp swanboard project experiment list` | `list_swan_experiments` | `swanboard` | 否 |
| `ml mtp swanboard project list` | `list_swan_projects` | `swanboard` | 否 |
| `ml mtp swanboard project namespace list` | `list_swan_namespaces` | `swanboard` | 否 |
| `ml offline experiment clone` | `clone_offline_project` | `offline` | 是 |
| `ml offline experiment clone` | `preview_offline_clone` | `offline` | 否 |
| `ml offline experiment list` | `get_offline_project` | `offline` | 否 |
| `ml offline experiment list` | `list_offline_projects` | `offline` | 否 |
| `ml offline experiment trial list` | `list_offline_trials` | `offline` | 否 |
| `ml resource template detail` | `get_resource_framework` | `resources` | 否 |
| `ml resource template detail` | `get_resource_template` | `resources` | 否 |
| `ml resource template list` | `list_resource_templates` | `resources` | 否 |
| `ml sample-task execution list` | `list_sample_executions` | `samples` | 否 |
| `ml sample-task list` | `list_sample_tasks` | `samples` | 否 |
| `ml sample-task period list` | `list_sample_periods` | `samples` | 否 |
| `ml service deployment list` | `get_service_deployments` | `services` | 否 |
| `ml service host list` | `list_service_hosts` | `services` | 否 |
| `ml service host mock` | `run_service_host_mock` | `inference` | 是 |
| `ml service list` | `list_services` | `services` | 否 |
| `ml service logs` | `list_service_log_files` | `logs` | 否 |
| `ml service logs` | `search_service_logs` | `logs` | 否 |
| `ml service mock` | `run_service_mock` | `inference` | 是 |
| `ml train cancel` | `cancel_train_instance` | `training_write` | 是 |
| `ml train cancel` | `cancel_train_task` | `training_write` | 是 |
| `ml train cancel` | `preview_train_cancellation` | `training_write` | 否 |
| `ml train clone` | `clone_train_task` | `training_write` | 是 |
| `ml train config export` | `export_train_config` | `training_files` | 否 |
| `ml train config update` | `update_train_config` | `training_write` | 是 |
| `ml train delete` | `delete_train_task` | `training_write` | 是 |
| `ml train history list` | `list_train_history` | `training` | 否 |
| `ml train history logs download` | `download_train_logs` | `training_files` | 否 |
| `ml train instance list` | `list_train_instances` | `training` | 否 |
| `ml train list` | `get_train_task` | `training` | 否 |
| `ml train list` | `list_train_tasks` | `training` | 否 |
| `ml train start` | `start_train_task` | `training_write` | 是 |
| `ml user info` | `get_current_user` | `account` | 否 |
| `ml webstudio list` | `list_webstudios` | `webstudio` | 否 |
| `ml webstudio login` | `login_webstudio` | `webstudio` | 否 |
| `ml webstudio show` | `get_webstudio` | `webstudio` | 否 |
| `ml webstudio start` | `start_webstudio` | `webstudio` | 是 |
| `ml webstudio stop` | `stop_webstudio` | `webstudio` | 是 |
