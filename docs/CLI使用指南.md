# CLI 使用指南

`ml` 是 WiseRec 平台的命令行客户端（包名 `wiserec-cli`，当前版本 `1.0.3`）。本指南覆盖全部命令的格式、参数与示例，供快速查询。

查询平台数据前，先完成 `ml login` 和 `ml business use`。示例中的 `TASK_ID`、`JOB_ID`、`PROJECT_ID`、`NAMESPACE_ID`、`EXPERIMENT_ID`、`SET_ID`、`ENV_ID` 均须替换为真实 ID，它们不是同一种 ID。

---

## 阅读导航

| 需要做什么 | 查看章节 |
| --- | --- |
| 了解命令行的整体写法与保留选项 | 全局用法、全局选项 |
| 按用途找到命令 | 命令总览 |
| 登录、退出、查看认证与授权状态 | 登录与认证 |
| 切换环境 | 运行环境 |
| 选择部门、租户、团队 | 业务上下文 |
| 查询账号信息与 MEP 配置 | 用户与 MEP |
| 查询训练看板项目与实验 | 训练看板 |
| 查询与克隆离线实验 | 离线实验 |
| 执行训练任务、查实例与日志 | 训练任务 |
| 查询特征集与特征集配置 | 特征集 |
| 执行 Notebook、连接远程终端 | Jupyter |
| 查询 Web Studio 实例与动态登录 | Web Studio |

---

## 全局用法

```text
ml - WiseRec平台命令行客户端

用法：ml [OPTIONS] COMMAND [ARGS]...

选项：
  --config PATH      config.json 路径，也可使用 ML_CONFIG 环境变量
  --version          显示版本
  --help             显示帮助信息并退出

命令：
  login              打开 Edge 登录并刷新当前环境的本地认证信息
  logout             清除当前环境的本地认证信息
  auth               查看认证状态
  access             检查 CLI 在线访问授权
  business           管理部门、租户和团队
  env                管理运行环境
  user               用户信息
  mep                MEP 管理
  mtp                MTP 管理
  offline            离线业务管理
  train              训练任务查询与执行管理
  featureset         特征集查询
  jupyter            Jupyter Notebook 前台执行与 Terminal
  webstudio          Web Studio 查询与 Jupyter 动态登录
```

`ml` 与 `ml --help` 打印顶层用法。每个子命令同样接受 `--help`；当前版本不支持 `-h`。

---

## 命令总览

### 登录与认证

| 命令 | 作用 |
| --- | --- |
| `ml login` | 打开 Edge 登录并刷新当前环境的本地认证信息 |
| `ml logout` | 清除当前环境的本地认证信息 |
| `ml auth status` | 显示当前环境的认证有效期，不显示敏感值 |
| `ml access status` | 实时检查当前平台账号及环境的访问授权 |

### 运行环境

| 命令 | 作用 |
| --- | --- |
| `ml env list` | 列出全部环境 |
| `ml env show` | 显示当前环境 |
| `ml env use NAME` | 切换当前环境 |

### 业务上下文

| 命令 | 作用 |
| --- | --- |
| `ml business list` | 显示当前环境可见的部门、租户和团队目录 |
| `ml business show` | 显示当前租户或团队上下文 |
| `ml business use` | 交互式或通过 ID 选择租户/团队 |
| `ml business refresh` | 打开 Edge 刷新当前环境的业务目录 |

### 用户与 MEP

| 命令 | 作用 |
| --- | --- |
| `ml user info` | 查询当前登录用户信息 |
| `ml mep config get [KEY]` | 查询一个 MEP 配置项 |

### 训练看板

| 命令 | 作用 |
| --- | --- |
| `ml mtp swanboard project list` | 分页查询项目 |
| `ml mtp swanboard project namespace list PROJECT_ID` | 查询项目下的全部项目空间 |
| `ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID` | 查询项目空间下的全部实验 |
| `ml mtp swanboard experiment feature list EXPERIMENT_ID` | 分页查询实验特性 |
| `ml mtp swanboard experiment environment get EXPERIMENT_ID` | 查询实验环境 |
| `ml mtp swanboard experiment metrics EXPERIMENT_ID` | 查询实验指标统计 |
| `ml mtp swanboard experiment config list EXPERIMENT_ID` | 查询实验配置 |
| `ml mtp swanboard experiment inspect EXPERIMENT_ID` | 一次性查询特性、环境、指标和配置 |

### 离线实验

| 命令 | 作用 |
| --- | --- |
| `ml offline experiment list` | 分页查询离线实验 |
| `ml offline experiment trial list PROJECT_ID` | 分页查询某个离线实验下的 trial |
| `ml offline experiment clone PROJECT_ID` | 克隆离线实验并指定新名称 |

### 训练任务

| 命令 | 作用 |
| --- | --- |
| `ml train start TASK_ID` | 立即执行指定训练任务，返回作业 ID |
| `ml train list` | 分页查询当前业务下的训练任务 |
| `ml train instance list TASK_ID` | 查询执行实例，固定第 1 页 10 条 |
| `ml train history list TASK_ID` | 查询执行记录，固定第 1 页 10 条 |
| `ml train history logs download TASK_ID JOB_ID` | 获取日志地址并下载 |
| `ml train config update TASK_ID` | 更新训练任务自定义参数 |

### 特征集

| 命令 | 作用 |
| --- | --- |
| `ml featureset wide list` | 分页查询宽表特征集 |
| `ml featureset model list` | 分页查询模型特征集 |
| `ml featureset wide config SET_ID` | 查询宽表特征集配置，固定 JSON 输出 |
| `ml featureset model config SET_ID` | 查询模型特征集配置，固定 JSON 输出 |

### Jupyter

| 命令 | 作用 |
| --- | --- |
| `ml jupyter doctor` | 验证认证、业务上下文、Kernel 与终端接口，不创建资源 |
| `ml jupyter notebook run SOURCE` | 上传并按顺序执行 Notebook |
| `ml jupyter terminal open` | 创建终端并连接 |
| `ml jupyter terminal list` | 列出当前身份可见的终端 |
| `ml jupyter terminal attach NAME` | 连接已有终端 |
| `ml jupyter terminal close NAME` | 关闭指定远程终端 |

### Web Studio

| 命令 | 作用 |
| --- | --- |
| `ml webstudio list` | 查询当前业务的实例列表 |
| `ml webstudio login ENV_ID` | 动态获取凭据并验证 Kernel 接口，保存默认实例 |
| `ml webstudio show` | 显示当前环境、账号与业务绑定的默认实例 |

---

## 全局选项

| 选项 | 环境变量 | 说明 |
| --- | --- | --- |
| `--config PATH` | `ML_CONFIG` | 指定 `config.json` 路径；文件必须存在且为合法 JSON |
| `--version` | — | 打印 `ml <版本号>` 后退出 |
| `--help` | — | 打印对应命令的用法后退出 |

`--config` 必须写在子命令之前，例如 `ml --config ./config.json train list -o json`。

`--output` 是部分末级命令的选项，不是全局选项。带 `-o` / `--output` 的命令可取 `table` 或 `json`，不传时跟随当前环境的默认输出格式。

---

## 登录与认证

### `ml login`

打开 Microsoft Edge 专用 Profile 完成平台登录，将 Cookie、CSRF Token、账号、中文名、部门与过期时间按环境保存到本地。

**命令格式**

```text
ml login [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--show-secrets` | `False` | 登录成功后额外打印完整的 Cookie 和 CSRF Token |

**说明**

- 认证默认有效 1800 秒（30 分钟）；过期时自动打开 Edge，优先复用已有平台会话，无需重复输入验证码。
- 等待用户登录最长 5 分钟；等待读取业务目录最长 30 秒。
- 需本机安装 Microsoft Edge；无需安装 Playwright Chromium。
- 登录可能恢复浏览器中已有的业务选择，可用 `ml business show` 核实。

**示例**

```bash
ml login
ml login --show-secrets
```

### `ml logout`

清除当前环境的本地短期认证缓存。

**命令格式**

```text
ml logout [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--all` | `False` | 清除所有环境的本地认证信息，而非仅当前环境 |
| `--forget-browser` | `False` | 同时删除专用 Edge Profile，之后登录可能需要重新输入验证码 |

**说明**

- 默认不影响 Edge 持久会话，便于下次无验证码恢复登录。

**示例**

```bash
ml logout
ml logout --all
ml logout --forget-browser
ml logout --all --forget-browser
```

### `ml auth status`

显示当前环境的认证有效期与基础信息，不打印 Cookie 或 Token。

**命令格式**

```text
ml auth status
```

**选项**

无。

**说明**

- 只读本地缓存，不自动续期。无缓存时命令失败；缓存过期时仍成功输出 `status` 为 `expired`。
- 输出字段：`profile`、`username`、`cn_name`、`department`、`business_id`、`status`、`remaining_seconds`、`acquired_at`、`expires_at`。
- 实际请求使用的业务 ID 以 `ml business show` 为准，`business_id` 仅为认证缓存中的记录值。

**示例**

```bash
ml auth status
```

### `ml access status`

实时检查当前登录账号是否获准在当前环境使用 CLI 业务功能。

**命令格式**

```text
ml access status [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--diagnose` | `False` | 显示权限请求连接、耗时和有限响应头，不输出凭据 |

**说明**

- 需管理员先部署权限服务并启用在线授权检查；未启用时输出配置提示。
- 启用后，业务查询、更新、日志下载等命令会在执行前自动做相同检查，被拒绝或服务故障均停止业务调用。每条业务命令重新检查，撤销对下一条命令生效。
- 帮助、版本、登录退出、环境切换和业务上下文操作不依赖在线授权。
- `--diagnose` 显示配置路径、版本、请求 URL、当前账号、环境、平台源地址、businessid、连接目标、HTTP 状态、请求耗时和有限的响应头；不输出 Cookie、CSRF、完整请求头或响应正文。输出含内部地址与账号，分享时按需隐藏。

**示例**

```bash
ml access status
ml access status --diagnose
ml --config ./config.json access status
```

---

## 运行环境

### `ml env list`

列出全部环境。

**命令格式**

```text
ml env list
```

**选项**

无。

**说明**

- 输出字段：`current`（`*` 表示当前环境）、`name`、`api_endpoint`、`access_status`（逐环境实时查询当前账号权限）、`output_format`、`verify_ssl`。查询需要对应环境已有的登录信息及 `business.json` 中的业务选择；不会自动登录，在线查询会留下调用日志。未登录、未配置权限服务或查询失败会单独显示，不代表已开通。
- 固定表格输出。

**示例**

```bash
ml env list
```

### `ml env show`

显示当前环境的完整信息。

**命令格式**

```text
ml env show
```

**选项**

无。

**说明**

- 输出字段：`name`、`api_endpoint`、`base_url`、`output_format`、`verify_ssl`。
- 固定表格输出。

**示例**

```bash
ml env show
```

### `ml env use`

切换当前环境。

**命令格式**

```text
ml env use NAME
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 目标环境名，必须已存在 |

**选项**

无。

**说明**

- 切换后需检查新环境的认证和业务选择。

**示例**

```bash
ml env use dev
```

---

## 业务上下文

所有平台业务请求统一携带 `businessid` 与 `ai-businessId` 请求头，值来自当前的业务选择。

### `ml business list`

显示当前环境可见的部门、租户、团队目录，并标记当前选择（`*当前`）。

**命令格式**

```text
ml business list
```

**选项**

无。

**说明**

- 业务命令要求至少选择租户，不能只选择部门。
- 团队仅当其 `teamStatus` 为 `available` 时才允许选择。
- 输出为层级目录，不是表格。

**示例**

```bash
ml business list
```

### `ml business show`

显示当前已选的租户或团队上下文。

**命令格式**

```text
ml business show
```

**选项**

无。

**说明**

- 输出字段：`type`、`department`、`tenant`、`team`、`businessId`。
- 固定表格输出。

**示例**

```bash
ml business show
```

### `ml business use`

交互式或通过 ID 选择租户/团队。

**命令格式**

```text
ml business use [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--tenant TEXT` | `None` | 租户 ID |
| `--team TEXT` | `None` | 团队 ID 或 key |
| `--department TEXT` | `None` | 部门 ID，用于消除重复租户 ID 的歧义 |

**说明**

- 不带任何参数时，按「部门 → 租户 → 租户级或团队级」顺序交互选择。
- 只传 `--team` 或 `--department` 而不传 `--tenant` 会报错。
- 实际可用的 ID 以 `ml business list` 列出的为准，不要从其他环境手工复制。

**示例**

```bash
ml business use
ml business use --tenant mep
ml business use --tenant mep --team asdasd
```

### `ml business refresh`

打开 Edge 重新读取浏览器中的业务目录并自动关闭 Edge。

**命令格式**

```text
ml business refresh
```

**选项**

无。

**说明**

- 已选团队被删除或变为非 `available` 状态时，当前选择会失效，必须重新选择。
- `ml business list` 未选择业务时也可执行，用于建立或维护业务上下文。

**示例**

```bash
ml business refresh
```

---

## 用户与 MEP

### `ml user info`

查询当前登录用户信息。

**命令格式**

```text
ml user info [OPTIONS]
```

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式（`table`） | 输出格式：`table` 或 `json` |

**说明**

- JSON 输出为接口的完整 JSON 响应。

**示例**

```bash
ml user info
ml user info -o json
```

### `ml mep config get`

查询一个 MEP 配置项。

**命令格式**

```text
ml mep config get [KEY] [OPTIONS]
```

**参数**

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `KEY` | 否 | `mep_service_access_type` | 配置项 key |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式（`table`） | 输出格式：`table` 或 `json` |

**说明**

- JSON 输出为接口的完整 JSON 响应。

**示例**

```bash
ml mep config get
ml mep config get mep_service_access_type -o json
```

---

## 训练看板

训练看板命令使用当前环境的认证与业务选择。推荐按「项目 → 项目空间 → 实验 → 实验数据」的顺序查询。以下命令均支持 `--output` / `-o`（`table` 或 `json`）。筛选团队不会切换当前业务上下文。

### `ml mtp swanboard project list`

分页查询项目，每次只请求一页。

**命令格式**

```text
ml mtp swanboard project list [OPTIONS]
```

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--team-id` | — | 空字符串 | 团队 ID 模糊查询 |
| `--creator` | — | 空字符串 | 创建者模糊查询 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 表格列：项目 id（`projectId`）、项目名称、项目描述、创建者、创建时间。
- JSON 包含 `page`、`pageSize`、`count`、`items`，并保留记录的额外字段。

**示例**

```bash
ml mtp swanboard project list
ml mtp swanboard project list --page 2 --page-size 20 --team-id team-a --creator a123456 -o json
```

### `ml mtp swanboard project namespace list`

查询训练看板项目下的全部项目空间。

**命令格式**

```text
ml mtp swanboard project namespace list [OPTIONS] PROJECT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | 是 | 训练看板 `projectId`，来自项目列表 |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--team-id` | — | 空字符串 | 团队 ID 模糊查询 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 不支持分页选项，单次调用项目空间查询接口。
- 表格列：项目空间 id（`namespaceId`）、实验 id、实验名称（`namespaceName`）、描述、创建时间。
- 这里表头的「实验 id」实际取响应的 `projectId`，**不是**后续实验数据命令需要的 `experimentId`。

**示例**

```bash
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project namespace list PROJECT_ID --team-id team-a -o json
```

### `ml mtp swanboard project experiment list`

查询项目空间下的全部实验。

**命令格式**

```text
ml mtp swanboard project experiment list [OPTIONS] PROJECT_ID NAMESPACE_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | 是 | 训练看板 `projectId` |
| `NAMESPACE_ID` | 是 | 项目空间 `namespaceId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--team-id` | — | 空字符串 | 团队 ID 模糊查询 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 没有分页选项，也不会自动遍历：只展示服务端单次返回的实验列表，不能据此保证取得全部实验。
- 表格列：项目实验 id（`experimentId`）、实验名称、创建时间。
- 后续实验数据命令使用这里返回的 `experimentId`。JSON 中服务端未返回的分页值可能为 `null`。

**示例**

```bash
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID --team-id team-a -o json
```

### `ml mtp swanboard experiment feature list`

查询实验特性。

**命令格式**

```text
ml mtp swanboard experiment feature list [OPTIONS] EXPERIMENT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `EXPERIMENT_ID` | 是 | 实验 `experimentId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 只查询指定的一页，不会自动遍历所有数据。
- 表格展示特征名（`featureName`）和扩展参数（`featuresConfig`）。
- JSON 包含 `page`、`pageSize`、`count`、`items`。

**示例**

```bash
ml mtp swanboard experiment feature list EXPERIMENT_ID --page 1 --page-size 10
ml mtp swanboard experiment feature list EXPERIMENT_ID --page 2 -o json
```

### `ml mtp swanboard experiment environment get`

查询实验环境。

**命令格式**

```text
ml mtp swanboard experiment environment get [OPTIONS] EXPERIMENT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `EXPERIMENT_ID` | 是 | 实验 `experimentId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 表格展示 Python 版本、系统硬件 CPU（`cpu.brand`）、系统硬件 Memory 和 Python 库名称；库数组按换行显示。
- JSON 输出环境对象；服务端环境数据为空数组时转为 `{}`。

**示例**

```bash
ml mtp swanboard experiment environment get EXPERIMENT_ID
ml mtp swanboard experiment environment get EXPERIMENT_ID -o json
```

### `ml mtp swanboard experiment metrics`

查询实验指标统计，默认查询 `loss` 和 `accuracy`。

**命令格式**

```text
ml mtp swanboard experiment metrics [OPTIONS] EXPERIMENT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `EXPERIMENT_ID` | 是 | 实验 `experimentId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--tag` | — | `loss`、`accuracy` | 指标名称，可重复传入 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 每个指标分别请求一次。显式传入 `--tag` 时替换默认列表。
- 表格展示指标名称、最大值、最小值、平均值，数值保留四位小数，非数值显示 `-`。
- JSON 保留原始精度。此命令不查询完整指标时间序列。

**示例**

```bash
ml mtp swanboard experiment metrics EXPERIMENT_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy -o json
```

### `ml mtp swanboard experiment config list`

查询实验配置。

**命令格式**

```text
ml mtp swanboard experiment config list [OPTIONS] EXPERIMENT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `EXPERIMENT_ID` | 是 | 实验 `experimentId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 表格逐项展示配置项与值；配置项为对象时取其 `value` 字段。
- JSON 保留配置对象的完整结构。

**示例**

```bash
ml mtp swanboard experiment config list EXPERIMENT_ID
ml mtp swanboard experiment config list EXPERIMENT_ID -o json
```

### `ml mtp swanboard experiment inspect`

一次性查询实验的特性、环境、指标和配置。

**命令格式**

```text
ml mtp swanboard experiment inspect [OPTIONS] EXPERIMENT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `EXPERIMENT_ID` | 是 | 实验 `experimentId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 一次依次查询特性、环境、`loss`、`accuracy` 和配置，共五次接口调用；任一查询失败则整条命令报错。
- 表格输出「实验特性」「实验环境」「指标信息」「实验配置」四个区块。JSON 对象包含 `features`、`environment`、`metrics`、`config`。
- **特性仅查询第 1 页 10 条**，并非完整导出；需要其他页时使用 `feature list`。
- 不接受 `--page`、`--page-size` 或 `--tag`。

**示例**

```bash
ml mtp swanboard experiment inspect EXPERIMENT_ID
ml mtp swanboard experiment inspect EXPERIMENT_ID -o json
```

---

## 离线实验

离线业务管理命令，在当前业务上下文内操作。

### `ml offline experiment list`

分页查询离线实验。

**命令格式**

```text
ml offline experiment list [OPTIONS]
```

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--name`, `--project-name` | — | `None` | 按实验名称模糊查询 |
| `--description` | — | `None` | 按描述模糊查询 |
| `--create-user` | — | `None` | 按创建者模糊查询 |
| `--update-user` | — | `None` | 按修改者模糊查询 |
| `--team-id` | — | `None` | 按团队 ID 模糊查询 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 表格列：`projectId`、实验名称、描述、创建者、修改者、创建时间、更新时间、运行配置模板。
- JSON 为 `pageIndex`、`pageSize`、`count`、`total`、`items`；记录保留固定字段。

**示例**

```bash
ml offline experiment list
ml offline experiment list --page 1 --page-size 20 --name "训练"
```

### `ml offline experiment trial list`

分页查询某个离线实验下的 trial。

**命令格式**

```text
ml offline experiment trial list [OPTIONS] PROJECT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | 是 | 离线实验 `projectId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--name` | — | `None` | 按 trial 名称模糊查询 |
| `--type` | — | `None` | 按 trial 类型模糊查询 |
| `--creator` | — | `None` | 按创建者模糊查询 |
| `--updater` | — | `None` | 按修改者模糊查询 |
| `--ai-module` | — | `None` | 按 AI 模块模糊查询 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 表格列：trial 名称、类型、创建者、修改者、创建时间、更新时间、调度状态、描述。
- `batch` 类型显示为「批式」，其他类型显示为「流式」；调度状态 `true` 显示「调度开启」、`false` 显示「调度停止」，其他值显示 `-`。
- JSON 记录当前不包含 trial ID。

**示例**

```bash
ml offline experiment trial list PROJECT_ID
ml offline experiment trial list PROJECT_ID --type batch --page-size 20
```

### `ml offline experiment clone`

查询源实验详情并同步克隆，仅修改实验名称。

**命令格式**

```text
ml offline experiment clone [OPTIONS] PROJECT_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `PROJECT_ID` | 是 | 源实验 `projectId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--name` | — | 必填 | 克隆后的实验名称 |
| `--yes` | `-y` | `False` | 跳过克隆确认 |
| `--dry-run` | — | `False` | 仅展示构造出的创建请求，不执行克隆 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 按源实验的业务与运行配置创建新实验，保留描述、业务、区域、集群、运行配置等字段，将创建者与修改者设为当前账号。它不是逐字段复制整个源响应，也不会复制 trial。
- 源实验必须属于当前业务上下文，否则报错。
- 不带 `--yes` 且不带 `--dry-run` 时，会先打印源/新实验名称、运行配置模板、`businessId`、团队 ID，再交互确认。回答否会输出「已取消克隆」。
- `--dry-run` 仍会认证、读取源实验并校验业务归属，但不发送创建请求；输出 `dryRun` 和 `request`。
- 成功创建输出源实验 ID、新 `projectId`（接口未提供时为 `-`）、实验名称、请求 UUID 和结果信息。
- 克隆会创建真实资源，建议先用 `--dry-run -o json` 查看实际创建请求。

**示例**

```bash
ml offline experiment clone PROJECT_ID --name "训练-副本"
ml offline experiment clone PROJECT_ID --name "训练-副本" -y
ml offline experiment clone PROJECT_ID --name "训练-副本" --dry-run
```

---

## 训练任务

所有命令使用当前环境的有效认证与业务选择。先用 `ml train list` 获取 `taskId`；执行实例和执行记录返回 `jobId`，下载日志时须同时提供所属任务 ID 与执行记录 ID。

### `ml train start`

立即执行指定训练任务，返回作业 ID；不预先查询任务列表。

**命令格式**

```text
ml train start [OPTIONS] TASK_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 要执行的训练任务 ID，直接提交给执行接口 |

**选项**

无专有选项。

**说明**

- 输入命令即发起执行，不再二次确认。
- 输出固定为文本，不受环境默认 JSON 输出设置影响。
- 成功输出作业 ID；成功响应没有有效 `jobId` 时输出提示，请查询执行记录确认。
- 执行成功表示接口接受本次执行操作，不表示训练已经完成。
- 提交后的超时、传输错误或其他无法确认结果的 HTTP 错误不会自动重发；请先用 `ml train history list` 查询确认。

**示例**

```bash
ml train start TASK_ID
ml --config ./config.json train start TASK_ID
```

### `ml train list`

分页查询当前业务下的训练任务。

**命令格式**

```text
ml train list [OPTIONS]
```

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--name` | — | 不筛选名称 | 按任务名称模糊查询 |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 只请求指定的一页。其他筛选保持管理台默认值，目前不接受任务类型、状态、团队、排序等选项。
- 表格列依次为任务 ID、任务名称、任务类型、业务场景、修改者、更新时间、最新执行时间、大小、描述；空列表显示「暂无训练任务」。
- JSON 为 `count`、`pageIndex`、`pageSize`、`items`；记录保留额外字段、空值与毫秒时间戳。
- 毫秒时间戳转换为北京时间的 `YYYY-MM-DD HH:mm:ss`。

**示例**

```bash
ml train list
ml train list --name wiserec --page 2 --page-size 20
ml train list -o json
```

### `ml train instance list`

查找训练任务并查询执行实例；固定第 1 页 10 条，开始时间升序。

**命令格式**

```text
ml train instance list [OPTIONS] TASK_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 训练任务的完整 `taskId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 命令自动逐页扫描当前业务的训练任务，精确匹配 ID，再用该任务的业务 ID 与任务类型查询实例，不必预先运行列表命令。任务多时会产生多次查询。
- 固定第 1 页 10 条，按开始时间 `createTime` 升序，不支持翻页、排序或筛选选项。
- 表格展示任务名称与 ID，以及作业 ID、算法名称、CPU、GPU、内存、状态、执行节点（`hostIp`）、集群、触发方式（`actionType`）、开始时间、执行时长、存储桶。
- 执行时长由展示时的当前时间减去开始时间计算，取整分钟；不足一分钟或未来开始时间显示 `0min`，缺少开始时间显示 `-`。它并非服务端记录的实际结束耗时。
- 作业 ID 首列固定宽度 36，不换行、不截断。空列表显示「暂无执行实例」。

**示例**

```bash
ml train instance list TASK_ID
ml train instance list TASK_ID -o json
```

### `ml train history list`

直接查询执行记录；固定第 1 页 10 条，开始时间倒序。

**命令格式**

```text
ml train history list [OPTIONS] TASK_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 训练任务的完整 `taskId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 直接按任务 ID 查询，不扫描任务列表。
- 固定第 1 页 10 条，按 `createTime` 倒序，不支持分页、排序或筛选选项。
- 表格列：作业 ID、算法名称、CPU、GPU、内存、状态、集群、节点数、执行时长、大小、检查时间（`checkTime`）、开始时间（`createTime`）、结束时间（`statusTime`）、触发方式、存储桶。
- 作业 ID 首列固定宽度 36，不换行、不截断。空列表显示「暂无执行记录」，不据此判定任务不存在。

**示例**

```bash
ml train history list TASK_ID
ml train history list TASK_ID -o json
```

### `ml train history logs download`

获取日志地址并下载；发送 `isApplicantPromise=true`，不覆盖已有文件。

**命令格式**

```text
ml train history logs download [OPTIONS] TASK_ID JOB_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 所属训练任务 ID |
| `JOB_ID` | 是 | 执行记录 ID，取记录中的 `jobId` |

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--file` | — | 当前目录下自动命名 | 本地保存路径，其父目录必须已存在 |
| `--output` | `-o` | 当前环境的默认输出格式 | 结果摘要格式：`table` 或 `json` |

**说明**

- 直接向下载地址接口提交这两个 ID，不预先查询历史记录或在本地验证归属，也不受记录列表第一页 10 条限制。
- 默认文件名取响应 `Content-Disposition`，移除目录成分及不适合文件名的字符，并补充 `.zip` 后缀；缺省为 `JOB_ID-logs.zip`。显式 `--file` 保留指定文件名，不强制补 `.zip`。
- 文件内容原样保存，不自动解压。目标已存在时自动递增编号（如 `train-logs (1).zip`），不覆盖已有文件。
- 下载先写入同目录临时文件，接收完整后以硬链接发布最终文件，故目标文件系统须支持硬链接。
- 实际文件下载使用独立客户端，不携带平台 Cookie、CSRF 或业务请求头。完整下载地址、认证提示和进度发送到 stderr。
- 成功摘要包含 `taskId`、`jobId`、绝对路径 `path`、字节数 `bytes`、`status="downloaded"`。`-o json` 只把 JSON 摘要写到 stdout。
- 下载失败、传输不完整或保存失败时非零退出并清理临时文件。

**示例**

```bash
ml train history logs download TASK_ID JOB_ID
ml train history logs download TASK_ID JOB_ID --file ./train-logs.zip
ml train history logs download TASK_ID JOB_ID --file ./train-logs.zip -o json
```

### `ml train config update`

获取训练任务详情，保留完整 `taskInfo` 后更新自定义参数。

**命令格式**

```text
ml train config update [OPTIONS] TASK_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 是 | 训练任务 ID，不允许空白 ID |

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--customize-config` | 必填 | 自定义参数，按字符串原样传递 |

**说明**

- 先查询训练任务详情，再更新自定义参数，执行命令即提交更新。
- 任务名称从详情读取，不提供 `--name`。
- `--customize-config` 不转换为数字或 JSON，保留前导零和空格；空字符串也原样提交。
- 修改人取当前环境账号，业务 ID 取当前业务选择；缺少业务选择、缺少用户名或账号不匹配时不提交更新。
- 成功输出「更新训练任务自定义参数成功！」；失败显示接口的 `code` 和 `des` 并非零退出。
- 固定输出成功文本，不提供 `--output` 选项。

**示例**

```bash
ml train config update TASK_ID --customize-config "96999"
ml train config update TASK_ID --customize-config "0096999"
```

---

## 特征集

两个入口分别固定查询宽表特征集与模型特征集，均使用当前业务的业务 ID。

### `ml featureset wide list`

分页查询当前业务下的宽表特征集。

**命令格式**

```text
ml featureset wide list [OPTIONS]
```

**选项**

| 选项 | 短选项 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `--name` | — | 空字符串 | 按特征集名称查询，匹配规则由服务端决定 |
| `--page` | — | `1` | 开始页码，≥ 1 |
| `--page-size` | — | `10` | 每页记录数，≥ 1 |
| `--output` | `-o` | 当前环境的默认输出格式 | 输出格式：`table` 或 `json` |

**说明**

- 只请求指定的一页，不会自动遍历所有数据。
- 表格列顺序：特征集 ID、特征集名称、特征集类型、场景、创建者、创建时间、修改者、修改时间。记录保持服务端顺序，缺失字段、`null` 和空字符串显示 `-`。
- 带时区的 ISO 时间转换为北京时间 `YYYY-MM-DD HH:mm:ss`；例如 `2026-09-08T03:30:58.000+00:00` 显示为 `2026-09-08 11:30:58`。
- 页尾展示当前页、每页条数和总记录数，空列表显示「暂无特征集」。
- JSON 为 `count`、`pageIndex`、`pageSize`、`items`；认证提示写入 stderr，不混入 JSON 标准输出。
- 未选择业务时提示执行 `ml business use`，不回退到默认业务。

**示例**

```bash
ml featureset wide list
ml featureset wide list --name test --page 2 --page-size 20
ml featureset wide list -o json
```

### `ml featureset model list`

分页查询当前业务下的模型特征集。

**命令格式**

```text
ml featureset model list [OPTIONS]
```

**选项**

与 `ml featureset wide list` 完全一致，仅查询的特征集类型不同。

**说明**

- 参数、输出字段与展示规则同 `ml featureset wide list`。

**示例**

```bash
ml featureset model list
ml featureset model list --name test --page-size 20
ml featureset model list --output json
```

### `ml featureset wide config`

查询特征集配置，固定输出解析后的 JSON 对象。

**命令格式**

```text
ml featureset wide config [OPTIONS] SET_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `SET_ID` | 是 | 特征集 ID，去除首尾空白后不能为空 |

**选项**

无。该命令固定输出格式化 JSON，不接受 `--output`，不受环境默认输出格式影响。

**说明**

- 直接根据 ID 查询，不预先请求列表。
- 仅打印解析后的配置对象，不包含 `version`、`meta`、`result` 等响应包装；配置对象自身的 `version` 等字段完整保留。
- 中文直接显示，嵌套结构、数组顺序和数据类型保持原样。
- 认证提示和错误写入 stderr，标准输出可直接重定向保存。

**示例**

```bash
ml featureset wide config SET_ID
ml featureset wide config 6743499e-15ec-496c-b510-ee9bf65f395e
ml featureset wide config SET_ID > featureset-config.json
```

### `ml featureset model config`

查询模型特征集配置，固定输出解析后的 JSON 对象。

**命令格式**

```text
ml featureset model config [OPTIONS] SET_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `SET_ID` | 是 | 特征集 ID，去除首尾空白后不能为空 |

**选项**

无。固定输出格式化 JSON，不接受 `--output`。

**说明**

- 参数校验、输出内容与展示规则同 `ml featureset wide config`。

**示例**

```bash
ml featureset model config SET_ID
ml featureset model config SET_ID > featureset-config.json
```

---

## Jupyter

以下命令需要可访问的 Jupyter Server 与有效凭据，并在当前环境完成登录与业务选择。

- 直接模式：需在当前环境配置 Jupyter 服务地址与 Token，Token 可通过环境变量或文件提供。
- Web Studio 模式：由实例动态返回访问地址与 Token，需先执行 `ml webstudio login ENV_ID` 保存默认实例。
- 终端相关命令需要服务端启用终端能力。
- 所有命令的 `--studio-id` 仅覆盖本次目标实例，不修改默认选择；未配置 Web Studio 模式时不能使用。

### `ml jupyter doctor`

验证认证、业务上下文、Kernel 与终端管理接口，不创建资源。

**命令格式**

```text
ml jupyter doctor [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 检查 HTTP 认证、Kernel 列表和 Terminal 接口，逐步报告管理台、实例、地址获取及 Kernel/Terminal HTTP 检查结果。
- 不会创建资源，也不代表 WebSocket 已验证；WebSocket 在实际执行或连接终端时验证。
- 登录成功不表示终端必然有权限。

**示例**

```bash
ml jupyter doctor
ml jupyter doctor --studio-id ENV_ID
```

### `ml jupyter notebook run`

上传并按顺序执行 Notebook；失败也保存部分结果，不自动重试。

**命令格式**

```text
ml jupyter notebook run [OPTIONS] SOURCE
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `SOURCE` | 是 | 本地 `.ipynb` 文件 |

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--download PATH` | `results` | 本地结果根目录，每次新建 UUID 子目录 |
| `--kernel TEXT` | 当前环境的 Kernel | 覆盖本次执行的 Kernel 名称 |
| `--cwd TEXT` | 本次独立目录 | 相对服务器根目录的工作目录 |
| `--timeout FLOAT` | `600` | 全部代码单元格执行时限（秒），≥ 0.1 |
| `--startup-timeout FLOAT` | `60` | Kernel 就绪等待时间（秒），≥ 0.1 |
| `--output TEXT` / `-o TEXT` | `text` | `text` 或 `json` |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 顺序执行非空代码单元格，遇错停止。每次创建 UUID 结果目录，保存 `executed.ipynb` 和 `summary.json`；不覆盖输入文件。
- `--cwd` 不会同步本地依赖文件，请提前准备远程目录；不指定时使用本次独立目录。
- 前台执行要求 CLI 持续连接；不提供 `--detach`，也不自动重试代码。
- JSON 模式仅 stdout 输出最终结构化摘要，进度和实时输出进入 stderr；摘要时间均为北京时间。
- 失败、超时或中断时保存已收到的输出，尝试中断并删除本次 Kernel；清理失败会在摘要中列出 `kernel_id` 和提示。
- 退出码：成功 `0`；参数、认证或执行失败 `1`（解析错误可能为 `2`）；执行结果未知 `2`；超时 `124`；用户中断 `130`。

**示例**

```bash
ml jupyter notebook run analysis.ipynb
ml jupyter notebook run analysis.ipynb --download results
ml jupyter notebook run analysis.ipynb --cwd projects/demo --kernel python3 --timeout 1800 --output json
ml jupyter notebook run analysis.ipynb -o json
ml jupyter notebook run analysis.ipynb --studio-id ENV_ID
```

### `ml jupyter terminal open`

创建终端并连接，Ctrl+] 仅断开本地连接。

**命令格式**

```text
ml jupyter terminal open [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 创建并连接远程终端，输出终端名称。
- 需要真实 TTY。Ctrl+] 只断开本地连接，不关闭远程 Shell。
- 服务端需启用终端能力。

**示例**

```bash
ml jupyter terminal open
ml jupyter terminal open --studio-id ENV_ID
```

### `ml jupyter terminal list`

列出当前 Jupyter 身份可见的终端。

**命令格式**

```text
ml jupyter terminal list [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 展示终端名称与北京时间格式的最后活动时间。
- 终端名称仅在所属实例内有效。

**示例**

```bash
ml jupyter terminal list
ml jupyter terminal list --studio-id ENV_ID
```

### `ml jupyter terminal attach`

连接已有终端，不保证补取完整历史输出。

**命令格式**

```text
ml jupyter terminal attach [OPTIONS] NAME
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 服务器返回的终端名称 |

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 重连现存终端，不保证补取全部历史输出。
- Ctrl+C 发给远程进程，Ctrl+D 发送 EOF，Ctrl+] 只断开客户端。
- 终端名称仅在所属实例内有效。

**示例**

```bash
ml jupyter terminal attach 1
ml jupyter terminal attach 1 --studio-id ENV_ID
```

### `ml jupyter terminal close`

关闭指定远程终端及其 Shell，会影响在其中运行的进程。

**命令格式**

```text
ml jupyter terminal close [OPTIONS] NAME
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `NAME` | 是 | 要关闭的终端名称 |

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--studio-id TEXT` | 无 | 指定本次目标 Web Studio 实例 |

**说明**

- 删除指定远程终端，可能中止其中的进程。
- 终端名称仅在所属实例内有效。

**示例**

```bash
ml jupyter terminal close 1
ml jupyter terminal close 1 --studio-id ENV_ID
```

---

## Web Studio

以下命令需要先完成 `ml login` 和 `ml business use`，并在当前环境启用 Web Studio 模式。平台模式即使未启用额外的权限服务，也需要管理台认证。

### `ml webstudio list`

查询当前业务的实例列表；名称模糊匹配，其余条件精确匹配。

**命令格式**

```text
ml webstudio list [OPTIONS]
```

**选项**

| 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `--page` | `1` | 开始页码，≥ 1 |
| `--page-size` | `10` | 每页记录数，≥ 1 |
| `--name TEXT` | 无 | 按实例名称模糊匹配 |
| `--status TEXT` | 无 | 按状态精确匹配 |
| `--relator TEXT` | 无 | 按关联人精确匹配 |
| `--env-id TEXT` | 无 | 按实例 ID 精确匹配 |
| `--business-id TEXT` | 无 | 必须与当前业务选择一致 |
| `--output TEXT` / `-o TEXT` | `table` | `table` 或 `json` |

**说明**

- 列按实例 ID、名称、集群类型、资源规格、状态、创建者、修改者、启动时间展示。
- 首列固定宽度 36，不换行、不截断。
- 启动时间使用 `accessTime`，转换为北京时间 `YYYY-MM-DD HH:mm:ss`。
- JSON 保留原始响应字段及原始机器时间，敏感字段脱敏；不能把原始时间当作北京时间展示。
- 查询结果为空正常显示。

**示例**

```bash
ml webstudio list
ml webstudio list --status online --name l001
ml webstudio list --relator l00123456 --page 2 --page-size 20
ml webstudio list --output json
ml webstudio list -o json
```

### `ml webstudio login`

动态获取凭据并验证 Kernel 接口，成功后保存默认实例；不保存 Token。

**命令格式**

```text
ml webstudio login [OPTIONS] ENV_ID
```

**参数**

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `ENV_ID` | 是 | Web Studio 实例 ID |

**选项**

无专有选项。

**说明**

- 定位实例、取得动态凭据、验证 Kernel HTTP 接口，成功后保存为当前默认目标实例；失败不覆盖旧选择。
- 只连接 online 状态的实例；其他状态会提示在管理台处理。不自动启动、重启或删除实例。
- 默认实例仅保存实例 ID、名称、区域和选择时间，不保存 Token。
- 从单一服务地址切换到区域映射配置后，默认实例的隔离范围会变化，请重新执行一次本命令。
- 命令会在连接前把包含 Token 的完整访问地址输出到 stderr，便于定位网关路径问题，且不污染 JSON 标准输出。

**示例**

```bash
ml webstudio login ENV_ID
ml webstudio login f925886d-072c-48fc-a4ec-636ab3ba9a60
```

### `ml webstudio show`

显示当前环境、账号与业务绑定的选择，不代表实例实时状态。

**命令格式**

```text
ml webstudio show [OPTIONS]
```

**选项**

无专有选项。

**说明**

- 显示保存时的实例名称，不是实时查询结果。
- 默认实例按配置文件路径、平台地址、环境、区域网关配置、账号和业务 ID 隔离。

**示例**

```bash
ml webstudio show
```
