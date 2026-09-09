# 命令行参考使用指南

`ml` 是 **WiseMLOps 平台** 的 Python 命令行客户端（包名 `wisemlops-cli`，当前版本 `0.3.32`）。
本文档按当前源码及命令帮助核对（2026-09-08），覆盖全部 31 个可执行子命令、参数、配置项与退出行为。示例中的 `TASK_ID`、`JOB_ID`、`PROJECT_ID`、`NAMESPACE_ID`、`EXPERIMENT_ID`、`SET_ID` 均须替换为对应资源的真实 ID；它们不是同一种 ID。

> 阅读前提：查询平台数据前建议先完成 `ml login` 和 `ml business use`。`user`、`mep`、`mtp`、`offline`、`train`、`featureset` 需要有效认证和业务选择；`business list/use/refresh` 用于建立或维护业务上下文，不要求预先选好业务。没有认证或认证过期时，相关命令会自动启动 Edge 登录。

## 安装与首次使用

需要 Python 3.9+ 和 Microsoft Edge。Windows 安装包用户完整解压后运行 `install.cmd`，安装完成后重新打开终端；详见 [Windows 安装说明](../scripts/windows/INSTALL.md)。从源码安装时，在项目根目录执行：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/ml --version
```

以上为 macOS/Linux 示例；Windows 可使用 `py -m venv .venv` 和 `.venv\Scripts\python.exe -m pip install -e .`，随后使用 `.venv\Scripts\ml.exe`。激活虚拟环境后可直接运行 `ml`。无需安装额外的 Playwright Chromium 浏览器。

```bash
ml --version
ml env list
ml env use dev
ml login
ml business list
ml business use
ml business show
ml train list
```

将 `dev` 换成配置中存在的环境名。登录可能恢复浏览器中已有的有效业务选择，可先用 `ml business show` 核实；切换环境后需检查新环境的认证和业务选择。

## 阅读导航

- 基础操作：全局用法、命令总览、全局选项、登录与认证、环境、业务上下文。
- 数据查询：用户、MEP、训练看板、离线实验、训练任务与日志、特征集列表及配置。
- 配置与排错：配置文件、本地文件与输出约定、退出码、提示与坑。

---

## 全局用法

```text
ml - WiseMLOps平台命令行客户端

用法：ml [OPTIONS] COMMAND [ARGS]...

选项：
  --config PATH      config.json 路径，也可使用 ML_CONFIG 环境变量
  --version          显示版本
  --help             显示帮助信息并退出

命令：
  login              打开 Edge 登录并刷新当前环境的本地认证信息
  logout             清除当前环境的本地认证信息
  auth               查看认证状态
  business           管理部门、租户和团队
  env                管理运行环境
  user               用户信息
  mep                MEP 管理
  mtp                MTP 管理（训练看板）
  offline            离线业务管理
  train              训练任务查询
  featureset         特征集查询
```

`ml` 与 `ml --help` 会打印顶层用法。每个子命令同样接受 `--help`；当前版本不支持 `-h`。上面省略了框架提供的 `--install-completion` / `--show-completion` 补全选项，完整选项以 `ml --help` 为准。

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
| `ml mtp swanboard project namespace list PROJECT_ID` | 查询项目空间 |
| `ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID` | 查询项目空间下的实验 |
| `ml mtp swanboard experiment feature list EXPERIMENT_ID` | 分页查询实验特性 |
| `ml mtp swanboard experiment environment get EXPERIMENT_ID` | 查询实验环境 |
| `ml mtp swanboard experiment metrics EXPERIMENT_ID` | 查询指定指标的统计信息 |
| `ml mtp swanboard experiment config list EXPERIMENT_ID` | 查询实验配置 |
| `ml mtp swanboard experiment inspect EXPERIMENT_ID` | 汇总特性第一页、环境、默认指标和配置 |
| `ml offline experiment list` | 分页查询离线实验 |
| `ml offline experiment trial list <project_id>` | 分页查询一个离线实验下的 trial |
| `ml offline experiment clone <project_id>` | 按源实验配置创建新名称的离线实验 |
| `ml train list` | 分页查询训练任务 |
| `ml train instance list TASK_ID` | 查询执行实例，固定第一页 10 条 |
| `ml train history list TASK_ID` | 查询执行记录，固定第一页 10 条 |
| `ml train history logs download TASK_ID JOB_ID` | 下载执行记录日志 |
| `ml train config update TASK_ID --customize-config VALUE` | 更新训练任务自定义参数 |
| `ml featureset wide list` | 分页查询宽表特征集 |
| `ml featureset model list` | 分页查询模型特征集 |
| `ml featureset wide config SET_ID` | 查询宽表特征集配置，固定 JSON 输出 |
| `ml featureset model config SET_ID` | 查询模型特征集配置，固定 JSON 输出 |

---

## 全局选项

`--config` 必须写在子命令之前，例如 `ml --config ./config.json train list -o json`。`--output` 是部分末级命令的选项，不是全局选项。

| 选项 | 环境变量 | 说明 |
| --- | --- | --- |
| `--config PATH` | `ML_CONFIG` | 指定 `config.json` 路径；文件必须存在且为合法 JSON |
| `--version` | — | 打印 `ml <版本号>` 后退出 |
| `--help` | — | 打印对应命令的用法后退出 |

> 配置文件解析优先级：`--config` → `ML_CONFIG` → 当前工作目录的 `config.json` → 用户配置目录的 `config.json`（Windows `%APPDATA%\ml\config.json`、macOS `~/Library/Application Support/ml/config.json`、Linux `$XDG_CONFIG_HOME/ml/config.json`，未设置时为 `~/.config/ml/config.json`）。
> Windows 安装器每次安装均立即用包内 `config.json` 完整覆盖用户默认配置，包括同版本重装和 `access_control`。直接 pip 安装在首次读取默认配置时检测并覆盖。普通后续运行不重复覆盖。`--config`、`ML_CONFIG` 及当前目录文件仍属于独立配置，不作为安装器覆盖目标。

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
- 若平台接口返回 401 / 403 / 419 / 440 或 HTTP 重定向，会刷新认证并重试整次业务操作一次；再次失败则报错。
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

显示当前环境的认证有效期与基础信息，不打印 Cookie 或 Token。该命令只读本地缓存，不自动续期；无缓存时退出码为 1，缓存过期时仍成功输出 `expired`。

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
| `business_id` | 认证缓存记录的业务 ID；实际请求使用 `business.json` 的有效选择，以 `ml business show` 为准 |
| `status` | `valid` 或 `expired` |
| `remaining_seconds` | 距过期剩余秒数 |
| `acquired_at` | 获取时间（当前机器本地时区，ISO 8601，到秒，不含时区偏移） |
| `expires_at` | 过期时间（当前机器本地时区，ISO 8601，到秒，不含时区偏移） |

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
ml env use NAME
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

管理部门、租户（服务）和团队上下文。所有平台业务请求统一携带 `businessid` 和 `ai-businessId` 请求头，值来自用户配置目录 `business.json` 的 `profiles.<当前环境>.selected.businessId`，并校验账号与业务目录。租户级选择使用租户 ID，团队级选择使用团队记录的 `businessId`。

> 业务命令要求**至少选择租户**，不能只选择部门；团队仅当其 `teamStatus` 为 `available` 时才允许选择。部门分组名称依次取 `settleTenantName.cn`、`settleTenantName.en`、顶层 `cn`；选择时以 `ml business list` 列出的 ID 为准。

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

训练看板使用当前环境的认证与业务选择。推荐按“项目 → 项目空间 → 实验 → 实验数据”查询。所有下列命令均支持 `--output` / `-o`（`table` 或 `json`），默认使用环境的 `output_format`；筛选团队不会切换当前业务上下文。

### `ml mtp swanboard project list`

分页查询项目，每次只请求一页。

```bash
ml mtp swanboard project list
ml mtp swanboard project list --page 2 --page-size 20 --team-id team-a --creator a123456 -o json
```

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--page` | `1` | 页码，≥ 1 |
| `--page-size` | `10` | 每页条数，≥ 1 |
| `--team-id` | 空字符串 | 团队 ID 模糊查询 |
| `--creator` | 空字符串 | 创建者模糊查询 |

表格列：项目 id（`projectId`）、项目名称、项目描述、创建者、创建时间。JSON 包含 `page`、`pageSize`、`count`、`items`，保留记录额外字段。

### `ml mtp swanboard project namespace list`

```bash
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project namespace list PROJECT_ID --team-id team-a -o json
```

`PROJECT_ID` 必填，来自项目列表的 `projectId`。可选 `--team-id` 默认为空字符串；不支持分页选项，单次调用项目空间查询接口。

表格列：项目空间 id（`namespaceId`）、实验 id（实际取响应的 `projectId`）、实验名称（`namespaceName`）、描述、创建时间。这里表头“实验 id”并非后续实验数据命令需要的 `experimentId`。JSON 为 `page`、`pageSize`、`count`、`items`，其中本地默认 `page=1`、`pageSize=0`，不代表结果为空。

### `ml mtp swanboard project experiment list`

```bash
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID --team-id team-a -o json
```

两个位置参数均必填，依次为项目 `projectId`、项目空间 `namespaceId`。可选 `--team-id` 默认为空字符串。当前没有分页选项，也不会自动遍历：只展示服务端单次返回的 `result.data.list`，不能据此保证取得全部实验。

表格列：项目实验 id（`experimentId`）、实验名称、创建时间。JSON 包含 `pageNum`、`pageSize`、`total`、`totalPages`、`items`；服务端未返回的分页值可能为 `null`。后续实验数据命令使用这里的 `experimentId`。

### `ml mtp swanboard experiment feature list`

```bash
ml mtp swanboard experiment feature list EXPERIMENT_ID --page 1 --page-size 10
ml mtp swanboard experiment feature list EXPERIMENT_ID --page 2 -o json
```

`EXPERIMENT_ID` 必填。`--page` 默认 `1`，`--page-size` 默认 `10`，均须 ≥ 1；只查询指定页。表格展示特征名（`featureName`）和扩展参数（`featuresConfig`）。JSON 包含 `page`、`pageSize`、`count`、`items`。

### `ml mtp swanboard experiment environment get`

```bash
ml mtp swanboard experiment environment get EXPERIMENT_ID
ml mtp swanboard experiment environment get EXPERIMENT_ID -o json
```

`EXPERIMENT_ID` 必填，无其他查询参数。表格展示 Python 版本、系统硬件 CPU（`cpu.brand`）、系统硬件 Memory 和 Python 库名称；库数组按换行显示。JSON 输出环境对象，服务端环境数据为空数组时转为 `{}`。

### `ml mtp swanboard experiment metrics`

```bash
ml mtp swanboard experiment metrics EXPERIMENT_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy -o json
```

`EXPERIMENT_ID` 必填。`--tag` 可重复，不传时查询 `loss` 和 `accuracy`；显式传入时替换默认列表。每个指标分别请求一次。表格展示指标名称、最大值、最小值、平均值，数值保留四位小数，非数值显示 `-`。JSON 输出统计对象数组，保留原始精度；此命令不查询完整指标时间序列。

### `ml mtp swanboard experiment config list`

```bash
ml mtp swanboard experiment config list EXPERIMENT_ID
ml mtp swanboard experiment config list EXPERIMENT_ID -o json
```

`EXPERIMENT_ID` 必填，无其他查询参数。表格逐项展示配置项与值；配置项为对象时取其 `value` 字段。JSON 保留配置对象的完整结构。

### `ml mtp swanboard experiment inspect`

```bash
ml mtp swanboard experiment inspect EXPERIMENT_ID
ml mtp swanboard experiment inspect EXPERIMENT_ID -o json
```

`EXPERIMENT_ID` 必填，仅支持输出选项。一次依次查询特性、环境、`loss`、`accuracy` 和配置，共五次接口调用；任一查询失败则整条命令报错。

表格输出“实验特性”“实验环境”“指标信息”“实验配置”四个区块。JSON 对象包含 `features`、`environment`、`metrics`、`config`。**特性仅查询第 1 页 10 条**，并非完整导出；需要其他页时使用 `feature list`。`inspect` 不接受 `--page`、`--page-size` 或 `--tag`。

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
ml offline experiment trial list PROJECT_ID [OPTIONS]
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

按源实验的业务与运行配置创建一个新实验，允许用户指定新名称。保留 `description`、`businessId`、`region`、`subDomain`、`serviceChannel`、`teamId`、`clusterName`、`configId`、`configName`（空值回退为空字符串）；清空新请求的 `projectId`，将 `createUser` 和 `updateUser` 设为当前账号，并生成请求 UUID。它不是逐字段复制整个源响应，也不会复制 trial。

```text
ml offline experiment clone PROJECT_ID [OPTIONS]
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
> 不带 `--yes` 且不带 `--dry-run` 时，会先打印源/新实验名称、运行配置模板、`businessId`、`团队 ID`，再交互确认。回答否会输出“已取消克隆”，退出码为 0。
> `--dry-run` 仍会认证、读取源实验并校验业务归属，但不发送创建请求；输出 `dryRun` 和 `request`。成功创建输出 `sourceProjectId`、新 `projectId`（接口未提供时为 `-`）、`projectName`、`uuid` 和 `message`。

### 示例

```bash
ml offline experiment list --page 1 --page-size 20 --name "训练"
ml offline experiment trial list abc123 --type batch --page-size 20
ml offline experiment clone abc123 --name "训练-副本"
ml offline experiment clone abc123 --name "训练-副本" -y
ml offline experiment clone abc123 --name "训练-副本" --dry-run
```

---

## `ml train`：训练任务、执行实例与日志

所有命令使用当前环境的有效认证及业务选择。先用 `ml train list` 获取 `taskId`；执行实例和执行记录返回 `jobId`，下载日志时须同时提供所属任务 ID 与执行记录 ID。

### `ml train config update`

先查询训练任务详情，再更新自定义参数，执行命令即提交更新。任务名称从详情读取，不再提供 `--name`。
使用前须完成当前环境登录及业务选择（`ml login`、`ml business use`）。
业务 ID 和请求头 `businessid` 来自当前环境 `business.json` 的 `selected.businessId`，
修改人 `updateUser` 必须读取同一环境的 `username`，不从其他环境或认证文件补全。
缺少业务选择、缺少用户名或账号不匹配时不提交更新，并提示登录或刷新业务信息。

```powershell
ml train config update a9a49cc3-9dd1-4ef8-a4f5-4ebd11b42c6d --customize-config "96999"
ml train config update a9a49cc3-9dd1-4ef8-a4f5-4ebd11b42c6d --customize-config "0096999"
```

| 参数或选项 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 对应 `data.id`，不允许空白 ID |
| `--customize-config VALUE` | 是 | 对应 `data.taskInfo.parameter.customizeConfig`，原样传递字符串；不转换为数字或 JSON，保留前导零和空格；空字符串也原样提交 |

请求使用当前 `api_endpoint`。先 POST 到 `/ai/backend/modelDev/modelTrain/detailNew`，
请求体为 `{"data":{"id":"用户输入的任务 ID","businessId":"当前业务 ID","teamId":""}}`。
详情响应必须满足 `code=0` 且 `des=success`；否则停止，不发送更新。
更新请求的 `data.name` 取详情的 `result.data.name`，`data.taskInfo` 完整复制
`result.data.taskInfo`，仅替换其中的 `parameter.customizeConfig` 和修改人 `updateUser`。
其他嵌套字段全部保留；parameter 缺失或为 null 时创建对象，其他非对象值报错。
随后 POST 到 `/ai/backend/modelDev/modelTrain/updateNew`，
`creator`、`modifier` 固定为空字符串。仅当 `result.code` 为数字 `0` 且
`result.des` 为 `success` 时，标准输出打印：

```text
更新训练任务自定义参数成功！
```

否则显示 `更新训练任务自定义参数失败：code=...，des=...` 并非零退出。
缺少响应结构、HTTP 或网络错误同样报错；认证提示发送到 stderr。
不对一般网络失败重放更新请求；服务端拒绝认证时沿用现有刷新认证逻辑。
该命令固定输出成功文本，不提供 `--output` 选项。

### `ml train list`

```bash
ml train list
ml train list --name wiserec --page 2 --page-size 20
ml train list -o json
```

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | 不筛选名称 | 按任务名称模糊查询 |
| `--page` | `1` | 页码，≥ 1 |
| `--page-size` | `10` | 每页条数，≥ 1 |
| `--output` / `-o` | 环境 `output_format` | `table` 或 `json` |

只请求指定的一页。其他筛选保持管理台默认值，目前不接受任务类型、状态、团队、排序等选项。表格列依次为任务 ID、任务名称、任务类型、业务场景、修改者、更新时间、最新执行时间、大小、描述；空列表显示“暂无训练任务”。

### `ml train instance list`

```bash
ml train instance list TASK_ID
ml train instance list TASK_ID -o json
```

`TASK_ID` 为必填的完整任务 ID，仅支持 `--output` / `-o`。命令自动逐页扫描当前业务的训练任务，精确匹配 ID，再使用该任务响应中的 `businessId` 和 `taskType` 查询实例，不必预先运行列表命令。任务多时会产生多次查询；未找到任务或任务缺少必要字段时报错。

实例固定为第 1 页 10 条，按开始时间 `createTime` 升序，不支持翻页、排序或筛选选项。表格展示任务名称与 ID，以及作业 ID、算法名称、CPU、GPU、内存、状态、执行节点（`hostIp`）、集群、触发方式（`actionType`）、开始时间、执行时长、存储桶。

执行时长由展示时的当前时间减去开始时间计算，取整分钟，例如 85 秒显示 `1min`；不足一分钟或未来开始时间显示 `0min`，缺少开始时间显示 `-`。它并非服务端记录的实际结束耗时；JSON 的 `runningTime` 保留原值。空列表显示“暂无执行实例”。

### `ml train history list`

```bash
ml train history list TASK_ID
ml train history list TASK_ID -o json
```

`TASK_ID` 必填，仅支持 `--output` / `-o`。直接按任务 ID 查询执行记录，不扫描任务列表。固定第 1 页 10 条，按 `createTime` 倒序；使用 `source="history"`、`latestFlag="true"` 和空状态筛选，不支持分页、排序或筛选选项。

表格列：作业 ID、算法名称、CPU、GPU、内存、状态、集群、节点数、执行时长、大小、检查时间（`checkTime`）、开始时间（`createTime`）、结束时间（`statusTime`）、触发方式、存储桶。执行时长保留接口 `runningTime` 原值。空列表显示“暂无执行记录”，不据此判定任务不存在。

### 三种训练列表的输出规则

- JSON 均为 `count`、`pageIndex`、`pageSize`、`items`，记录保留额外字段、空值、原始字节数和毫秒时间戳。认证提示发往 stderr，可直接保存：`ml train list -o json > train-tasks.json`。
- 表格缺失值、`null`、空字符串显示 `-`，数值零保留。毫秒时间戳转换为北京时间（UTC+8）的 `YYYY-MM-DD HH:mm:ss`。
- 大小按 1024 进制换算：零为 `0B`，不足 1 GiB 显示两位小数的 `M`，其余显示两位小数的 `G`。内存、状态和触发方式沿用响应原值，不另行推测单位或中文含义。
- 页尾展示页码、每页条数、总数和时区；实例/记录总数超过 10 时提示仅展示第一页。
- 实例和执行记录的作业 ID 首列固定宽度 36，不换行、不截断；其余长字段优先换行。任务列表的 `taskId` 列当前仍随终端布局换行，复制时可使用 JSON。

### `ml train history logs download`

```text
ml train history logs download TASK_ID JOB_ID [OPTIONS]
```

| 参数/选项 | 默认值 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 必填 | 所属训练任务 ID |
| `JOB_ID` | 必填 | 执行记录 ID，取记录中的 `jobId` |
| `--file PATH` | 当前目录下自动命名 | 指定保存文件路径，父目录必须已存在 |
| `--output` / `-o` | 环境 `output_format` | 下载结果摘要格式：`table` 或 `json` |

```bash
ml train history logs download TASK_ID JOB_ID
ml train history logs download TASK_ID JOB_ID --file ./train-logs.zip
ml train history logs download TASK_ID JOB_ID --file ./train-logs.zip -o json
```

命令直接向下载地址接口提交这两个 ID，不预先查询历史记录或在本地验证归属，也不受记录列表第一页 10 条限制。业务 ID 取当前选择，`isApplicantPromise` 固定为 `true`。只有接口返回整数 `code=0`、`des=success` 且地址为有效 HTTPS URL 时开始下载。

默认文件名取响应 `Content-Disposition`，移除目录成分及不适合文件名的字符，并补充 `.zip` 后缀；缺省为 `JOB_ID-logs.zip`。显式 `--file` 保留指定文件名，不强制补 `.zip`。文件内容原样保存，不自动解压。目标已存在时自动递增编号，如 `train-logs (1).zip`，不覆盖已有文件。

获取地址仍使用平台认证及环境证书设置；实际文件下载使用独立客户端，不携带平台 Cookie、CSRF 或业务请求头。当前下载固定关闭证书校验，不读取 `verify_ssl`；超时设为 60 秒，最多跟随 5 次 HTTPS 跳转。下载先写入同目录临时文件，接收完整后以硬链接发布最终文件，故目标文件系统须支持硬链接。

完整下载地址（含查询参数）、认证提示和进度发送到 stderr。成功摘要包含 `taskId`、`jobId`、绝对路径 `path`、字节数 `bytes`、`status="downloaded"`。`-o json` 只把 JSON 摘要写到 stdout。下载失败、传输不完整或保存失败时非零退出并清理临时文件。

---

## 配置文件

`config.json` 是默认配置的唯一来源。顶层字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `current` | string | 当前激活环境名（必须存在于 `profiles`） |
| `api.timeout` | int(ms) | 请求超时，默认 30000 |
| `api.retry_times` | int | HTTP 连接建立失败的底层重试次数，默认 3；不是所有 HTTP 错误或业务错误都重试 |
| `api.verify_ssl` | bool | 全局 HTTPS 证书校验，默认 `true` |
| `auth.expires_in_seconds` | int | 认证有效期，默认 1800 |
| `browser.profile_root` | string? | 自定义持久化浏览器目录根路径；默认用户配置目录下的 `browser-profiles` |
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

`api.verify_ssl` 是全局默认值，环境中的 `verify_ssl` 优先覆盖；最终值同时作用于平台接口和 Edge 登录上下文。日志文件下载使用独立客户端，当前固定关闭证书校验，不受此配置影响。

请求地址从当前 `profiles[].api_endpoint` 获取：完整值用于登录页和 Referer，实际接口基址取其协议、主机和端口，再连接 `/ai/...` 路径。例如配置以 `/dashboard` 结尾时，不会把 `/dashboard` 加到接口路径前。需求示例中的 `xxx` 代表该配置值，不是另一个需要配置的字段。

---

## 特征集列表

对应 Web 的“样本工程 → 特征集 → 宽表特征集 / 模型特征集”：

```bash
ml featureset wide list
ml featureset model list
ml featureset wide list --name test --page 2 --page-size 20
ml featureset model list --output json
```

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | 空字符串 | 按特征集名称查询，匹配规则由服务端决定 |
| `--page` | `1` | 页码，正整数 |
| `--page-size` | `10` | 每页条数，正整数 |
| `--output` / `-o` | 环境的 `output_format` | `table` 或 `json` |

两个入口分别固定 `setType=wide` 和 `setType=model`，每次只请求指定的一页，
不会自动遍历所有数据。接口为当前环境域名下的
`POST /ai/backend/dpp/proxy/featureStore/featureset/names`。
请求体的 `businessId` 与请求头 `businessid` 均取当前环境 `business.json` 中
已校验的 `selected.businessId`；未选择业务时提示执行 `ml business use`，不回退到 `default`。
`teamId`、`scene`、`subscene`、`operator`、`modifier`、`tagIdList` 均固定为空字符串，
即使选择团队也不填入 `teamId`，暂不支持通过选项修改这些字段。

表格列顺序为：特征集 ID、特征集名称、特征集类型、场景、创建者、创建时间、修改者、修改时间。
记录保持服务端顺序，类型显示响应原值。缺失字段、`null` 和空字符串显示 `-`。
带时区的 ISO 时间转换为北京时间 `Asia/Shanghai (UTC+08:00)`，格式为 `YYYY-MM-DD HH:mm:ss`；
例如 `2026-09-08T03:30:58.000+00:00` 显示为 `2026-09-08 11:30:58`。
非空时间无法解析或缺少时区时保留原值，并向 stderr 输出提示。
页尾展示当前页、每页条数和总记录数，合法空列表显示“暂无特征集”。

JSON 输出结构为 `{"count": 0, "pageIndex": 1, "pageSize": 10, "items": []}`，
`count` 对应接口的 `totalCount`，`items` 对应 `featureSetInfoList`。
记录保留原始时间、空值和额外字段；认证提示写入 stderr，不混入 JSON 标准输出。
业务错误或缺失、无效的列表/总数字段会报错，不会被当作空列表。

---

## 特征集配置查询

```bash
ml featureset wide config SET_ID
ml featureset model config SET_ID
ml featureset wide config 6743499e-15ec-496c-b510-ee9bf65f395e
```

`SET_ID` 为必填参数，去除首尾空白后不能为空。两个入口共用
`POST /ai/backend/dpp/proxy/featureStore/featureset/config`，直接根据 ID 查询，不预先请求列表。
请求体仅包含当前环境所选业务的 `businessId` 和指定的 `setId`，不发送 `setType`。
复用当前环境域名、认证和业务选择，请求头 `businessid` 与请求体一致；
没有有效业务选择时提示执行 `ml business use`。

仅当 `result.code` 为整数 `0` 且 `result.des` 严格等于 `success` 时响应成功。
`featureJson` 必须是非空 JSON 字符串，且解析后为对象；合法空对象 `{}` 正常输出。
缺失字段、非法 JSON 或非对象配置会报错。配置字符串只解析一次，不删除反斜杠或修复非法转义。

配置命令固定输出格式化 JSON，无需也不接受 `--output`，不受环境 `output_format` 影响。
仅打印解析后的配置对象，不包含 `version`、`meta`、`result` 等响应包装；
配置对象自身的 `version` 等字段完整保留。例如：

```json
{
  "features": [],
  "table_configs": {},
  "feature_set_name": "test_hash_239features",
  "version": "latest"
}
```

中文直接显示，嵌套结构、数组顺序和数据类型保持原样。普通下划线显示为 `_`，
不带多余转义；路径、正则表达式、引号或换行等内容所需的合法 JSON 转义仍会保留。
认证提示和错误写入 stderr，标准输出可直接重定向保存：

```bash
ml featureset model config SET_ID > featureset-config.json
```

---

## 本地文件与输出约定

用户配置目录为 Windows `%APPDATA%\ml`、macOS `~/Library/Application Support/ml`、Linux `$XDG_CONFIG_HOME/ml`（未设置时 `~/.config/ml`）。以下文件由 CLI 管理：

| 文件或目录 | 内容 |
| --- | --- |
| `config.json` | 默认环境与接口配置；显式 `--config` / `ML_CONFIG` 可指定另一份文件 |
| `credentials.json` | 按环境保存认证缓存 |
| `business.json` | 按环境保存业务目录、账号及 `selected` 选择 |
| `browser-profiles/profile-<环境名>` | 每个环境独立的 Edge 持久会话；可用 `browser.profile_root` 修改根目录 |

指定另一份配置文件不会自动迁移认证、业务目录或浏览器会话。它们默认仍使用上述用户目录，按环境名区分。

### 表格与 JSON 的区别

表格只展示各命令定义的字段，接口可能返回其他未展示数据；指南中的响应示例同样不表示接口完整结构。JSON 也不一律等于整个 HTTP 响应：

| 命令 | JSON 内容 |
| --- | --- |
| `user info`、`mep config get` | 接口 JSON 响应 |
| 训练列表、特征集列表 | 归一化分页对象，`items` 保留原始记录 |
| 离线实验与 trial 列表 | `pageIndex`、`pageSize`、`count`、`total`、`items`；记录仅保留各自固定字段 |
| 训练看板列表 | 各命令注明的分页对象；记录保留额外字段 |
| 特征集配置 | 从 `featureJson` 解析出的配置对象 |
| 克隆与日志下载 | 命令生成的操作摘要；克隆预览为 `dryRun` 和 `request` |

离线实验 JSON 记录字段为 `projectId`、`projectName`、`description`、`createUser`、`updateUser`、`createTime`、`updateTime`、`configName`。trial JSON 记录字段为 `experimentName`、`experimentType`、`creator`、`updater`、`createTime`、`updateTime`、`cronIntervalStartFlag`、`description`；当前不包含 trial ID。

当前 `train`、`featureset` 命令明确把认证提示发往 stderr。其他数据命令在触发认证刷新时仍可能向 stdout 打印提示；克隆交互提示也在 stdout，脚本使用时需考虑这些内容，不能对所有 `-o json` 命令假定 stdout 始终是纯 JSON。

### 当前展示限制

AGENTS.md 要求时间适合人类阅读、首列 ID 固定 36 宽且不换行/截断。当前实现尚未对所有旧命令统一应用：训练及特征集表格已转换北京时间；训练看板、离线实验沿用响应时间，认证状态使用机器本地 ISO 时间。固定 ID 列宽目前仅在训练执行实例与执行记录生效。其他列表复制完整 ID 时，优先使用 JSON 并加宽终端；JSON 时间通常保留原值。

---

## 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 命令成功、显示帮助/版本，或在克隆确认中回答否；`auth status` 显示 `expired` 也为 0 |
| `1` | 命令执行错误，如认证、配置解析、业务选择、网络、响应格式或保存文件失败；错误输出到 stderr |
| `2` | 命令行用法错误，如未知命令/选项、缺少必填参数、`--page 0`、不存在的 `--config` 路径；不支持的 `-h` 也属于此类 |

---

## 提示与坑

- **登录依赖 Microsoft Edge**：`ml` 使用系统安装的 Edge 专用 Profile 登录，不需要 `playwright install chromium`，但必须安装 Edge。
- **认证会自动续期**：过期时优先复用已有平台会话；仅当平台会话真正失效时才要求重新登录/输入验证码。
- **业务上下文是先决条件**：平台数据命令需要有效的租户或团队选择；提示未选择时执行 `ml business list`、`ml business use`，不要手工从其他环境复制业务 ID。
- **`--tenant` 是必选项组合**：只传 `--team` 或 `--department` 而不传 `--tenant` 会被拒绝。
- **输出格式控制**：带 `-o` / `--output` 的命令可临时切换 `table` / `json`；不传时跟随当前环境的 `output_format`。`env`、`auth status`、`business show` 固定表格；`business list` 输出层级目录，其他业务管理命令输出交互提示。特征集配置固定输出 JSON。
- **配置会被自动覆盖**：Windows 安装器每次安装均完整覆盖用户默认 `config.json`；直接 pip 安装在首次读取默认配置时同步，包括同版本重装。`access_control` 也会覆盖。
- **克隆会创建资源**：先用 `--dry-run -o json` 查看实际创建请求，再按需使用 `--yes`。源实验必须属于当前业务上下文。

---

## 参见

- [项目 README](../README.md) — 安装、Windows 一键发布与安装、配置说明
- [Windows 安装说明](../scripts/windows/INSTALL.md) — `install.cmd` 详细步骤
- [需求与设计规格](./REQUIREMENTS_DESIGN_SPEC.md) — 详细功能设计文档

## 在线访问授权：`ml access status`

默认 `config.json` 已包含 `access_control`：`enabled` 为 `false`、`url` 为空、`timeout_seconds` 为 `15`。启用时填写实际权限服务地址，并将 `enabled` 改为 `true`。

用于实时检查当前登录账号是否获准在当前环境使用 CLI 业务功能。权限管理页面和离线部署说明见 [权限服务说明](../access-service/README.md)。

使用前提：管理员已部署权限服务、创建平台账号及环境授权，并在 CLI `config.json` 顶层配置：

```json
"access_control": {
  "enabled": true,
  "url": "https://permissions.internal:8008/cli-permission",
  "timeout_seconds": 15
}
```

权限服务地址支持 HTTP 或 HTTPS，并统一使用 `/cli-permission` 前缀。可信内网使用 HTTP 时，服务配置 `COOKIE_SECURE=false` 并清空两个 TLS 路径。`enabled` 是布尔值（对象存在时默认 true），`timeout_seconds` 为 1–120 秒（默认 15）。没有该对象时兼容旧版不执行在线检查；生产分发需由管理员启用，安装时默认配置全部以包内文件为准，不保留既有设置。客户端配置可被本地修改，此机制不替代业务平台或网关的权限校验。

```bash
ml login
ml business use
ml access status
# 也可明确指定配置
ml --config ./config.json access status
```

该命令无位置参数和专有选项，支持通用 `--config`。调用权限接口时，`businessid` 取当前环境 `business.json` 的 `selected.businessId`；账号 `username` 取当前环境本地登录缓存，权限服务信任该账号并查询授权，不再调用平台 `/ai/user/info`。权限请求不发送 Cookie 或 CSRF。CLI 与权限服务需同时更新，旧 CLI 缺少账号字段会收到 HTTP 422；本次无需数据库迁移。

成功输出：`当前账号已获当前环境访问授权。` 未启用时输出配置提示；未授权、停用、过期、身份不一致或网络异常时打印具体类别的错误并返回非零退出码。未登录或未选择业务时，按原有登录和业务选择流程完成初始化。

启用后，业务查询、更新、获取日志下载地址等命令会在执行前自动进行相同检查；拒绝或故障均停止业务调用。每条业务命令重新检查，撤销对下一条命令生效。帮助、版本、登录退出、环境选择和本地业务上下文操作不依赖在线授权，以免阻塞初始化。

权限服务采用 HTTPS 时仍校验证书，不沿用日志下载的 `verify_ssl: false`。内网 CA 可通过 CLI 进程的 `SSL_CERT_FILE` 指向包含企业 CA 的信任证书包。

### 调用日志与多环境授权

管理员可在「访问授权」一次为同一账号勾选多个环境；切换环境后 CLI 按当前环境检查授权。
每次在线检查由权限服务写入 MySQL，并可在「CLI 调用日志」按账号、环境、命令、授权结果、时间查询。
新版 CLI 仅上报命令名称，例如 `ml train list`，不记录位置参数、密码、Cookie 或自定义参数内容。
该日志表示命令发起时的授权检查，不表示业务执行结果；帮助、登录和本地配置等未经过检查的操作不在记录范围内。
请求未提供命令名称时日志显示 `unknown`；未提供账号 `username` 的旧客户端无法使用新权限接口。

## 执行训练任务：`ml train start <task-id>`

立即执行指定训练任务。使用前需完成 `ml login` 和 `ml business use`；如启用了在线权限检查，当前用户还须获准访问当前环境。

| 参数 | 必填 | 说明 |
|---|---|---|
| `task-id` | 是 | 训练任务 ID，直接提交给执行接口；不预先查询列表，不要求本地校验 UUID 格式 |

```bash
ml train start aaaa83b8-5669-43a7-a62c-97ccf877e732
ml --config ./config.json train start aaaa83b8-5669-43a7-a62c-97ccf877e732
```

无专有选项；输入命令即发起执行，不再二次确认。输出固定为文本，不受环境默认 JSON 输出设置影响。

调用 `POST /ai/backend/modelDev/modelTrain/startScheduleTask`，接口基础地址沿用当前环境 `api_endpoint` 的构造规则。
请求头 `businessid` 来自当前环境 `business.json` 的 `selected.businessId`，认证信息复用当前登录。
请求体包含 `version="1.0"`、每次请求新生成的 `meta.uuid` 以及 `data.taskId`。
权限服务日志记录命令名称 `ml train start`，不包含 task-id。

仅当 `result.code` 为整数 `0` 且 `result.des` 为 `success` 时，输出：

```text
训练任务执行成功，jobId：8e348580-e889-4d1a-80d3-8d52b17a7004
```

若成功响应没有有效 jobId，输出“训练任务执行成功，但接口未返回有效 jobId，请查询执行记录确认。”。
业务失败显示接口的 code 和 des，退出码为非零。执行成功表示接口接受本次执行操作，不表示训练已经完成。

对于提交后的超时、传输错误、认证拒绝或其他无法确认结果的 HTTP 错误，不自动重发执行请求，先查询：

```bash
ml train history list aaaa83b8-5669-43a7-a62c-97ccf877e732
```

执行接口发出之前，权限检查发生登录失效时仍可按既有机制重新登录。底层只允许原有连接建立阶段的重试，不对已发送的执行请求自动重放。


### 权限检查故障定位

`GET /cli-permission/healthz` 正常不代表 `POST /cli-permission/api/v1/access/check` 正常。权限检查分别提示连接超时、等待响应超时、连接失败、HTTP 协议异常以及 HTTP 200 非 JSON 响应；不会输出原始异常或响应正文。等待响应超时应检查权限服务日志、数据库和 `access_control.timeout_seconds`；HTTP 200 非 JSON 应检查权限接口路由或网关是否返回 HTML 页面。


### 权限连接诊断（0.3.31）

当健康检查或 curl 正常但 CLI 报错时，可执行：

```powershell
ml --config "C:\Users\l00123456\AppData\Roaming\ml\config.json" access status --diagnose
```

需先完成登录和业务选择。`--diagnose` 显示配置路径、版本、请求 URL、当前账号、环境、平台源地址、businessid、连接目标、可获取的 TCP 对端、HTTP 状态、请求耗时和 Server/Via 等有限响应头。连接目标可能是代理；对端仅代表直接连接的节点，响应头不能证明整个转发链。连接失败时可能没有对端或响应头。

诊断不额外改变请求策略；权限请求默认直连，只有 `use_env_proxy: true` 时使用环境代理；不输出 Cookie、CSRF、完整请求头或响应正文。输出包含内部地址与账号，分享时按需隐藏。诊断失败仍阻止业务请求，退出码沿用原有规则。


### 权限服务前缀与默认直连（0.3.31）

```json
"access_control": {
  "enabled": true,
  "url": "https://管理域名/cli-permission",
  "timeout_seconds": 15,
  "use_env_proxy": false
}
```

权限服务请求统一为 `/cli-permission/api/v1/access/check`。URL 仅允许纯源地址或 `/cli-permission` 路径（可带尾斜杠）；纯源地址自动补齐前缀，不影响业务平台 `api_endpoint`。需同步升级权限服务，管理入口为 `/cli-permission/`，健康检查为 `/cli-permission/healthz`。

`use_env_proxy` 为可选布尔值，默认 false：权限检查直接连接服务地址，不读取环境代理、不修改系统设置，其他业务请求保持原有行为。只有明确配置 true 才使用环境代理。默认直连仍支持 SSL_CERT_FILE、SSL_CERT_DIR 企业 CA，并校验证书。直连失败不会自动切换代理；可使用 `--diagnose` 查看当前模式及连接目标。
