# 命令行参考使用指南

`ml` 是 **WiseMLOps 平台** 的 Python 命令行客户端（包名 `wisemlops-cli`，当前版本 `0.3.25`）。
本文档是每一个 `ml` 子命令、参数、配置项与退出行为的完整参考。

> 阅读前提：首次使用请先完成 `ml login`。所有业务命令（除 `login`/`logout`/`env`/`auth status` 外）都要求已登录且已选择租户或团队（见 `ml business use`）。

---

## 全局用法

```text
ml - WiseMLOps平台命令行客户端

用法：ml [OPTIONS] COMMAND [ARGS]...

选项：
  --config PATH      config.json 路径，也可使用 ML_CONFIG 环境变量
  --version          显示版本
  -h, --help         显示帮助信息并退出

命令：
  login              打开 Edge 登录并刷新当前环境的本地认证信息
  logout             清除当前环境的本地认证信息
  auth               查看认证状态
  business           管理部门、租户和团队
  env                管理运行环境
  user               用户信息
  mep                MEP 管理
  offline            离线业务管理
```

`ml` 与 `ml -h` / `ml --help` 会打印上述顶层用法。每个子命令同样接受 `-h` / `--help`。

---

## 命令总览

| 命令 | 作用 |
| --- | --- |
| `ml login` | 打开 Edge 登录并刷新当前环境的本地认证信息 |
| `ml logout` | 清除当前环境的本地认证信息 |
| `ml auth status` | 显示当前环境的认证有效期（不显示敏感值） |
| `ml env list` | 列出全部环境 |
| `ml env show` | 显示当前环境 |
| `ml env use <name>` | 切换当前环境 |
| `ml business list` | 显示当前环境可见的部门、租户、团队目录 |
| `ml business show` | 显示当前租户或团队上下文 |
| `ml business use` | 交互式或通过 ID 选择租户/团队 |
| `ml business refresh` | 打开 Edge 刷新当前环境的业务目录 |
| `ml user info` | 查询当前登录用户信息 |
| `ml mep config get <key>` | 查询一个 MEP 配置项 |
| `ml mtp swanboard project list` | 分页查询训练看板项目 |
| `ml mtp swanboard experiment inspect <experiment_id>` | 查询实验的完整训练看板数据 |
| `ml offline experiment list` | 分页查询离线实验 |
| `ml offline experiment trial list <project_id>` | 分页查询一个离线实验下的 trial |
| `ml offline experiment clone <project_id>` | 克隆一个离线实验（仅修改名称） |

---

## 全局选项

所有命令均继承以下顶层选项（定义于 CLI 入口回调）：

| 选项 | 环境变量 | 说明 |
| --- | --- | --- |
| `--config PATH` | `ML_CONFIG` | 指定 `config.json` 路径；文件必须存在且为合法 JSON |
| `--version` | — | 打印 `ml <版本号>` 后退出（优先级最高，`-h` 之前生效） |
| `-h`, `--help` | — | 打印对应命令的用法后退出 |

> 配置文件解析优先级：`--config` → `ML_CONFIG` → 当前工作目录的 `config.json` → 用户配置目录的 `config.json`（Windows `%APPDATA%\ml\config.json`、macOS `~/Library/Application Support/ml/config.json`、Linux `~/.config/ml/config.json`）。
> 安装包携带的默认 `config.json` 会在「新版本」或「默认配置变化」后首次运行时，自动覆盖用户配置目录的那份文件；同一版本再次运行不会重复覆盖。升级前若改过环境配置，请先备份用户配置目录的 `config.json`。

---

## `ml login`

打开 Microsoft Edge（专用 Profile）完成平台登录，并将 Cookie、CSRF Token、账号、中文名、部门与过期时间按环境保存到本地。登录成功后默认不打印敏感值。

### 命令格式

```text
ml login [OPTIONS]
```

### 选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--show-secrets` | `False` | 登录成功后额外打印完整的 Cookie 和 CSRF Token |

### 说明

- 认证默认有效 `auth.expires_in_seconds` 秒（默认 1800，即 30 分钟）。
- 执行命令前会检查有效期；过期时自动打开 Edge 专用 Profile，优先复用已有平台会话，无需重复输入验证码。
- 若服务端提前返回 401 / 403，会刷新认证并重试一次。
- `login_timeout`（默认 300000 毫秒 = 5 分钟）控制等待用户登录的最长时间；`business_catalog_timeout`（默认 30000 毫秒）控制读取业务目录的最长等待。

### 示例

```bash
ml login
ml login --show-secrets
```

---

## `ml logout`

清除当前环境的本地短期认证缓存（不影响 Edge 持久会话，方便下次无验证码恢复）。

### 命令格式

```text
ml logout [OPTIONS]
```

### 选项

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--all` | `False` | 清除**所有**环境的本地认证信息，而非仅当前环境 |
| `--forget-browser` | `False` | 同时删除专用 Edge Profile，之后登录可能需要重新输入验证码 |

### 示例

```bash
ml logout
ml logout --all
ml logout --forget-browser
ml logout --all --forget-browser
```

---

## `ml auth status`

显示当前环境的认证有效期与基础信息，不打印任何敏感值。

### 命令格式

```text
ml auth status
```

### 输出字段

| 字段 | 说明 |
| --- | --- |
| `profile` | 当前环境名 |
| `username` | 登录账号 |
| `cn_name` | 中文名 |
| `department` | 部门 |
| `business_id` | 当前业务 ID（`ai-businessId`） |
| `status` | `valid` 或 `expired` |
| `remaining_seconds` | 距过期剩余秒数 |
| `acquired_at` | 获取时间（ISO 8601，到秒） |
| `expires_at` | 过期时间（ISO 8601，到秒） |

### 示例

```bash
ml auth status
```

---

## `ml env`

管理运行环境（profile）。环境定义在 `config.json` 的 `profiles` 数组中，`current` 字段标记当前激活环境。

### `ml env list`

列出全部环境。

```text
ml env list
```

输出字段：`current`（`*` 表示当前）、`name`、`api_endpoint`、`output_format`、`verify_ssl`。

### `ml env show`

显示当前环境的完整信息。

```text
ml env show
```

输出字段：`name`、`api_endpoint`、`base_url`、`output_format`、`verify_ssl`。

### `ml env use`

切换当前环境（修改 `config.json` 中的 `current` 字段并落盘）。

```text
ml env use [NAME]
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 目标环境名（必须存在于 `profiles`） |

### 示例

```bash
ml env list
ml env show
ml env use dev
```

---

## `ml business`

管理部门、租户（服务）和团队上下文。所有平台业务请求都会统一携带当前选择对应的 `ai-businessId` 请求头。

> 业务命令要求**至少选择租户**，不能只选择部门；团队仅当其 `teamStatus` 为 `available` 时才允许选择。部门/租户/团队名称取值优先级见 `ml business list` 输出。

### `ml business list`

显示当前环境可见的部门、租户、团队目录，并标记当前选择（`*当前`）。

```text
ml business list
```

### `ml business show`

显示当前已选的租户或团队上下文。

```text
ml business show
```

输出字段：`type`、`department`、`tenant`、`team`、`businessId`。

### `ml business use`

交互式或通过 ID 选择租户/团队。

```text
ml business use [OPTIONS]
```

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--tenant TEXT` | `None` | 租户 ID（`ai-businessList[].value`） |
| `--team TEXT` | `None` | 团队 ID 或 key |
| `--department TEXT` | `None` | 部门 ID，用于消除重复租户 ID 的歧义 |

> 不带任何参数时，按「部门 → 租户 → 租户级或团队级」顺序交互选择。
> 若只传 `--team` 或 `--department` 而未传 `--tenant`，命令会报错：**不能仅选择部门或团队，请同时通过 `--tenant` 指定租户**。

### `ml business refresh`

打开 Edge 重新读取浏览器中的业务目录并自动关闭 Edge。

```text
ml business refresh
```

> 已选团队被删除或变为非 `available` 状态时，当前选择会失效，必须重新选择。旧版 `business.json` 不做迁移，登录或刷新时会根据浏览器缓存重新生成。

### 示例

```bash
ml business list
ml business use
ml business use --tenant mep
ml business use --tenant mep --team asdasd
ml business show
ml business refresh
```

---

## `ml user`

### `ml user info`

查询当前登录用户信息。

```text
ml user info [OPTIONS]
```

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境 `output_format`（`table`） | 输出格式：`table` 或 `json` |

### 示例

```bash
ml user info
ml user info -o json
```

---

## `ml mep`

MEP 相关管理命令。

### `ml mep config get`

查询一个 MEP 配置项。

```text
ml mep config get [KEY] [OPTIONS]
```

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` | 否 | `mep_service_access_type` | 配置项 key |

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境 `output_format`（`table`） | 输出格式：`table` 或 `json` |

> 底层请求：`POST /ai/backend/mep/config/queryConfig`，请求体 `{"key": <key>}`。

### 示例

```bash
ml mep config get
ml mep config get mep_service_access_type -o json
```

---

## `ml mtp swanboard`

训练看板项目、实验和实验数据查询。所有命令使用当前业务上下文的 `businessId`，并统一携带认证信息和 `businessid` 请求头。

```text
ml mtp swanboard project list [OPTIONS]
ml mtp swanboard project namespace list PROJECT_ID [OPTIONS]
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID [OPTIONS]

ml mtp swanboard experiment feature list EXPERIMENT_ID [OPTIONS]
ml mtp swanboard experiment environment get EXPERIMENT_ID [OPTIONS]
ml mtp swanboard experiment metrics EXPERIMENT_ID [OPTIONS]
ml mtp swanboard experiment config list EXPERIMENT_ID [OPTIONS]
ml mtp swanboard experiment inspect EXPERIMENT_ID [OPTIONS]
```

项目列表支持 `--page`、`--page-size`、`--team-id`、`--creator`，表格依次展示项目 id、项目名称、项目描述、创建者和创建时间；项目空间列表在实验 id 后展示实验名称（`namespaceName`）；特性列表支持 `--page`、`--page-size`。所有命令支持 `--output` / `-o` 输出 table 或 json。

`metrics` 默认查询 `loss` 和 `accuracy`，可通过重复传递 `--tag` 指定指标。表格将最大值、最小值和平均值格式化为四位小数。

`environment get` 展示 Python 版本、系统硬件 CPU、系统硬件 Memory 和 Python 库名称；Python 库数组在表格中按换行显示。`inspect` 一次输出实验特性、环境、指标和配置四个区块。

### 示例

```bash
# 查询训练看板项目；支持分页、团队和创建者筛选
ml mtp swanboard project list --page 1 --page-size 10
ml mtp swanboard project list --page 2 --page-size 20 --team-id team-a --creator a123456

# 查询项目下全部项目空间
ml mtp swanboard project namespace list dbbe11c4-5217-408e-89fb-8a8c148b32fd

# 查询项目空间下全部实验
ml mtp swanboard project experiment list \
  dbbe11c4-5217-408e-89fb-8a8c148b32fd \
  76a30af2-8955-4a8b-b547-dc6c13cf2039

# 分别查询实验数据
ml mtp swanboard experiment feature list 1b115cc7-6627-4fd0-a2f1-a020b4d83bce --page 1 --page-size 10
ml mtp swanboard experiment environment get 1b115cc7-6627-4fd0-a2f1-a020b4d83bce
ml mtp swanboard experiment metrics 1b115cc7-6627-4fd0-a2f1-a020b4d83bce
ml mtp swanboard experiment metrics 1b115cc7-6627-4fd0-a2f1-a020b4d83bce --tag loss
ml mtp swanboard experiment config list 1b115cc7-6627-4fd0-a2f1-a020b4d83bce

# 一次性查询特性、环境、loss/accuracy 指标和配置
ml mtp swanboard experiment inspect 1b115cc7-6627-4fd0-a2f1-a020b4d83bce

# 获取可供脚本消费的 JSON
ml mtp swanboard experiment inspect 1b115cc7-6627-4fd0-a2f1-a020b4d83bce --output json
```

---

## `ml offline`

离线业务管理命令。

### `ml offline experiment list`

分页查询离线实验（当前业务上下文内）。

```text
ml offline experiment list [OPTIONS]
```

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--page` | — | `1` | 开始页码（≥ 1） |
| `--page-size` | — | `10` | 每页记录数（≥ 1） |
| `--name`, `--project-name` | — | `None` | 按实验名称模糊查询 |
| `--description` | — | `None` | 按描述模糊查询 |
| `--create-user` | — | `None` | 按创建者模糊查询 |
| `--update-user` | — | `None` | 按修改者模糊查询 |
| `--team-id` | — | `None` | 按团队 ID 模糊查询 |
| `--output` | `-o` | 当前环境 `output_format`（`table`） | 输出格式：`table` 或 `json` |

> 表格列为：`projectId`、`实验名称`、`描述`、`创建者`、`修改者`、`创建时间`、`更新时间`、`运行配置模板`。

### `ml offline experiment trial list`

分页查询指定离线实验下的 trial。

```text
ml offline experiment trial list [PROJECT_ID] [OPTIONS]
```

| 参数/选项 | 默认值 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | （必填） | 离线实验 `projectId` |
| `--page` | `1` | 开始页码（≥ 1） |
| `--page-size` | `10` | 每页记录数（≥ 1） |
| `--name` | `None` | 按 trial 名称模糊查询 |
| `--type` | `None` | 按 trial 类型模糊查询 |
| `--creator` | `None` | 按创建者模糊查询 |
| `--updater` | `None` | 按修改者模糊查询 |
| `--ai-module` | `None` | 按 AI 模块模糊查询 |
| `--output`, `-o` | 当前环境 `output_format`（`table`） | 输出格式：`table` 或 `json` |

> 表格仅展示：`trial名称`、`类型`、`创建者`、`修改者`、`创建时间`、`更新时间`、`调度状态`、`描述`。其中 `batch` 显示为“批式”，其他类型显示为“流式”；调度状态的 `true` 显示为“调度开启”、`false` 显示为“调度停止”，其他值显示为 `-`。

### `ml offline experiment clone`

查询源实验详情并同步克隆，**仅修改实验名称**（其余字段如 `businessId`、`teamId`、`configId` 等保持原样）。

```text
ml offline experiment clone [PROJECT_ID] [OPTIONS]
```

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | 是 | 源实验 `projectId` |

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--name` | — | （必填） | 克隆后的实验名称 |
| `--yes` | `-y` | `False` | 跳过克隆确认 |
| `--dry-run` | — | `False` | 仅展示构造出的创建请求，不执行克隆 |
| `--output` | `-o` | 当前环境 `output_format`（`table`） | 输出格式：`table` 或 `json` |

> 源实验必须属于当前业务上下文（已选租户/团队），否则报错。
> 不带 `--yes` 且不带 `--dry-run` 时，会先打印源/新实验名称、运行配置模板、`businessId`、`团队 ID`，再交互确认。

### 示例

```bash
ml offline experiment list --page 1 --page-size 20 --name "训练"
ml offline experiment trial list abc123 --type batch --page-size 20
ml offline experiment clone abc123 --name "训练-副本"
ml offline experiment clone abc123 --name "训练-副本" -y
ml offline experiment clone abc123 --name "训练-副本" --dry-run
```

---

## 配置文件

`config.json` 是默认配置的唯一来源。顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `current` | string | 当前激活环境名（必须存在于 `profiles`） |
| `api.timeout` | int(ms) | 请求超时，默认 30000 |
| `api.retry_times` | int | 失败重试次数，默认 3 |
| `api.verify_ssl` | bool | 全局 HTTPS 证书校验，默认 `true` |
| `auth.expires_in_seconds` | int | 认证有效期，默认 1800 |
| `browser.channel` | string | Edge 通道：`msedge` / `msedge-beta` / `msedge-dev` / `msedge-canary` |
| `browser.session_probe_timeout` | int(ms) | 登录轮询探测超时，默认 5000 |
| `browser.login_timeout` | int(ms) | 等待用户登录超时，默认 300000 |
| `browser.business_catalog_timeout` | int(ms) | 读取业务目录超时，默认 30000 |
| `profiles[]` | array | 环境列表 |
| `profiles[].name` | string | 环境名（唯一） |
| `profiles[].api_endpoint` | string | 环境 API 地址（http/https） |
| `profiles[].output_format` | string | `table` 或 `json` |
| `profiles[].verify_ssl` | bool? | 覆盖全局证书校验；省略则继承全局 |

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

> 关闭证书校验（`verify_ssl: false`）只应用于显式配置的环境，并同时作用于平台接口请求和 Playwright 启动的持久化 Edge 上下文；**只建议用于完全可信的内部网络**。

---

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 成功（`--version`、`-h` 等正常退出同理） |
| `1` | 任意错误（认证失败、配置无效、网络/接口错误、用户取消等），错误以红色输出到 stderr |

---

## 提示与坑

- **登录依赖 Microsoft Edge**：`ml` 使用系统安装的 Edge 专用 Profile 登录，不需要 `playwright install chromium`，但必须安装 Edge。
- **认证会自动续期**：过期时优先复用已有平台会话；仅当平台会话真正失效时才要求重新登录/输入验证码。
- **业务上下文是先决条件**：除 `login` / `logout` / `env` / `auth status` 外，所有业务命令都要求先 `ml business use` 选择租户或团队，否则会报「尚未选择租户或团队」。
- **`--tenant` 是必选项组合**：只传 `--team` 或 `--department` 而不传 `--tenant` 会被拒绝。
- **输出格式控制**：带 `-o` / `--output` 的命令可临时切换 `table` / `json`；不传时跟随当前环境的 `output_format`。`env`、`business`、`auth status` 固定以表格输出。
- **配置会被自动覆盖**：升级 `wisemlops-cli` 或默认 `config.json` 变化后，首次运行会覆盖用户配置目录的 `config.json`；自定义环境请提前备份。
- **克隆实验只改名称**：`offline experiment clone` 会完整复制源实验的 `businessId`、`teamId`、运行配置等；务必确认源实验属于当前业务上下文。

---

## 参见

- [项目 README](../README.md) — 安装、Windows 一键发布与安装、配置说明
- [Windows 安装说明](../scripts/windows/INSTALL.md) — `install.cmd` 详细步骤
- [需求与设计规格](./REQUIREMENTS_DESIGN_SPEC.md) — 详细功能设计文档
