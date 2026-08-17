# WiseMLOps Python CLI 需求设计说明书

## 1. 文档信息

| 项目 | 内容 |
| --- | --- |
| 项目名称 | WiseMLOps Python CLI |
| Python 包名 | `wisemlops-cli` |
| 命令名 | `ml` |
| 当前代码版本 | `0.3.18` |
| 目标平台 | Windows 优先，兼容 macOS/Linux 的基础路径逻辑 |
| 文档整理日期 | 2026-08-16 |
| 代码仓库 | `mossexplore/platform-cli` |

本文档根据项目全部历史讨论、已提交代码和当前仓库状态整理，用于需求备份、后续开发和验收。为避免把中途讨论当成最终实现，需求使用以下状态：

- **已实现**：当前 `main` 分支已有对应代码。
- **待实现**：需求已明确，但当前代码尚未完成。
- **规划中**：已有设计方向，仍缺少接口契约或实现排期。
- **已废弃**：被后续需求替代，不再作为当前行为。

## 2. 项目背景与目标

WiseMLOps Web 管理台已有大量 Java 后端接口，需要在现有 Python 项目上持续封装为 CLI，降低人工登录页面和重复操作的成本。

核心目标：

1. 使用 `ml` 作为统一命令入口。
2. 支持 dev、test 等多个环境并可快速切换。
3. 使用 Microsoft Edge 完成 Web 登录，复用持久会话以减少验证码输入。
4. 自动捕获 Cookie、独立请求头 `csrftoken` 和用户信息。
5. 对短期认证信息进行本地缓存、过期判断和自动刷新。
6. 从浏览器 `localStorage` 获取部门、租户和团队目录，允许用户选择业务上下文。
7. 通过统一 HTTP 客户端封装 Java 接口，集中处理认证、超时、重试、SSL 和错误。
8. 使用 Python Wheel 分发，不要求生成 exe。

非目标：

- 不使用 Playwright 自带 Chromium 作为默认浏览器。
- 暂不构建 exe 安装包。
- 不在命令模块中重复拼装 Cookie、CSRF Token 或基础 URL。
- 不兼容旧命令 `wo`、`profile`、`context`。

## 3. 总体架构

```text
Typer 命令层
    ↓ 参数解析、交互、结果展示
Service 业务适配层
    ↓ 领域接口与请求体
PlatformClient 统一 HTTP 层
    ↓ Cookie / csrftoken / ai-businessId / 重试 / SSL
WiseMLOps Java API

登录流程：
AuthManager → Playwright → 持久化 Microsoft Edge Profile
                         ↓
              /ai/user/info + localStorage
                         ↓
             Credentials / BusinessStore
```

代码职责：

| 模块 | 职责 |
| --- | --- |
| `commands/` | Typer 命令、参数、交互提示和输出 |
| `services/` | 按业务领域封装后端接口 |
| `client.py` | 统一 HTTPX 客户端和认证请求头 |
| `auth.py` | Edge 登录、认证捕获、认证刷新 |
| `business.py` | 部门/租户/团队解析、选择和持久化 |
| `config.py` | 配置安装、读取、校验和环境切换 |
| `credentials.py` | 认证信息持久化 |
| `runtime.py` | 运行时依赖组合和认证失败重试 |

新增 Java 接口时，优先按以下路径扩展：

```text
commands/<domain>.py → services/<domain>.py → PlatformClient
```

如果后端能够提供 OpenAPI，可将生成客户端放入独立的 `generated/` 目录，由 Service 层适配，命令层保持稳定。

## 4. 命令与命名规范

### 4.1 命名演进

| 旧名称 | 当前名称 | 状态 |
| --- | --- | --- |
| `wo` | `ml` | `wo` 已完全废弃 |
| `ml profile` | `ml env` | `profile` 命令已废弃 |
| `ml context` | `ml business` | `context` 命令已废弃 |

CLI 产品描述统一为：

> `ml` 是 WiseMLOps平台的 Python 命令行客户端。

### 4.2 当前命令树

```text
ml
├── login [--show-secrets]
├── logout [--all] [--forget-browser]
├── auth
│   └── status
├── env
│   ├── list
│   ├── show
│   └── use <name>
├── business
│   ├── list
│   ├── show
│   ├── use [--department ID] [--tenant ID] [--team ID_OR_KEY]
│   └── refresh
├── user
│   └── info [--output table|json]
├── mep
│   └── config
│       └── get [key] [--output table|json]
└── offline
    └── experiment
        └── list [查询条件] [--output table|json]
```

全局参数：

```text
--config <path>      指定 config.json
ML_CONFIG=<path>     通过环境变量指定 config.json
--version            输出 ml 当前版本
```

## 5. 配置设计

### 5.1 默认配置

项目根目录 `config.json` 是默认配置的唯一源码：

```json
{
  "current": "dev",
  "api": {
    "timeout": 30000,
    "retry_times": 3,
    "verify_ssl": true
  },
  "auth": {
    "expires_in_seconds": 1800
  },
  "browser": {
    "channel": "msedge",
    "session_probe_timeout": 5000,
    "login_timeout": 300000
  },
  "profiles": [
    {
      "name": "test",
      "api_endpoint": "https://console-test.cloudtest.cn/dashboard",
      "output_format": "table"
    },
    {
      "name": "dev",
      "api_endpoint": "https://console-dev.cloudtest.cn/dashboard",
      "output_format": "table"
    }
  ]
}
```

字段说明：

| 字段 | 说明 |
| --- | --- |
| `current` | 当前使用的环境，必须匹配 `profiles[].name` |
| `api.timeout` | HTTP/页面操作超时，毫秒 |
| `api.retry_times` | HTTP 传输重试次数 |
| `api.verify_ssl` | 所有环境默认 SSL 证书校验开关 |
| `auth.expires_in_seconds` | CLI 认证缓存有效期，默认 1800 秒 |
| `browser.channel` | Edge 通道，默认 `msedge` |
| `browser.session_probe_timeout` | 探测已有 Edge 会话的超时，毫秒 |
| `browser.login_timeout` | 等待用户完成登录的超时，毫秒 |
| `profile.api_endpoint` | 管理台入口地址 |
| `profile.output_format` | 默认输出格式，`table` 或 `json` |
| `profile.verify_ssl` | 可选；覆盖当前环境的全局 SSL 设置 |

`api_endpoint` 的基础地址通过 scheme + host 计算，即：

```text
https://console-dev.cloudtest.cn/dashboard
→ https://console-dev.cloudtest.cn
```

### 5.2 配置安装与优先级

构建 Wheel 时，根目录 `config.json` 被复制进安装包。安装新版本或默认配置内容变化后，首次执行 CLI 会强制覆盖用户目录的 `config.json`；同一版本后续执行不重复覆盖。

配置选择优先级：

1. 命令行 `--config`。
2. 环境变量 `ML_CONFIG`。
3. 当前工作目录的 `config.json`。
4. 用户配置目录的 `config.json`。

注意：当前“新版本首次运行强制覆盖”会覆盖用户自定义环境，升级前需要备份。该行为是历史明确需求，不属于安装故障。

### 5.3 SSL 配置

全局默认开启证书校验。可信内部环境可以单独关闭：

```json
{
  "name": "internal",
  "api_endpoint": "https://10.0.0.1/dashboard",
  "output_format": "table",
  "verify_ssl": false
}
```

IP address mismatch 表示访问 IP 与证书的域名/SAN 不匹配。`verify_ssl: false` 只应用于显式配置的环境，且仅建议用于可信内部网络。

## 6. Microsoft Edge 登录与认证

### 6.1 Playwright 依赖检查

如果没有安装 Playwright，返回明确错误：

```text
未安装 playwright，请运行: py -m pip install playwright
```

当前使用 Windows 自带 Microsoft Edge，不需要执行 `playwright install chromium`。

### 6.2 持久化 Edge Profile

每个环境使用独立的持久化 Edge Profile：

```text
<用户配置目录>/ml/browser-profiles/profile-dev
<用户配置目录>/ml/browser-profiles/profile-test
```

`profile-` 后的环境名需要进行安全 URL 编码。也可以通过 `browser.profile_root` 配置根目录。

优点：

- 可复用登录态，减少重复验证码。
- 环境间 Cookie、Local Storage 和浏览器状态隔离。
- 使用系统 Edge，与用户平台兼容性更接近。

注意：持久化 Profile 不能绕过平台安全策略。若平台会话过期、风控触发或验证码策略强制执行，仍需用户登录。

### 6.3 登录成功自动判断

登录流程不再要求用户按回车。页面提示为：

```text
正在等待登录成功...
```

Playwright 监听目标请求：

```text
GET <base_url>/ai/user/info
```

请求头捕获规则：

- Cookie 从浏览器上下文完整读取，不能截断。
- `csrftoken` 是独立请求头，不从 Cookie 中解析。
- 兼容大小写和 `csrftoken`、`x-csrftoken`、`x-csrf-token` 名称。

为避免页面跳转后 `Network.getResponseBody` 不可用，不依赖已导航响应的 `response.json()`；捕获认证请求头后，使用浏览器上下文请求客户端再次调用 `/ai/user/info`，立即读取响应文本并解析 JSON。

### 6.4 用户信息成功判定

接口响应必须包含：

```json
{
  "result": {
    "code": 0,
    "des": "success",
    "username": "123456",
    "department": "技术部",
    "cnName": "张三"
  }
}
```

仅当 `result.code == 0` 时视为登录成功。成功后打印：

```text
账号: 123456
中文名: 张三
部门: 技术部
租户: <ai-businessId>
```

默认不打印敏感值。`ml login --show-secrets` 才额外打印完整 Cookie 和 CSRF Token。

### 6.5 Local Storage 读取

登录成功后，从当前页面读取：

```javascript
localStorage.getItem('ai-businessId')
localStorage.getItem('ai-businessList')
```

- `ai-businessId`：当前浏览器租户/团队业务标识。
- `ai-businessList`：部门、租户和团队原始目录。

这些值由对应环境的持久化 Edge Profile 保存。Chromium/Edge 的 Local Storage 底层通常位于该 Profile 的 `Local Storage/leveldb`，属于浏览器内部格式，不应由 CLI 直接解析文件；必须通过 Playwright 页面上下文读取。

### 6.6 Edge 关闭策略

最终有效需求：

- 登录并成功保存认证信息后，自动关闭 Edge。
- 登录失败时保留 Edge 打开，显示错误，让用户检查页面；用户关闭 Edge 后流程结束。

历史上“成功后保持 Edge 直到用户主动关闭”的设计已被后续需求替代，属于已废弃行为。

## 7. 认证缓存与自动刷新

### 7.1 认证字段

认证记录包含：

```text
profile
cookie
csrftoken
username
cn_name
department
business_id
acquired_at
expires_at
```

Cookie 和 CSRF Token 属于敏感信息，本地文件应尽可能使用仅当前用户可读写的权限，不写入项目配置，不提交 Git，不在默认日志中显示。

### 7.2 有效期与刷新

- 默认有效期 30 分钟，即 `1800` 秒。
- 每次业务请求前检查 `expires_at`。
- 未登录或过期时，自动打开当前环境的持久 Edge Profile。
- 先探测持久会话；会话仍有效时无需验证码。
- 服务端返回 401、403、419、440 或认证重定向时，自动刷新认证并重试一次。
- 第二次仍失败则返回认证错误，禁止无限重试。

### 7.3 退出登录

```text
ml logout
ml logout --all
ml logout --forget-browser
ml logout --all --forget-browser
```

- 普通退出只删除 CLI 短期认证缓存，保留 Edge 持久会话。
- `--forget-browser` 删除持久 Edge Profile，后续可能重新触发验证码。

## 8. 部门、租户与团队业务上下文

### 8.1 原始目录结构

`ai-businessList` 是数组，每条顶层记录表示一个租户（服务），并携带部门信息和 `teamList`。

三层目录：

```text
部门
└── 租户（服务）
    ├── 租户级操作范围
    └── 团队
```

用户必须选择租户级或团队级，不能只选择部门。

### 8.2 字段映射

| 层级/字段 | 来源与规则 |
| --- | --- |
| 部门名称 | `settleTenantName.cn` → `settleTenantName.en` → 顶层 `cn` |
| 部门分组键 | 与最终部门名称相同 |
| 租户 ID | 顶层 `value` |
| 租户名称 | 顶层 `cn` → 顶层 `en` → `value` |
| 服务 ID | `serviceIdList[].serviceId` |
| 团队 ID | `teamList[].teamId` |
| 团队名称 | `teamList[].cn` → `teamList[].name.cn/en` → 团队 ID |
| 团队 key | `teamList[].key` |
| 团队状态 | `teamList[].teamStatus` |
| 团队业务 ID | `teamList[].businessId` |

明确约束：

- 部门名称和分组逻辑绝不使用 `settleTenant`。
- `settleTenantName` 本身存在，但其 `cn`、`en` 都可能为空。
- `softwareUnitEntity` 可包含额外字段，解析器只读取需要字段，其他字段忽略，不影响功能。
- 仅 `teamStatus == "available"` 的团队可选，其他状态全部禁选。

### 8.3 业务选择值

- 选择租户级时，请求使用租户 `value` 作为 `businessId`。
- 选择团队级时，请求使用 `teamList[].businessId` 作为 `businessId`。
- `business.json` 使用驼峰字段 `businessId`。
- 已删除旧字段 `effective_business_id`。
- 不迁移旧 schema，登录或刷新时根据浏览器缓存重建。

### 8.4 `ml business use` 交互展示

部门列表只显示部门名称：

```text
请选择部门：
  1. 云平台部
```

租户列表只显示租户名称：

```text
请选择租户：
  1. 测试MEP平台
```

团队列表：

```text
请选择团队：
  1. 测试MEP平台（租户级）
  2. 可用团队
  3. 禁用团队（禁选）
```

样式规则：

- `租户名称（租户级）`：整行加粗蓝色。
- 可选团队：终端默认颜色，只显示团队中文名。
- 禁选团队：显示 `团队中文名（禁选）`，整行红色。
- 关闭 Rich 自动高亮，避免名称中的数字或特殊字符被自动显示为粉色等颜色。
- 团队列表不展示团队 ID、key、owner 或原始状态值。

如果用户输入禁选团队对应的序号，必须返回不可选择错误，不写入选择结果。

### 8.5 选择成功后的输出

最终界面只显示以下五项，中文括注也必须保留：

```text
type（选择维度）
department（部门）
tenant（租户）
team（团队）
businessId
```

租户级选择没有团队时，`team（团队）` 显示 `-`。不显示 `department_id`、`tenant_id`、`team_id`，但底层持久化内容保持完整。

### 8.6 目录刷新与失效

- `ml login` 成功时读取并缓存 `ai-businessList`。
- `ml business refresh` 打开当前环境 Edge Profile，刷新目录后自动关闭。
- 目录绑定登录账号；账号变化时要求重新刷新。
- 已选团队被删除或状态变为非 `available` 后，选择自动失效。
- 未选择租户/团队时，所有需要业务上下文的接口拒绝执行，并提示运行 `ml business use`。

## 9. HTTP 客户端与接口封装

### 9.1 统一请求头

业务请求统一携带：

```text
cookie: <完整 Cookie>
csrftoken: <独立捕获的 CSRF Token>
content-type: application/json
referer: <profile.api_endpoint>
ai-businessId: <当前租户或团队 businessId>
```

### 9.2 响应处理

- 成功响应必须是有效 JSON。
- 401、403、419、440：视为认证失效。
- 3xx：不自动跟随，视为认证可能失效。
- 其他非 2xx：返回状态码和最多 500 字符响应摘要。
- 网络或 SSL 异常：统一包装为“请求失败”。

### 9.3 已封装接口

#### 用户信息

```http
GET /ai/user/info
```

命令：

```text
ml user info
ml user info --output json
```

#### MEP 配置查询

```http
POST /ai/backend/mep/config/queryConfig
Content-Type: application/json

{"key":"mep_service_access_type"}
```

命令：

```text
ml mep config get
ml mep config get mep_service_access_type --output json
```

默认 key 为 `mep_service_access_type`，输出接口完整 JSON 响应体。

#### 离线实验列表

```http
GET /ai/backend/experiment/project/list
```

命令：

```text
ml offline experiment list
ml offline experiment list --page 2 --page-size 20
ml offline experiment list --name test --create-user a123456
ml offline experiment list --output json
```

查询参数映射：

| CLI 参数 | 接口参数 | 默认值 | 说明 |
| --- | --- | --- | --- |
| 当前业务上下文 | `businessId` | 无 | 必传，从已校验的 `ml business use` 选择结果获取 |
| `--page` | `pageIndex` | `1` | 开始页码，最小为 1 |
| `--page-size` | `pageSize` | `10` | 每页记录数，最小为 1 |
| `--name` / `--project-name` | `projectName` | 不传 | 实验名称模糊查询 |
| `--description` | `description` | 不传 | 描述模糊查询 |
| `--create-user` | `createUser` | 不传 | 创建者模糊查询 |
| `--update-user` | `updateUser` | 不传 | 修改者模糊查询 |
| `--team-id` | `teamId` | 不传 | 团队筛选；不会从当前团队选择中自动填充 |

默认表格仅展示实验名称、描述、创建者、修改者、创建时间、更新时间、运行配置模板。JSON 输出包含 `pageIndex`、`pageSize`、`count`、`total` 和经过字段筛选的 `items`。业务响应必须满足 `result.code == 0` 且 `result.data` 为数组。

离线实验列表请求除统一请求头外，还必须携带以下请求头：

```text
businessid: <当前租户或团队 businessId>
```

## 10. 本地目录与存储

### 10.1 用户配置根目录

| 操作系统 | 路径 |
| --- | --- |
| Windows | `%APPDATA%\ml` |
| macOS | `~/Library/Application Support/ml` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/ml` |

### 10.2 当前代码状态（0.3.18）

```text
ml/
├── config.json
├── .config.json.installed
├── credentials.json               # 当前：一个文件内按 profile 保存
├── business.json                  # 当前：一个文件内按 profile 保存
└── browser-profiles/
    ├── profile-dev/               # Edge 持久数据
    └── profile-test/              # Edge 持久数据
```

### 10.3 已确认但待实现的环境隔离存储

**状态：待实现，优先级高。**

最新明确需求要求 `business.json` 和 `credentials.json` 都随环境存放到对应 `browser-profiles` 子目录：

```text
ml/
├── config.json
└── browser-profiles/
    ├── profile-dev/
    │   ├── credentials.json
    │   ├── business.json
    │   └── <Edge 持久数据>
    └── profile-test/
        ├── credentials.json
        ├── business.json
        └── <Edge 持久数据>
```

设计约束：

1. 当前环境的登录、认证刷新、业务目录刷新、业务选择和 HTTP 请求必须读取同一环境目录下的文件。
2. `browser.profile_root` 自定义后，两类 JSON 必须跟随自定义根目录。
3. `ml env use` 切换环境后，下一条命令必须使用新环境目录，不能复用旧环境缓存。
4. `ml logout` 只清理当前环境的 `credentials.json`。
5. `ml logout --all` 需要遍历所有已配置环境清理认证文件。
6. `--forget-browser` 删除对应环境目录时，也会同时删除其中的业务与认证文件，命令提示应反映这一点。
7. 原全局 `ml/business.json` 已明确不做兼容迁移；在新位置通过 `ml login` 或 `ml business refresh` 重建。
8. 原全局 `ml/credentials.json` 的迁移策略历史中未最终确认。建议不迁移并要求重新登录，以避免复制过期或跨环境敏感信息；实现前应确认。
9. 除物理路径变化外，JSON 字段格式默认保持不变，降低改造风险。

## 11. 安装、打包与 Windows 使用

### 11.1 运行条件

- Windows PowerShell 5.1 或 PowerShell 7.x（Windows）。
- Python 3.9 或更高版本。
- 系统已安装 Microsoft Edge。
- Python 依赖：`httpx`、`playwright`、`rich`、`typer`。

### 11.2 Wheel 打包方案

本项目选择 Wheel 分发，不生成 exe。构建者执行：

```powershell
py -m pip install --upgrade build
py -m build --wheel
```

当前已提供 Windows 一键发布脚本：

```cmd
scripts\windows\build-release.cmd
```

脚本默认构建包含全部 Python 依赖、安装时无需访问包下载源的离线 ZIP。使用
`build-release.ps1 -Online` 可以生成更小的联网安装包。发布 ZIP 同时包含 Wheel、
安装脚本、安装说明和 SHA-256 校验文件。

离线包文件名和 `release.json` 必须记录构建 Python 主次版本与 Windows 架构；安装器
要求用户环境与其一致。联网包只校验 Python 3.9+，由 pip 在线解析适配当前解释器的
依赖。

产物示例：

```text
dist\wisemlops_cli-0.3.18-py3-none-any.whl
```

安装者执行：

```powershell
py -m pip install --upgrade .\dist\wisemlops_cli-0.3.18-py3-none-any.whl
ml --version
```

### 11.3 任意 CMD 目录执行 `ml`

标准 Wheel 安装会将 `ml.exe` 命令入口放入 Python Scripts 目录。该目录必须位于 Windows `PATH`。建议使用以下任一方式：

1. 安装 Python 时勾选 “Add Python to PATH”。
2. 将用户级 Python Scripts 目录加入用户 `PATH`。
3. 使用 pipx 安装并执行 `pipx ensurepath`，隔离依赖并自动管理命令路径。

示例：

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
pipx install .\dist\wisemlops_cli-0.3.18-py3-none-any.whl
```

重新打开 CMD 后，应能在任意目录执行：

```cmd
ml --help
ml login
```

### 11.4 Windows 一键安装器

**状态：已实现。**

用户完整解压发布 ZIP 后双击 `install.cmd`。安装器默认：

1. 校验 PowerShell 5.1+ 及所需 cmdlet。
2. 校验 `CHECKSUMS.sha256`。
3. 检查 Python 3.9+ 和 Microsoft Edge。
4. 在 `%LOCALAPPDATA%\Programs\WiseMLOpsCLI\venv` 创建独立虚拟环境。
5. 自动识别离线 `packages/`；存在时禁止联网并从本地安装依赖，不存在时联网解析依赖。
6. 创建 `%LOCALAPPDATA%\Programs\WiseMLOpsCLI\bin\ml.cmd`。
7. 将上述 `bin` 目录加入当前用户 `PATH`。
8. 调用虚拟环境中的 `ml --version` 验证安装。

整个过程不要求管理员权限。升级时解压新版本并再次运行 `install.cmd`；使用 `-Force`
可删除并重建 CLI 虚拟环境，但不会删除 `%APPDATA%\ml` 下的配置、认证缓存或 Edge
Profile。

## 12. 复杂资源与离线实验 CLI 规划

**状态：规划中，尚未实现。**

Web 管理台资源依赖如下：

```text
环境配置模板
    ↓ 被引用
构建流程模板（含复杂工作流配置）
    ↓ 被引用
离线实验
```

### 12.1 环境配置模板字段

- 名称：手动填写。
- 状态：可选、优选、禁选。
- 租户。
- 团队：下拉选择。
- 子数据域：下拉选择。
- 关联服务名称。
- 区域：下拉选择。
- 集群：下拉选择。
- 描述：手动填写。

### 12.2 构建流程模板字段

基本信息：

- 模板名称。
- 状态：可选、优选、禁选。
- 描述。
- 引用某个环境配置模板。

工作流配置：复杂结构，建议使用 YAML/JSON 文件声明，不通过大量命令行参数直接表达。

### 12.3 离线实验字段

- 实验名称。
- 描述。
- 引用某个构建流程模板。

### 12.4 推荐创建方式

采用声明式文件 + 服务端 ID/名称解析 + 创建前校验：

```text
ml offline experiment create -f experiment.yaml
ml offline experiment validate -f experiment.yaml
ml offline experiment create -f experiment.yaml --dry-run
```

建议配置示例：

```yaml
apiVersion: wisemlops/v1
kind: OfflineExperiment
metadata:
  name: demo-experiment
spec:
  description: 示例离线实验
  buildFlowTemplate:
    name: demo-build-flow
```

在创建实验前，CLI 应：

1. 确认当前业务上下文已选择租户或团队。
2. 查询并唯一解析构建流程模板。
3. 校验构建流程模板引用的环境配置模板仍有效。
4. 校验状态是否允许选择。
5. 对复杂工作流配置进行 schema 校验。
6. 使用 `--dry-run` 展示解析后的 ID 和最终请求体。
7. 用户确认后调用创建接口。

待补充信息：三个资源的查询/创建 API、唯一键、分页规则、状态枚举的后端值、工作流 JSON Schema、幂等和重复名称策略。

## 13. 安全与可靠性要求

1. Cookie 和 CSRF Token 不得默认打印。
2. 认证文件和业务选择文件不得提交 Git。
3. 写 JSON 使用临时文件后原子替换，尽量设置用户私有权限。
4. Cookie 必须完整保存和发送，禁止日志截断后再用于请求。
5. `csrftoken` 必须来自独立请求头，禁止假设它存在于 Cookie。
6. 禁止跨环境复用 Edge Profile、认证信息和业务目录。
7. 关闭 SSL 校验必须是显式环境配置，不作为默认行为。
8. 不在 Service 或命令层复制认证刷新逻辑。
9. 页面导航与响应体读取存在竞态时，必须先保存响应文本，或使用浏览器请求上下文重新请求。
10. 认证刷新最多自动重试一次，避免死循环和频繁弹出浏览器。

## 14. 验收标准

### 14.1 登录

- 未安装 Playwright 时给出可执行的安装提示。
- 使用系统 Edge 和当前环境独立 Profile。
- 已有有效会话时无需验证码。
- 不需要用户按回车确认登录。
- `/ai/user/info.result.code == 0` 才视为成功。
- 成功打印账号、中文名、部门和租户。
- Cookie 完整，CSRF Token 从独立请求头获取。
- 成功后自动关闭 Edge；失败时 Edge 保持打开供排查。

### 14.2 业务上下文

- 部门解析不使用 `settleTenant`。
- 部门列表和租户列表只显示名称。
- 团队列表满足颜色、文字和自动高亮规则。
- 禁选团队不能写入选择结果。
- 选择结果只展示五个重要字段。
- 团队级请求头使用 `teamList[].businessId`。
- 切换账号或目录变化后能发现无效选择。

### 14.3 接口请求

- MEP 查询请求路径和 JSON 请求体正确。
- 所有业务请求携带 Cookie、`csrftoken` 和 `ai-businessId`。
- 认证失效时自动登录并仅重试一次。
- SSL 可全局配置并按环境覆盖。
- table/json 输出可选择。

### 14.4 安装

- Wheel 中包含根目录默认 `config.json`。
- 新版本首次运行刷新用户配置。
- 安装后在已正确配置 PATH 的任意 CMD 目录可执行 `ml`。
- `ml --version` 与 Wheel 版本一致。

### 14.5 待实现存储隔离

- dev 与 test 的 `business.json`、`credentials.json` 位于各自 Edge Profile 目录。
- 切换环境后读写路径立即切换。
- `logout`、`logout --all`、`--forget-browser` 的删除范围准确。
- 自定义 `browser.profile_root` 时路径仍正确。
- 不再读取全局 `ml/business.json`。

## 15. 版本与主要里程碑

| 版本/阶段 | 主要内容 |
| --- | --- |
| 初始阶段 | 创建 `config.json`，Playwright 登录并获取 Cookie、CSRF Token、username |
| `wo` 阶段 | Python CLI、认证有效期和自动刷新 |
| 命名升级 | `wo` 改为 `ml`，清理遗留字样 |
| 环境管理 | `profile` 改为 `env`，支持环境级 `verify_ssl` |
| `0.3.0` | `/ai/user/info` code 判定，打印账号/中文名/部门 |
| `0.3.1`—`0.3.4` | 默认配置进入 Wheel，安装版本刷新用户配置 |
| 业务上下文 | 读取 `ai-businessId`、`ai-businessList`，新增 `ml business` |
| schema v2 | 使用 `businessId`，移除 `effective_business_id`，不迁移旧文件 |
| `0.3.8`—`0.3.9` | 修正部门回退和分组，不再使用 `settleTenant` |
| `0.3.10` | 收敛选择结果字段，增加团队状态样式 |
| `0.3.11` | 关闭 Rich 自动高亮 |
| `0.3.12` | 部门只显示名称，提示改为“请选择团队” |
| `0.3.13` | 租户只显示名称 |
| `0.3.14` | 新增 Windows 一键构建、离线/联网发布和免管理员安装脚本 |
| `0.3.15` | 修复 Windows PowerShell 5.1 参数绑定阶段无法解析发布目录的问题 |
| `0.3.16` | 完成 PowerShell 5.1/7.x 兼容审计，修复变量解析并增加版本与命令预检 |
| `0.3.17` | 新增离线实验分页列表查询，支持模糊筛选及 table/json 输出 |
| `0.3.18` | 离线实验列表请求增加必需的 `businessid` 请求头 |
| 后续待实现 | `business.json`、`credentials.json` 随环境存放 |

## 16. 决策记录与废弃行为

| 主题 | 最终决策 |
| --- | --- |
| 浏览器 | 使用系统 Microsoft Edge，不使用 Playwright Chromium |
| Edge Profile | 每个环境使用专用持久化 Profile |
| 登录确认 | 自动检测，不按回车 |
| 登录成功后浏览器 | 自动关闭 |
| 登录失败后浏览器 | 保持打开供用户排查 |
| CSRF Token | 独立请求头，不从 Cookie 解析 |
| 命令前缀 | `ml`，不再使用 `wo` |
| 环境命令 | `ml env`，不再使用 `ml profile` |
| 业务命令 | `ml business`，不再使用 `ml context` |
| 打包 | Wheel，不要求 exe |
| 默认配置 | 仅以项目根目录 `config.json` 为源码 |
| 部门分组 | 使用显示名称回退链，不使用 `settleTenant` |
| business schema | `businessId`，不保留 `effective_business_id` |

## 17. 当前遗留事项

1. **高优先级**：将 `business.json` 移至各环境 Edge Profile 子目录。
2. **高优先级**：将 `credentials.json` 同样移至各环境 Edge Profile 子目录。
3. 明确旧全局 `credentials.json` 是否迁移；当前建议不迁移。
4. 更新 README 中的本地存储路径说明。
5. 为新路径补充 dev/test 隔离、环境切换、logout 和自定义 profile root 测试。
6. 获取离线实验相关后端 API 和工作流 schema，进入实现阶段。
7. 评估默认配置在每次版本升级时强制覆盖用户自定义配置的长期风险，可考虑未来引入“默认模板 + 用户覆盖层”。
