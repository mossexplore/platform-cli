# WiseRec Agent 本地工作台

基于 OpenAI Agents SDK、FastAPI、MySQL 和 SSE 的正式应用源码。静态页面由 FastAPI 同源托管，无需 Node 构建或 CDN。采用方案 1 的蓝白工作台，具有环境登录页、业务选择、历史对话、流式回答、工具执行状态、停止和退出登录。

**本次交付尚未完成真实环境验收**：没有模型、MySQL、平台或 access-service 配置。自动化测试使用可注入的 HTTP 测试桩与 SQLite；生产启动路径必须连接 MySQL 和真实模型，不会回退为演示数据。Windows 与真实 Edge 登录需按下方验收清单验证。

## 环境与安装

需要完整检出本仓库、Python 3.12、已安装的 Microsoft Edge，以及可访问的 MySQL 8。CLI Service 从仓库根目录以 editable 包安装；不执行 CLI 子进程，不读取用户 CLI 的 config.json、business.json 或登录缓存。Agent 仅支持本机单进程、单 worker、回环地址访问。Chrome 打开 Agent 页面，Edge 完成登录，两者无需共享 Cookie。

Windows PowerShell，在仓库根目录执行：

```powershell
.\agent-service\scripts\setup.ps1
```

如果企业策略限制 PowerShell 脚本，请在获准的终端中逐行执行脚本内的安装命令，不要求修改执行策略。安装脚本不安装 Edge，不覆盖已有 config.local.json。

macOS 开发环境：

```bash
bash agent-service/scripts/setup.sh
```

依赖由 requirements.lock 固定（同时包含 CLI 和 Agent 依赖）。升级锁文件必须重新执行 SDK 流式工具调用测试。仓库根 CLI 的发布版本不随 Agent 增加独立命令或发布包。

## 配置

编辑 `agent-service/config.local.json`，模板为 `config.example.json`：

| 区段 | 填写说明 |
| --- | --- |
| server | 默认 127.0.0.1:8000，workers 固定为 1；不要改为公网监听 |
| database | 独立 Agent MySQL 数据库、用户名、密码，字符集 utf8mb4 |
| llm | OpenAI 兼容 base_url、model、api_key；Chat Completions 使用 chat_completions；支持 Responses 的服务可显式改为 responses |
| environments | 每个环境的 id、显示名、api_endpoint 和 enabled；示例地址必须替换；不使用的环境设为 false |
| access_control | 沿用现有 CLI 配置中的服务根 URL（例如含 /cli-permission 的部署前缀）；程序追加 /api/v1/gateway/check；gateway_token 至少 32 字符 |
| login | 本机 msedge；持久化 Edge 登录缓存目录，路径相对本配置文件解析 |
| session | 空闲、绝对和平台凭据过期时间；凭据默认 30 分钟过期，届时重新登录 |
| runtime | 最大轮数、调用数、分页、输出与日志行数、超时、事件及历史保留期 |

模型必须支持流式响应及 function calling。仅提供普通文本聊天的兼容服务不能满足工具查询。默认禁用 Agents tracing，不发送 tracing 数据。TLS 默认校验；企业 CA 应加入本机信任链。

可选环境变量覆盖文件中的秘密：`WISEREC_AGENT_LLM_API_KEY`、`WISEREC_AGENT_DB_PASSWORD`、`WISEREC_AGENT_GATEWAY_TOKEN`。`WISEREC_AGENT_CONFIG` 可指定配置文件。首版按已确认方案明文保存平台 Cookie/csrftoken；配置和数据库应仅供本机授权用户访问。真实配置、运行状态和数据库不提交 Git。

## 初始化与启动

先由数据库管理员创建独立空库，为配置的账号授予该库运行权限。初始化时需建表权限；不要连接现有 access-service 数据库执行迁移。

```sql
CREATE DATABASE IF NOT EXISTS `wiserec_agent`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

所有 Agent 表显式指定 InnoDB、utf8mb4、utf8mb4_bin，字符串外键两端一致，不依赖数据库默认排序规则。若此前按旧说明创建了空库，可执行 `ALTER DATABASE wiserec_agent CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;` 统一默认值；这不会修改已有表。不要删除有数据的表或手动写入结构版本。

Windows，在 agent-service 目录执行：

```powershell
.\.venv\Scripts\python.exe -m app.manage migrate --config config.local.json
.\.venv\Scripts\python.exe -m app.manage check --config config.local.json
.\scripts\start.ps1
```

macOS，在 agent-service 目录执行：

```bash
.venv/bin/python -m app.manage migrate --config config.local.json
.venv/bin/python -m app.manage check --config config.local.json
bash scripts/start.sh
```

打开 http://127.0.0.1:8000 。`check` 仅检查配置及数据库结构，不宣称模型或业务联调成功。迁移为显式初始版本 1：仅在空库创建 Agent 表，按外键依赖顺序创建业务表，最后创建版本表并核对表、字段与外键后写入版本号。重复执行会验证已有结构；未知版本、不完整结构或未初始化的非空库均拒绝操作。MySQL 使用同一连接的命名锁阻止同时初始化；启动不自动迁移。未来结构变化须新增有序迁移后再升级，不允许手改结构版本。

选环境 → 在本机独立 Edge 窗口完成平台登录（已有有效缓存时可复用） → 回到当前网页 → 选择可用业务 → 提问。账号来自平台 `/ai/user/info`，不会要求额外注册 Agent 账号。只有一个业务时自动选择。平台页面需提供 `ai-businessList` 目录；如果平台更新了该机制，需要适配后再上线。

浏览器登录缓存保存在 `login.profile_root/env-<环境id>`，不同环境隔离，不共享 CLI 或日常 Edge 目录。成功登录或正常停止 Agent 后保留；下次登录仍重新检查平台身份和读取业务目录。浏览器缓存仅属于运行 Agent 的本机用户，不用于云端多用户部署。

主动退出后删除该会话的服务端凭据、停止后续查询，并清除涉及环境的专用 Edge 缓存；历史按环境与平台用户名保留。Windows 文件占用时有限重试；若仍失败，页面提示未清理成功，并保留待清理标记，下一次登录先完成清理再启动 Edge。退出 Agent 不等于注销平台所有其他浏览器的登录。切换环境先退出再重新登录；切换业务后新建对话。历史默认保留 30 天，事件 24 小时，清理每分钟执行。停止运行会中止模型流并阻止后续平台请求；已经发出的只读 HTTP 请求不能撤回，其返回值不会继续交给模型。

## 能力与边界

13 个显式只读工具：模型列表、详情、来源、关联训练任务；训练任务列表/查找、实例、历史；服务列表、主机、部署状态、日志文件及日志检索。服务日志使用实际接口支持的尾部行数与关键词，不伪造按时间段查询能力。分页、日志、模型上下文均有上限，超限要求缩小范围。

每个业务 HTTP 请求先检查会话状态与 access-service 授权，再由原 CLI Service 调用平台。businessid 来自本次登录选中的业务；用户名、环境、业务、Cookie 均由服务端确定，模型不能指定。权限服务异常或拒绝时停止查询。CLI 版本准入使用当前安装的 CLI 包版本；管理员需授权对应命令（见 app/platform.py 的 COMMANDS）。同一次工具执行以 X-CLI-Invocation-ID 关联权限请求，单个权限请求另有独立 X-Request-ID。

会话使用随机 HttpOnly/SameSite Cookie，数据库保存其 SHA-256；写接口校验 Origin 和 CSRF。平台凭据不返回网页，不放入模型上下文。工具结果先清理敏感字段、凭据值和 URL 参数；Markdown 经 DOMPurify 清理，CSP 禁止外部脚本。非通用 DLP：业务日志中的未知格式秘密仍需平台在源头脱敏。

当前实现针对本地使用，不能直接当作云端多人生产部署：远程浏览器认证代理、HTTPS、密钥加密/轮换、集中任务队列、分布式锁、审计留存与容量测试须在下一阶段设计。不要简单改监听地址暴露此服务。

## 开发与验证

```bash
# 在 agent-service 目录，用本服务的 Python 3.12 环境
.venv/bin/python -m pytest tests -q
```

Windows 等价命令将 `.venv/bin/python` 换成 `.venv\Scripts\python.exe`。测试包含真实 SDK 的 Chat Completions 流式工具闭环（模型 HTTP 响应为测试桩）、Service 请求与权限链路、SSE 重放、幂等、会话隔离、取消、过期、退出及序列化。

真实联调放行前逐项执行：

1. Windows Python 3.12 按锁文件安装；Chrome 页面触发 Edge 登录，取消、关闭 Edge、超时都能恢复；重复登录不会复用旧凭据。
2. 在 MySQL 上迁移、重启、登录、查询、退出，检查凭据已删除；验证中文、长日志/回答和历史持久化。
3. 配置真实模型，验证选定 api_mode 的工具调用与流式输出；Responses 模式必须另做真实兼容性验证。
4. 三类业务各执行实际查询：模型详情/来源、训练实例/历史、服务主机/部署/日志；对照平台验证完整 ID、业务、北京时间与分页。
5. access-service 授权允许/拒绝、版本准入失败、服务不可用及运行中撤权；确认拒绝后没有新的平台请求，权限日志可按 invocation 关联。
6. 两个不同平台账号与环境验证隔离；运行中停止、退出、断网恢复、刷新、服务重启及凭据过期。

本次结果与视觉证据见 `design-qa.md`。源码职责按配置/持久化/会话/登录/平台工具/运行/SSE/前端分离；模块均控制在 500 行以内，供应商文件除外。

## 登录故障定位

平台页面能登录不代表后端已完成验证与落库。失败提示包含阶段和异常类型：`business_catalog` 为业务目录解析，`browser_close` 为浏览器关闭，`identity_probe` 为 Python 后端再次访问平台，`credential_save` 为 MySQL 保存，`profile_cleanup` 为本机浏览器缓存清理。MySQL 异常同时显示数字错误码；日志不输出原始异常文本、Cookie、Token、SQL 参数或完整 URL。

请向维护者提供页面阶段、异常类型和错误编号，不提交配置或浏览器缓存。`identity_probe / ConnectError` 需核对 Python 进程的网络、代理与企业 CA 信任；不要仅因 Edge 可访问就关闭 TLS 校验。`credential_save` 应检查数据库字段/权限与返回身份字段。缓存并不能替代这两步校验。当前真实 Windows 登录故障尚待新诊断信息确认根因。
