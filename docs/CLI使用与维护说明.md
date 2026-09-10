# CLI 使用与维护说明

> 面向 WiseMLOps 平台的命令行客户端：把平台上的查询与配置操作带到终端，方便脚本化和批量处理。

`ml` 通过 Microsoft Edge 复用你的平台登录态，把认证信息、业务上下文（部门 / 租户 / 团队）缓存在本地，
业务请求通过 HTTP(S) 访问平台接口，支持表格或 JSON 输出；认证过期时仍可能打开浏览器。

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Version](https://img.shields.io/badge/version-1.0.0-informational)

---

## 目录

- [它解决什么问题](#它解决什么问题)
- [快速开始](#快速开始)
- [运行环境要求](#运行环境要求)
- [核心概念](#核心概念)
- [配套权限管理系统](#5-配套权限管理系统)
- [命令速查](#命令速查)
- [输出与脚本化](#输出与脚本化)
- [配置文件](#配置文件)
- [本地文件布局](#本地文件布局)
- [架构与代码结构](#架构与代码结构)
- [Windows 安装与发布](#windows-安装与发布)
- [故障排查](#故障排查)
- [安全说明](#安全说明)
- [贡献](#贡献)
- [许可证](#许可证)

---

## 它解决什么问题

平台上的操作大多要点开网页、逐层点选租户和团队才能看到数据。当你要做的事变成"每天查一遍训练看板的指标"
或"把一个实验克隆十份"，网页操作既慢又无法纳入脚本。`ml` 把这些操作变成一条命令：

```bash
ml offline experiment list --name "训练" --page-size 50 -o json | jq '.items[].projectId'
```

同时它解决了命令行工具的经典难题 —— **登录**。`ml` 不要求你在终端里输入账号密码，而是拉起一个
专用 Edge 窗口复用平台的登录会话：浏览器里已经是登录状态就直接读取认证信息，没有才需要你手动登录一次。
本地认证默认有效 30 分钟（可配置）；过期后会重开浏览器，优先复用平台会话，必要时需手动重新登录。

---

## 快速开始

普通用户请从 [GitHub v1.0.0](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.0) 下载 Windows 联网或离线安装包，解压运行 `install.cmd`。离线包要求 Python 3.12 x64，Python 和 Edge 需另行安装。以下源码安装步骤用于开发，先将仓库下载到本地并进入项目根目录。

```bash
# 1. 安装（开发模式，建议在虚拟环境中执行）
py -m pip install --upgrade pip
py -m pip install -e .

# 2. 确认安装
ml --version

# 3. 查看当前环境并登录（会打开 Edge）
ml env show
ml login

# 4. 选择业务上下文：部门 → 租户 → 团队
ml business use

# 5. 跑第一条命令
ml user info
ml offline experiment list --page-size 5
```

> 平台业务命令需要当前环境的登录与租户或团队选择；`business list/use/refresh` 用于建立上下文，不要求预先选好业务。帮助、版本、登录退出和环境选择可先执行。

使用系统已安装的 Microsoft Edge，**不需要**执行 `playwright install chromium`。

---

## 运行环境要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| Python | 3.9 或更高 | 包声明 `requires-python = ">=3.9"` |
| 操作系统 | Windows / macOS / Linux | Windows 有一键安装包，见下文 |
| 浏览器 | Microsoft Edge | 登录必需；支持 `msedge`、`msedge-beta`、`msedge-dev`、`msedge-canary` |
| 网络 | 可访问平台地址 | 由 `profiles[].api_endpoint` 决定 |

Python 依赖：`typer`（命令框架）、`rich`（表格输出）、`httpx`（HTTP 客户端）、`playwright`（驱动 Edge）。

---

## 核心概念

理解以下概念就能顺畅使用 `ml`。

### 1. 环境（profile）

一个环境就是一套平台地址，定义在 `config.json` 的 `profiles` 数组里，`current` 字段标记当前激活项。
切换环境只影响"连哪个平台"，不会互相污染：

```bash
ml env list          # 列出全部环境，* 标记当前
ml env show          # 当前环境详情
ml env use dev       # 切换环境（写回 config.json）
```

### 2. 认证（credentials）

- 登录方式：Playwright 启动**持久化 Edge Profile**（每个环境一个目录），导航到平台首页。
- 成功判定：监听页面对 `/ai/user/info` 的请求，抓取 `cookie` 与 `csrftoken`，再回放该请求校验；
  校验通过才算登录成功，CLI 会自动关闭 Edge，用户不用敲回车。
- 有效期：默认 1800 秒（30 分钟），由 `auth.expires_in_seconds` 控制。
- 续期策略：命令执行前检查有效期；过期则重开 Edge，**优先复用已有平台会话**（通常无验证码即恢复），
  只有平台会话真失效时才要求重新登录。
- 兜底重试：若服务端返回 401 / 403 / 419 / 440 或发生重定向，CLI 会刷新认证并**重试一次**。

```bash
ml auth status               # 剩余有效期，不打印敏感值
ml login --show-secrets      # 打印完整 Cookie 与 CSRF Token（排查用，注意泄露风险）
ml logout                    # 只清 CLI 缓存，保留浏览器会话
ml logout --forget-browser   # 连专用 Edge Profile 一起删除（下次可能需重新输验证码）
```

### 3. 业务上下文（businessId）

平台数据按「部门 → 租户 → 团队」三级隔离。CLI 从浏览器 `localStorage` 的 `ai-businessList`
解析出这份目录并缓存在本地，业务请求同时携带 `ai-businessId` 和 `businessid` 请求头，取当前环境 `business.json` 的 `selected.businessId`。

- **必须至少选到租户**，不能只选部门；团队只有 `teamStatus == "available"` 时才可选。
- 租户级选择使用 `tenant.id` 作为 `businessId`；团队级选择使用 `teamList[].businessId`。
- 名称取值优先级：`settleTenantName.cn` → `settleTenantName.en` → 顶层 `cn`。

```bash
ml business list                    # 展示三级目录，*当前 标记已选项
ml business show                    # 当前选择
ml business use                     # 交互式：部门 → 租户 → 租户级或团队级
ml business use --tenant mep --team my-team
ml business refresh                 # 重开 Edge 重新读取目录
```

### 4. 命令域

| 域 | 命令前缀 | 覆盖能力 |
| --- | --- | --- |
| 认证与环境 | `login` `logout` `auth` `env` | 登录、续期、退出、多环境切换 |
| 业务上下文 | `business` | 部门 / 租户 / 团队目录与选择 |
| 用户 | `user` | 当前登录用户信息 |
| MEP | `mep` | 平台配置项查询 |
| MTP | `mtp swanboard` | 训练看板：项目、项目空间、实验、特性、环境、指标、配置 |
| 离线业务 | `offline` | 离线实验列表、trial 列表、实验克隆 |
| 训练任务 | `train` | 任务与实例查询、执行记录、日志下载、启动任务、更新配置 |
| 特征集 | `featureset` | 宽表与模型特征集列表、配置查询 |
| 在线授权 | `access` | 检查当前账号和环境的访问授权 |

### 5. 配套权限管理系统

管理员通过独立 Web 服务管理人员、环境授权、有效期及调用审计。CLI 的 `access_control` 默认关闭，启用后会在执行业务命令前检查当前账号与环境授权；拒绝或服务故障会阻止该次业务调用。客户端校验不替代平台后端鉴权，也不负责创建平台本身的租户权限。

服务使用 MySQL，支持 Docker 离线部署，详见 [Docker 部署速查](权限管理系统Docker安装部署与调试指南.md)。部署后在 CLI 配置中合并以下字段，保留其他设置：

```json
{
  "access_control": {
    "enabled": true,
    "url": "http://服务器IP:8008/cli-permission",
    "timeout_seconds": 15,
    "use_env_proxy": false
  }
}
```

替换为实际服务地址，管理员配置与平台账号一致的人员及对应环境授权。登录、选择业务后执行 `ml access status`；排查连接时可用 `ml access status --diagnose`。

---

## 命令速查

### 命令树

```text
ml
├── login                             登录并刷新当前环境的认证信息
├── logout                            清除本地认证信息
├── auth
│   └── status                        查看认证有效期
├── env
│   ├── list | show | use             环境列表 / 详情 / 切换
├── business
│   ├── list | show | use | refresh   业务目录与上下文
├── user
│   └── info                          当前用户信息
├── mep
│   └── config
│       └── get [KEY]                 查询 MEP 配置项
├── mtp
│   └── swanboard                     训练看板
│       ├── project
│       │   ├── list                  项目分页查询
│       │   ├── namespace list <projectId>
│       │   └── experiment list <projectId> <namespaceId>
│       └── experiment
│           ├── feature list <experimentId>
│           ├── environment get <experimentId>
│           ├── metrics <experimentId> [--tag loss --tag accuracy]
│           ├── config list <experimentId>
│           └── inspect <experimentId>    一次查全部（特性/环境/指标/配置）
├── offline
│   └── experiment
│       ├── list                      离线实验分页查询
│       ├── trial list <projectId>    某实验下的 trial 列表
│       └── clone <projectId>         克隆实验（仅改名称）
├── access
│   └── status [--diagnose]           当前账号与环境授权
├── train
│   ├── list                         训练任务列表
│   ├── start <task-id>               启动训练任务
│   ├── config update <task-id>       更新任务配置
│   ├── instance list <task-id>       执行实例
│   └── history
│       ├── list <task-id>            执行记录
│       └── logs download <task-id> <job-id>  下载日志
└── featureset
    ├── wide
    │   ├── list                     宽表特征集
    │   └── config <set-id>           查看配置
    └── model
        ├── list                     模型特征集
        └── config <set-id>           查看配置
```

全局选项：`--config PATH`（等价于环境变量 `ML_CONFIG`）、`--version`、`--help`。
`ml` 不带参数或加 `--help` 会打印顶层帮助；各子命令使用 `--help` 查看参数。当前未配置 `-h` 别名。

### 常用示例

```bash
# 认证与环境
ml login
ml auth status
ml env list
ml env use dev

# 业务上下文
ml business list
ml business use --tenant mep --team my-team
ml business show

# 用户与平台配置
ml user info -o json
ml mep config get mep_service_access_type -o json

# 训练看板：从项目一路查到实验指标
ml mtp swanboard project list --page 1 --page-size 10
ml mtp swanboard project namespace list <projectId>
ml mtp swanboard project experiment list <projectId> <namespaceId>
ml mtp swanboard experiment metrics <experimentId>
ml mtp swanboard experiment metrics <experimentId> --tag loss
ml mtp swanboard experiment inspect <experimentId> --output json

# 离线实验
ml offline experiment list --page 1 --page-size 20 --name "训练"
ml offline experiment trial list <projectId> --type batch --page-size 20
ml offline experiment clone <projectId> --name "训练-副本"          # 会先确认
ml offline experiment clone <projectId> --name "训练-副本" -y       # 跳过确认
ml offline experiment clone <projectId> --name "训练-副本" --dry-run # 只看请求体
```

### 过滤参数速查

| 命令 | 主要参数 |
| --- | --- |
| `mtp swanboard project list` | `--page` `--page-size` `--team-id` `--creator` |
| `mtp swanboard experiment feature list` | `--page` `--page-size` |
| `offline experiment list` | `--page` `--page-size` `--name/--project-name` `--description` `--create-user` `--update-user` `--team-id` |
| `offline experiment trial list` | `--page` `--page-size` `--name` `--type` `--creator` `--updater` `--ai-module` |
| `offline experiment clone` | `--name`（必填）`--yes/-y` `--dry-run` |

> 完整的逐命令参数说明见 [docs/CLI参考使用指南.md](CLI参考使用指南.md)。

---

## 输出与脚本化

- **两种格式**：`table`（默认，人类可读）与 `json`（脚本消费）。
- **选择方式**：命令行 `--output` / `-o` 临时指定；不传则跟随当前环境的 `profiles[].output_format`。
- **固定表格输出的命令**：`env`、`business`、`auth status`（这些是上下文信息，不提供 JSON）。
- **退出码**：成功为 `0`；业务错误通常为 `1`，参数错误通常为 `2`，脚本应以非零判断失败。业务错误写入 stderr；使用 JSON 输出前确认命令支持该格式。交互提示、进度和 URL 输出规则以对应命令说明为准。

```bash
ml offline experiment list -o json > experiments.json
ml user info --output json | jq -r '.result.username'
```

---

## 配置文件

`config.json` 是默认配置的唯一来源。

### 查找优先级

1. 命令行 `--config PATH`
2. 环境变量 `ML_CONFIG`
3. 当前工作目录的 `config.json`
4. 用户配置目录的 `config.json`

```powershell
ml --config C:\path\to\config.json env show
$env:ML_CONFIG = "C:\path\to\config.json"
```

> **安装会覆盖用户默认配置**：Windows 安装器每次运行都会用包内配置覆盖用户默认 config.json，包括同版本重装。直接 pip 安装后，在读取默认配置时按版本、内容哈希和安装文件时间戳判断是否同步；普通后续运行不重复覆盖。升级前备份自定义环境和 access_control，安装后核对。显式 --config、ML_CONFIG 和当前目录配置是独立配置来源，不作为安装器覆盖目标。

### 字段说明

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `current` | string | — | 当前环境名，必须存在于 `profiles` |
| `api.timeout` | int(ms) | `30000` | HTTP 请求超时 |
| `api.retry_times` | int | `3` | 传输层重试次数 |
| `api.verify_ssl` | bool | `true` | 全局 HTTPS 证书校验开关 |
| `access_control.enabled` | bool | `false` | 是否启用在线权限校验 |
| `access_control.url` | string | 空 | 权限服务地址，包含 /cli-permission |
| `access_control.timeout_seconds` | int(s) | `15` | 权限检查超时，范围 1–120 |
| `access_control.use_env_proxy` | bool | `false` | 权限请求是否采用环境代理 |
| `auth.expires_in_seconds` | int | `1800` | 本地认证有效期 |
| `browser.channel` | string | `msedge` | Edge 通道 |
| `browser.session_probe_timeout` | int(ms) | `5000` | 登录后探测已有会话的等待时间 |
| `browser.login_timeout` | int(ms) | `300000` | 等待用户完成登录的上限（5 分钟） |
| `browser.business_catalog_timeout` | int(ms) | `30000` | 读取 `ai-businessList` 的上限 |
| `browser.profile_root` | string | 用户配置目录 | 自定义 Edge Profile 根目录 |
| `profiles[].name` | string | — | 环境名（唯一） |
| `profiles[].api_endpoint` | string | — | 环境地址，必须 http/https |
| `profiles[].output_format` | string | `table` | `table` 或 `json` |
| `profiles[].verify_ssl` | bool? | 继承全局 | 单环境覆盖证书校验 |

### 示例

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
  "access_control": {
    "enabled": false,
    "url": "",
    "timeout_seconds": 15,
    "use_env_proxy": false
  },
  "browser": {
    "channel": "msedge",
    "session_probe_timeout": 5000,
    "login_timeout": 300000,
    "business_catalog_timeout": 30000
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
    },
    {
      "name": "internal",
      "api_endpoint": "https://10.0.0.1/dashboard",
      "output_format": "table",
      "verify_ssl": false
    }
  ]
}
```

`verify_ssl: false` 同时作用于接口请求和 Playwright 启动的 Edge 上下文，**仅建议用于完全可信的内网**。

---

## 本地文件布局

用户配置根目录：

| 操作系统 | 路径 |
| --- | --- |
| Windows | `%APPDATA%\ml` |
| macOS | `~/Library/Application Support/ml` |
| Linux | `${XDG_CONFIG_HOME:-~/.config}/ml` |

```text
ml/
├── config.json                    # 生效的配置（可能被安装包覆盖）
├── .config.json.installed         # 覆盖标记：版本、内容哈希及安装时间戳
├── credentials.json               # 认证缓存，按 profile 分组；POSIX 权限 0600
├── business.json                  # 业务目录与当前选择，按 profile 分组
└── browser-profiles/
    ├── profile-dev/               # 环境 dev 的 Edge 持久数据
    └── profile-test/              # 环境 test 的 Edge 持久数据
```

敏感度：`credentials.json` 内含 Cookie 与 CSRF Token，写入时按 `0600` 收紧权限，默认位于用户目录；提交文件前仍需确认未包含凭据（Git 忽略规则不能阻止强制添加或已跟踪文件）。`business.json` 使用 `version: 2` 格式，旧版本文件不做迁移，
会在下次 `ml login` 或 `ml business refresh` 时重建。

---

## 架构与代码结构

### 分层

```text
命令层  src/wiserec_cli/commands/*      参数解析、交互提示、输出
   ↓
服务层  src/wiserec_cli/services/*      业务接口封装（路径、参数、响应校验）
   ↓
客户端  src/wiserec_cli/client.py       统一请求头、超时、重试、错误分类
```

周边支撑：

- `cli.py` — Typer 入口，注册全部命令组，`--config` / `--version` 回调。
- `runtime.py` — 运行时容器（配置、认证、业务、客户端）；`authenticated_call()` 实现"认证失效自动重试一次"。
- `auth.py` / `credentials.py` — Edge 登录、认证信息读写。
- `business.py` — `ai-businessList` 解析与业务上下文持久化。
- `config.py` / `models.py` — 配置读取校验、`Profile` 与 `Credentials` 数据模型。
- `output.py` / `errors.py` — `table` / `json` 渲染与统一异常体系（`MlError` 派生）。

### 目录结构

```text
src/wiserec_cli/
├── cli.py                 # 入口与命令注册
├── runtime.py             # 运行时与认证重试
├── config.py              # 配置管理
├── credentials.py         # 认证持久化
├── auth.py                # Edge 登录流程
├── business.py            # 业务上下文
├── client.py              # HTTP 客户端
├── models.py              # 数据模型
├── output.py / errors.py  # 输出与异常
├── commands/              # access auth business env featureset mep mtp offline train user
└── services/              # experiment featureset mep swanboard train user
```

### 增加一个新接口

1. 在 `services/<domain>.py` 里写请求方法与响应校验（复用 `_result` / `_data` 之类的解析辅助）。
2. 在 `commands/<domain>.py` 里加命令，只负责参数、调用 `runtime.authenticated_call(...)` 和输出。
3. 若涉及 `businessId`，命令必须调用 `authenticated_call`，由它统一注入上下文与认证。

```text
commands/mep.py  →  services/mep.py  →  client.py
```

**不要在命令模块里直接拼 Cookie、URL 或超时。** 如果后端提供 OpenAPI，可把生成的客户端放进独立的
`generated/` 目录，由 service 层适配，命令层结构不变。

### 测试

```bash
py -m pytest
```

CLI 测试位于 `tests/`，使用 mock 与临时目录验证逻辑，不访问真实业务平台；用例数量以测试输出为准。覆盖：
配置解析与覆盖、认证信息读写、业务目录解析与选择、HTTP 客户端错误分类、运行时重试、
各 service 的响应校验、命令可用性与 Windows 打包脚本约束。权限服务另有 `access-service/tests/`；GitHub 发布流程还会验证 Windows 安装升级、Docker 离线导入和真实 MySQL，不能用 CLI 单元测试代替这些验证。

> 仓库根目录的 `capture_auth.py` 是早期用于单独验证登录流程的独立脚本，不属于安装包，
> 日常使用无需关心。

---

## Windows 安装与发布

### 面向使用者

1. 完整解压发布 ZIP（不要只复制单个 Wheel）。
2. 双击 `install.cmd`，按提示完成（无需管理员权限）。
3. 重新打开 CMD / PowerShell 使 `PATH` 生效，然后执行 `ml --version`、`ml env show`、`ml login`。

安装器会校验 `CHECKSUMS.sha256`、检查 Python 3.9+ 与 Edge，在
`%LOCALAPPDATA%\Programs\WiseRecCLI` 创建**独立虚拟环境**（不污染其他 Python 项目），
并把 `ml` 加入当前用户 `PATH`。

PowerShell 补全：

```powershell
ml --install-completion powershell
```

### 面向发布人员

```cmd
scripts\windows\build-release.cmd
```

产出联网包 `release\wiserec-cli-<版本>-windows-py3-online.zip`：

- **联网包**：只带通用 Wheel，安装时按用户实际 Python 版本拉依赖，因此一个包可用于 Python 3.12 / 3.13 等；
  要求内网源包含全部直接与传递依赖的 Windows Wheel，脚本**不会**回退公网附加源。
- **离线包**：加 `-Offline` 生成，依赖与 Python 小版本、Windows 架构绑定。

企业内网源可预置进发布包（不得包含凭据）：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\build-release.ps1 `
  -IndexUrl "https://pypi.company.example/simple" -Force
```

安装时也可显式指定源、私有 CA 证书或安装目录：

```powershell
.\install.ps1 -IndexUrl "https://pypi.company.example/simple"
.\install.ps1 -Cert "C:\Certificates\company-ca.pem"
.\install.ps1 -InstallDirectory "D:\Tools\WiseMLOpsCLI"
.\install.ps1 -SkipEdgeCheck                   # 仅跳过安装期 Edge 检查
```

升级：解压新包再次运行 `install.cmd`；CLI 程序会升级，登录缓存与 Edge Profile 保留。

> 详细步骤、常见问题与包源优先级见 [scripts/windows/INSTALL.md](../scripts/windows/INSTALL.md)。

---

## 故障排查

| 现象 | 原因 | 处理 |
| --- | --- | --- |
| `尚未选择租户或团队，请运行 ml business use` | 未建立业务上下文 | 执行 `ml business use` |
| `不能仅选择部门或团队，请同时通过 --tenant 指定租户` | 只传了 `--team` 或 `--department` | 补上 `--tenant` |
| `当前环境没有业务目录，请先运行 ml login 或 ml business refresh` | 本地还没缓存目录 | 跑 `ml login` 或 `ml business refresh` |
| `业务目录属于其他账号，请运行 ml business refresh` | 换过账号 | 刷新目录 |
| `business.json 版本不兼容…` | 旧格式文件 | 按提示重新生成（不迁移） |
| `等待登录超时（300 秒）…` | 未在时限内完成登录 | 重新执行，或在 Edge 里完成登录；必要时调大 `browser.login_timeout` |
| `认证信息已被服务端拒绝，HTTP 401/403` | 会话失效或权限不足 | 已自动刷新重试一次；仍失败请确认平台侧环境授权 |
| `接口请求被重定向…` | 认证失效导致跳登录页 | 同上，重新登录 |
| `配置文件不存在: …` | 路径不对 | 用 `--config` 或 `ML_CONFIG` 指定 |
| `profiles 中不存在 current 指定的环境: X` | `current` 与 `profiles` 不一致 | 修正 `config.json` |
| `团队 'X' 当前状态为 '…'，不可选择` | 团队非 `available` | 换团队，或联系管理员 |
| 找不到 `ml` 命令 | `PATH` 未刷新 | 重新打开终端 |

想确认当前状态时，先跑这三条：

```bash
ml --version
ml auth status
ml business show
```

---

## 安全说明

- **凭据保存在本地**：CLI 将 Cookie / CSRF Token 写入用户目录的 credentials.json，并尝试限制文件权限；Edge 持久化目录也包含登录会话。Windows 应同时依靠用户目录 ACL，勿上传这些文件。
- **默认不打印敏感值**：只有显式加 `--show-secrets` 才会输出 Cookie，请勿在共享终端或日志中使用。
- **关闭证书校验有风险**：`verify_ssl: false` 应仅用于完全可信的内网地址。
- **发布包不带凭据**：内网源地址不得包含用户名、密码或令牌；认证请通过 `PIP_INDEX_URL` 等安全环境变量提供。
- **认证有效期有限**：默认 30 分钟是 CLI 的有效期检查，不代表缓存内容到期自动删除；清理登录缓存用 ml logout，清理专用浏览器会话需加 --forget-browser。

---

## 贡献

1. Fork 仓库并创建特性分支：`git checkout -b feature/your-feature`。
2. 安装开发依赖（`py -m pip install -e .`），确保测试通过：

   ```powershell
   py -m pytest
   ```

3. 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)：`feat:`、`fix:`、`docs:` 等。
4. 向 `main` 分支提 Pull Request，并在描述中说明动机与测试方式。

提交 Issue 前请先检索已有问题；反馈时附上 `ml --version` 输出、操作系统版本、复现步骤与期望行为。

---

## 参见

- [docs/CLI参考使用指南.md](CLI参考使用指南.md) — 每个命令、参数、配置项与退出行为的完整参考
- [docs/REQUIREMENTS_DESIGN_SPEC.md](REQUIREMENTS_DESIGN_SPEC.md) — 功能设计与实现细节规格
- [scripts/windows/INSTALL.md](../scripts/windows/INSTALL.md) — Windows 安装器详细说明

---

## 许可证

本项目基于 [MIT 许可证](../LICENSE) 开源，详见 [LICENSE](../LICENSE)。
