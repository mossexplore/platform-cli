# Agent 工具渐进式加载说明

## 范围

当前提供 87 个业务工具（覆盖全部 78 个 CLI 业务叶子命令）和 1 个发现工具，支持查询、写入、文件与远端执行。25 个有副作用工具需要网页确认并继续校验权限。完整能力、配置和覆盖表见 [Agent 全量 CLI 业务工具设计与使用指南](Agent全量CLI业务工具设计与使用指南.md)。正式 CLI 命令和版本保持不变。

这里的“加载”指将工具的完整参数 Schema 放入下一次模型请求。服务端仍持有全部工具实现，不需要运行时导入模型指定的模块，也不依赖 MCP。

## 用户体验

- 提问“查询模型”：首个模型请求只包含模型领域的 4 个工具及发现入口。
- 提问“查询训练任务”：先加载训练领域。
- 继续分析需要日志时，模型调用 `discover_tools`，后端返回匹配工具；SDK 在下一次模型请求中发送新增工具定义。
- 无法从问题判断领域时，只提供发现入口。未知搜索返回领域目录，不等同于系统没有该能力。
- 页面以“查找业务工具”显示发现过程，复用已有工具执行事件和历史展示。
- 每条用户消息启动新的运行，重新选择初始领域。旧对话仍可作为语义上下文，但旧工具加载集合不会自动继承。

## 基础查询领域示例

| domain | 初始工具 |
| --- | --- |
| models | list_models、get_model、get_model_source、get_model_training |
| training | list_train_tasks、get_train_task、list_train_instances、list_train_history |
| services | list_services、list_service_hosts、get_service_deployments |
| logs | list_service_log_files、search_service_logs |

完整目录包含 23 个领域，空 query 可查询全部；领域超过四个工具时使用 offset 翻页。初始路由使用当前消息中的中英文关键词计分，选择一个匹配最多的领域；同分按目录顺序选择。它是可纠正的启发式路由，不承诺识别所有自然语言意图。跨领域问题通过发现入口补充。

`discover_tools` 支持：

```json
{"domain": "training"}
```

```json
{"query": "查询服务主机"}
```

```json
{"query": "list_train_history"}
```

显式 domain 优先；query 为精确工具名时可只加载该工具，否则按关键词匹配一个领域。每次最多返回一个领域的四个工具，next_offset 给出下一页位置；无匹配返回领域名称和简短说明。发现结果只包含目录信息，不包含平台数据、Cookie、账号凭据或任意 URL。

## 配置与限制

`agent-service/config.local.json` 的 runtime 可增加：

```json
{
  "max_discovery_calls": 4,
  "max_loaded_tools": 16
}
```

以上是 runtime 内的字段片段，不是完整配置。旧配置无需修改，缺省值自动生效。

| 配置 | 默认值 | 范围及行为 |
| --- | --- | --- |
| max_discovery_calls | 4 | 1–10；每次运行的发现次数上限，超出后返回限制原因并记录失败事件 |
| max_loaded_tools | 16 | 4–100；本轮可见业务工具上限，不含 discover_tools |
| max_tool_calls | 20 | 既有总工具调用预算，发现调用也占用预算 |
| max_turns | 12 | 既有 SDK 模型轮次上限，发现同样消耗模型轮次 |

已经加载的工具在本轮保留。若本页新增工具会超过工具上限，本次不加载任何新工具，不淘汰旧工具；模型可按精确工具名加载仍可容纳的单个工具，或让用户拆分问题。上限均来自服务端配置，不能由模型参数修改。

发现会增加模型往返；当前实现减少不相关工具定义，不承诺所有查询的耗时和总 Token 都下降。后续应结合真实模型、实际问题和已记录使用量评估。

## 执行与权限

工具定义来自固定注册表和 Pydantic 参数 Schema。SDK 的 `FunctionTool.is_enabled` 在每次模型请求前根据当前运行的加载集合筛选，未加载工具不发送给模型；工具回调还会再次检查可见性。

加载集合在 `AgentEngine.run` 内新建，不写入进程全局变量、不复用其他用户的集合、不依据历史消息恢复。模型不能通过发现接口传入代码、平台请求头或外部接口地址。

发现入口只读静态目录，通过 RunManager 检查运行/会话状态、控制调用预算并记录 ToolCall 和 SSE 事件；它不调用权限服务获取放行，也不返回业务数据。写入和执行工具另需网页确认，网关使用对应 CLI 命令。发现不是授权：实际业务调用继续经过平台身份复核、业务目录校验、每次业务 HTTP 请求的权限网关检查，以及现有资源归属校验。撤销权限后，即使工具已经加载，业务请求仍须被拒绝。

## 代码位置

| 文件 | 职责 |
| --- | --- |
| agent-service/app/tool_catalog.py | 领域目录、发现参数、关键词路由、单次运行加载集合 |
| agent-service/app/tools.py | 工具 Schema、动态可见性及发现回调 |
| agent-service/app/agent_engine.py | 每次运行创建独立集合，接入 SDK |
| agent-service/app/runs.py | 发现调用的预算、会话检查、审计与执行事件 |
| agent-service/app/settings.py | 配置默认值与范围校验 |

新增工具时需同时维护业务注册表、所属领域、平台分发逻辑及测试。发现接口不会自动开放未注册的 CLI 命令。

## 验证

从 agent-service 目录，在安装了 requirements.lock 的 Python 环境执行：

```bash
python -m pytest tests -q
node --test tests/*.cjs
```

新增用例：

- `test_tool_loading.py`：领域选择、未知问题、目录覆盖、参数拒绝、加载上限、直接调用未加载工具的拒绝，以及不同运行的隔离。
- `test_discovery_sdk.py`：使用真实锁定 SDK 和模拟模型 HTTP 服务，分别验证 Chat Completions 与 Responses 实际发出的工具定义；验证跨领域发现后下一次请求变化，以及带历史的新运行不继承工具集合。
- `test_discovery_runs.py`：发现事件与数据库审计、发现次数及总预算、发现后撤销授权阻断平台数据请求。

以上自动化验证不代表已完成真实模型、生产 MySQL、平台或 Windows Edge 登录联调。本次无需数据库迁移，不发布正式 Release。

当前全量验证结果见 [Agent CLI 业务能力测试记录](AgentCLI业务能力测试记录.md)。
