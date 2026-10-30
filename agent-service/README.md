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
| llm | OpenAI 兼容 base_url、model、api_key；Chat Completions 使用 chat_completions；支持 Responses 的服务可显式改为 responses；use_env_proxy 默认 false，模型直连，需要环境代理时改为 true |
| environments | 每个环境的 id、显示名、api_endpoint 和 enabled；示例地址必须替换；不使用的环境设为 false |
| access_control | 沿用现有 CLI 配置中的服务根 URL（例如含 /cli-permission 的部署前缀）；程序追加 /api/v1/gateway/check；gateway_token 至少 32 字符；use_env_proxy 默认 false，权限服务直连，确需环境代理时显式改为 true |
| login | 本机 msedge；持久化 Edge 登录缓存目录，路径相对本配置文件解析 |
| session | 空闲、会话及凭据期限；keepalive_enabled 默认 true，每 600 秒确认平台登录并滚动续期；失败时不延长期限 |
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

打开 http://127.0.0.1:8000 。`check` 仅检查配置及数据库结构，不宣称模型或业务联调成功。当前数据库结构版本为 2。空库初始化时创建 Agent 表，按外键依赖顺序创建业务表，最后创建版本表并核对表、字段与外键后写入版本号。重复执行会验证已有结构；未知版本、不完整结构或未初始化的非空库均拒绝操作。MySQL 使用同一连接的命名锁阻止同时初始化；启动不自动迁移。已有结构版本1支持显式升级至2，新增账号租户偏好表，保留已有业务数据；操作步骤见下文。不允许手改结构版本。

选环境 → 在本机独立 Edge 窗口完成平台登录（已有有效缓存时可复用） → 回到当前网页 → 选择可用业务 → 提问。账号来自平台 `/ai/user/info`，不会要求额外注册 Agent 账号。只有一个业务时自动选择。平台页面需提供 `ai-businessList` 目录；如果平台更新了该机制，需要适配后再上线。

浏览器登录缓存保存在 `login.profile_root/env-<环境id>`，不同环境隔离，不共享 CLI 或日常 Edge 目录。成功登录或正常停止 Agent 后保留；下次登录仍重新检查平台身份和读取业务目录。浏览器缓存仅属于运行 Agent 的本机用户，不用于云端多用户部署。

主动退出后删除该会话的服务端凭据、停止后续查询，保留涉及环境的专用 Edge 登录缓存，便于下次登录复用；历史按环境与平台用户名保留。退出 Agent 不等于注销平台所有其他浏览器的登录。切换环境先退出再重新登录；切换业务后新建对话。历史默认保留 30 天，事件 24 小时，清理每分钟执行。停止运行会中止模型流并阻止后续平台请求；已经发出的请求不能撤回，其返回值不会继续交给模型；写入或执行结果可能未知，需要先查询远端状态。

## 能力与边界

87 个业务工具覆盖当前 78 个 CLI 业务叶子命令，另有 1 个发现工具。覆盖查询、克隆、训练任务管理、部署、文件、Web Studio/Jupyter 执行及终端；25 个有副作用工具需要网页确认具体参数，之后仍检查权限。完整覆盖表、配置、使用与操作边界见 [Agent 全量 CLI 业务工具设计与使用指南](../docs/Agent全量CLI业务工具设计与使用指南.md)。

每个业务 HTTP 请求先检查会话状态与 access-service 授权，再由原 CLI Service 调用平台。businessid 来自本次登录选中的业务；用户名、环境、业务、Cookie 均由服务端确定，模型不能指定。权限服务异常或拒绝时停止查询。CLI 版本准入使用当前安装的 CLI 包版本；管理员需授权对应命令（见 app/platform.py 的 COMMANDS）。同一次工具执行以 X-CLI-Invocation-ID 关联权限请求，单个权限请求另有独立 X-Request-ID。

会话使用随机 HttpOnly/SameSite Cookie，数据库保存其 SHA-256；写接口校验 Origin 和 CSRF。Agent 的认证配置不会自动作为工具参数或会话响应返回。按当前要求，平台业务结果与文本不做字段删除、凭据值替换或 URL 参数脱敏；保留完整 ID 和接口内容，仅转换时间与数值类型。Markdown 仍经 DOMPurify 清理，CSP 禁止外部脚本。

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

## 平台与权限服务代理

平台身份验证固定直连，忽略 HTTP_PROXY、HTTPS_PROXY、ALL_PROXY；业务 Service 沿用 CLI 的显式直连 transport。无需在启动窗口临时设置 NO_PROXY。权限服务默认直连，仅在 `access_control.use_env_proxy: true` 时读取环境代理。旧 config.local.json 未填写此字段时默认为 false。

大模型客户端默认直连；需要使用环境代理访问模型时，将 `llm.use_env_proxy` 设为 `true`。该设置与权限服务独立。平台身份验证保留环境 verify_ssl 设置，权限服务始终校验证书；直连时仍加载 SSL_CERT_FILE 或 SSL_CERT_DIR 指定的企业 CA，不通过关闭 TLS 校验解决代理故障。

此次修订针对 identity_probe 的 ProxyError；更新后重新启动 Agent 并验证。若仍显示 ConnectError、ConnectTimeout 等错误，需继续检查 Python 到平台的网络及 CA 信任，不将其视为登录 Cookie 无效。

模型出现 APIConnectionError / ProxyError，且配置 NO_PROXY 后恢复时，更新后的默认直连行为即可解决，无需每次手动设置 NO_PROXY。现有 config.local.json 未包含 llm.use_env_proxy 时默认 false；如果模型只能经企业代理访问，必须显式设为 true。模型 HTTP 客户端保留 SDK 默认连接池参数、配置的超时和企业 CA，并在运行结束/失败/取消时关闭。Chat Completions 和 Responses 共用该客户端策略。此次修改无需数据库迁移。

## 查询进度与等待定位

运行中通过 SSE 返回当前阶段、累计秒数和模型请求次数。平台工具返回后会显示等待模型继续处理；模型公开输出文字实时呈现。进度每 5 秒刷新，短文本缓冲约 200 毫秒刷新。PowerShell 日志同步打印 run、stage、elapsed_seconds 和 model_requests，不包含对话正文、凭据或工具参数。

前端每 5 秒检查后台运行状态，弥补遗漏结束事件；不会重复提交问题。连接故障时仍需检查本地服务健康。进度用于定位等待发生在模型、平台工具或输出阶段，并不代表可以读取模型隐藏推理。当前没有接入厂商专属 reasoning_content 或推理摘要接口；只展示模型公开回答和可验证的执行状态。

前端进度回归测试：`node --test tests/test_chat_progress.cjs`。这次优化减少客户端输出缓冲延迟，不承诺缩短模型服务器本身的推理时间。若主要耗时集中在第二次模型请求，可根据实际测量继续调整模型、结果数量或查询范围。

## 流式输出数据库开销

文本片段先在内存聚合，约每 200ms 或累计 4096 字符批量保存；不再逐片段查询 MySQL。输出期间约每秒检查运行及会话状态，平台工具调用前后及每次业务 HTTP 请求仍执行完整检查。输出队列主动让出事件循环，保证进度、停止和超时回调可调度。

运行管理的数据库事务、进度写入和 SSE 读取在工作线程内执行，每次事务独立创建/关闭 SQLAlchemy Session；不会在线程之间共享 Session。同次运行的存储操作串行，取消时会等待正在执行的存储操作完成，以防取消后旧写入覆盖状态。已发出的数据库或平台请求不能强制撤回，存储故障本身仍可能延迟收尾。

成功运行的 `agent_runs.usage.runtime` 增加安全统计：`first_output_seconds`（运行准备开始到首个公开文本片段）、`elapsed_seconds`（最终结果保存前的累计耗时）、`db_wait_ms`（运行存储操作等待时间，含线程调度，不含 SSE 客户端读取）、`output_chunks`（收到的文本片段数）。这些用于比较程序开销，不等于纯模型推理耗时，也不包含查询正文。无需数据库迁移。

```sql
SELECT id, status,
       JSON_EXTRACT(usage, '$.runtime') AS runtime_metrics
FROM agent_runs ORDER BY created_at DESC LIMIT 1;
```

## 单次工具结果大小

`runtime.max_tool_output_chars` 按规范化后的 JSON 字符数计量，默认 20000，允许范围 1000～200000，不是 token 数量。需要提高预算时，在本机 config.local.json 的 runtime 中将该字段设置为 200000，检查配置并重启 Agent。现有本机配置不会被安装脚本或代码更新覆盖；模板仍保留 20000 的默认值。

放宽范围无需依赖重装或数据库迁移。较大结果可能增加模型上下文开销和响应耗时，需匹配实际模型及网关容量。此次仅放宽校验上限，没有实现列表摘要或部分记录保留；超过所配置限制时仍返回 truncated=true、data=null，并提示缩小查询范围。

## 自动保活与滚动会话

登录并选择业务后，默认每10分钟后台保活。普通业务请求成功会更新活动时间，因此距离上次成功平台活动不足10分钟时不额外保活。后台先验证平台身份，再经过 access-service 网关授权，请求与 CLI 相同的 `/ai/backend/mep/tenant/queryTeamList`；不调用模型或执行 CLI 命令。权限命令标识为 `ml auth ping start`。网络直连并保留企业CA。

在 config.local.json 的 session 中可以配置：

```json
"keepalive_enabled": true,
"keepalive_interval_seconds": 600,
"browser_cookie_max_age_seconds": 31536000
```

这些是 session 对象中的字段，示例片段不能单独作为完整JSON文件。省略时使用上述默认值。保活间隔必须小于 idle_timeout_seconds、absolute_timeout_seconds 和 credential_ttl_seconds。默认保留30分钟凭据/空闲窗口及8小时会话窗口，但成功活动会将这些期限从当前时刻向后滚动，不再按最初登录时间固定8小时退出。设 keepalive_enabled=false 可恢复固定超时策略。

平台明确确认成功后才续期，并合并 Set-Cookie 及更新的 csrftoken（包括身份接口响应中的轮换值）。保持网页打开时每分钟续发 Agent 的 HttpOnly/SameSite Cookie；浏览器Cookie本身默认保存1年，不会因为网页请求就假装平台登录成功。没有人工操作、甚至关闭网页时，已选择业务的会话仍会在 Agent 进程运行期间后台保活。Agent 停止时不再发请求；停机超过有效期、平台绝对登录期限、管理员注销或认证失效仍需重新登录。浏览器有自己的Cookie存储限制，不保证永久登录。

网络错误和平台5xx不删除凭据、不续期，最多每60秒重试；超过现有期限仍会正常失效。平台明确认证拒绝则删除凭据、结束会话并停止后续保活。每个会话的保活与业务调用串行处理，保存时核对会话状态和原凭据快照，退出/重登后的在途返回不能恢复或覆盖凭据。主动退出保留专用Edge登录缓存；后台轮换的Cookie保存于服务端，未在关闭的Edge配置目录中同步写入。

保活任务生命周期绑定本地单进程服务，重启后从仍有效的数据库会话恢复调度，不对匿名、未选业务或已退出会话发送保活。相关日志仅打印会话ID、成功/失败状态和错误分类，不输出Cookie或密钥。本次不新增表或字段，无需数据库迁移。

## 模型文字和工具块的展示顺序

同一轮回答按事件顺序显示独立片段：模型文字 → 工具块 → 后续模型文字，支持多次工具调用。连续的文本片段只在同一文字块内合并，工具块出现后会开始新的文字块；结束事件不再把整轮内容覆盖为一个Markdown块。

展示结构保存在既有 agent_runs.usage.presentation JSON 中，历史消息、运行完成事件和状态恢复使用同一结构。即使24小时后清理SSE事件，新的历史回答仍保留片段顺序。旧回答优先从尚存事件重建；若旧事件已经清理且没有展示快照，只能显示原来保存的回答，无法恢复丢失的过程文字。此次不新增数据库字段，无需迁移。

前端顺序测试：`node --test tests/test_message_parts.cjs tests/test_chat_progress.cjs`。本次仅调整公开文字和工具状态的呈现，不改变模型的业务工具或历史上下文。

## 记住上次租户及搜索

每次成功选择租户/团队后，按平台账号（账号本身按环境隔离）保存偏好。重新登录时优先从本次新目录中解析同一租户/团队并重新校验gateway权限，通过后直接进入对话；目录已移除或权限不可用时退回选择弹窗。退出只销毁登录凭据，不删除租户偏好。既有账号升级后若尚无偏好，会尝试最近对话所用业务并重新检查目录和权限；首次使用且没有偏好和历史对话时，仍按可用目录选择，只有一个条目时可自动进入。

选择弹窗支持按租户、团队、部门名称或ID过滤，英文不区分大小写，多个词用空格分隔。显示匹配数，无结果时禁用确认。租户与团队即使共用businessId，也通过独立selection_key选择，防止恢复错误条目。

### 结构版本1升级至2

本次需要显式迁移。先停止Agent，使用现有数据库备份工具备份整个Agent库及config.local.json，并确认备份可恢复，再在agent-service目录执行：

```powershell
.\.venv\Scripts\python.exe -m app.manage migrate --config config.local.json
.\.venv\Scripts\python.exe -m app.manage check --config config.local.json
.\scripts\start.ps1
```

迁移只增加agent_user_preferences表，包含用户外键、最近选择的业务JSON及更新时间；不修改或删除原有用户、会话、凭据和对话。完整核对原有结构及新增表后，程序将版本1更新为2。初次空库安装直接创建版本2。迁移不接触access-service数据库。

MySQL DDL有隐式提交：中断后可能已建偏好表但仍为版本1，再次执行会核对表结构后继续；不覆盖已有数据。没有降级迁移，旧Agent代码要求结构1，不能直接回滚代码使用结构2。若必须回滚，应停止Agent并恢复升级前数据库和配置备份；恢复会丢失备份后的新增数据。禁止手动修改agent_schema_version或删除表伪造回滚。

当前开发环境已验证SQLite上的升级、幂等、DDL中断重试和原用户保留；真实MySQL及Windows界面验收仍待执行。应先更新完整代码，再执行迁移，避免在Windows仅更新部分文件造成结构与代码不一致。

## 历史对话侧栏

浅色侧栏支持按标题关键词搜索全部历史，按北京时间分为今天、昨天和更早。对话输入框仅支持文字输入。行尾菜单可重命名、置顶、归档或删除；删除前需确认，确认后会永久删除服务端的对话、全部消息、运行记录和工具调用记录，无法恢复。正在执行的对话需先停止后再删除。删除当前对话后返回新对话页。重命名保存在服务端。置顶与归档仅保存在当前浏览器，按账号和环境隔离，不会跨设备同步；清除浏览器数据会清除这些整理偏好。点击“已归档”查看并恢复归档对话，归档不会删除消息。搜索只匹配标题，不检索消息正文。

对话中，用户消息下方显示服务端接收时间，Agent回复下方显示回复保存时间，均按北京时间（UTC+8）展示为 `YYYY-MM-DD HH:mm:ss`。历史记录与实时消息使用相同的服务端时间，刷新或重新打开不会变成当前时间；回复生成中待保存后显示时间。租户/团队选择弹窗只提供选择与确认，退出登录仍从侧栏账号区操作。

## 工具渐进式加载

87 个业务工具按 23 个领域渐进加载，一次最多提供四个候选，支持 offset 翻页。明确的问题先加载相关领域的前四个工具；缺少工具时，模型通过 `discover_tools` 查找，后端在下一次模型请求中提供新增工具的完整参数定义。网页以“查找业务工具”显示这个过程。

每次用户消息创建独立加载集合，跨用户和跨轮次不共享。发现只读取静态目录，不授予平台访问权限；业务查询仍沿用现有逐请求权限检查。未知搜索会返回领域目录，工具发现和已有业务调用共同受总预算限制。

runtime 新增可选配置 `max_discovery_calls`（默认 4）和 `max_loaded_tools`（默认 16，不含发现入口）；旧配置无需修改。没有新增 CLI 命令或数据库结构；新增的 Agent 写工具使用网页确认。详细行为、限制及验证入口见 [Agent 工具渐进式加载说明](../docs/Agent工具渐进式加载说明.md)。

本次业务扩展的完整用例与执行结果见 [Agent CLI 业务能力测试记录](../docs/AgentCLI业务能力测试记录.md)。
