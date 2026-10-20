# WiseRec CLI 使用手册

`ml` 用于管理 WiseRec 平台的环境、业务、训练任务、样本任务、特征任务、算法仓、服务、数据集、特征集和开发工作空间。本手册面向命令使用者。示例中的 `TASK_ID`、`JOB_ID`、`PROJECT_ID`、`EXPERIMENT_ID`、`SET_ID`、`SERVICE_ID`、`DATASET_ID` 等占位符，需要替换成列表查询得到的实际 ID。

## 1. 命令树

### 1.1 命令格式

```text
ml                                              WiseRec 命令行工具
├── context                                     查看运行上下文
├── login                                       登录平台
├── logout                                      退出登录
├── tree                                        查看完整命令树
├── history                                     查看和管理本地命令历史
│   ├── list                                    查询历史执行记录
│   └── clear                                   清理历史记录
├── auth                                        登录状态
│   ├── status                                  查看当前登录状态
│   └── ping                                    管理终端会话自动保活
│       ├── start                               启动当前终端的保活
│       ├── status                              查看保活状态和最近请求
│       └── stop                                停止当前环境的保活
├── env                                         环境管理
│   ├── list                                    查看可用环境
│   ├── show                                    查看当前环境
│   └── use                                     切换环境
├── business                                    业务选择
│   ├── list                                    查看可选租户和团队
│   ├── show                                    查看当前业务选择
│   ├── use                                     选择租户或团队，可逐级返回或取消
│   └── refresh                                 刷新业务目录
├── access                                      访问授权
│   └── status                                  检查当前账号的访问权限
├── user                                        用户信息
│   └── info                                    查看当前用户信息
├── mep                                         MEP 管理
│   └── config                                  配置项查询
│       └── get                                 查看指定配置项
├── mtp                                         训练看板
│   └── swanboard                               项目和实验信息
│       ├── project                             项目
│       │   ├── list                            查看项目列表
│       │   ├── namespace                       项目空间
│       │   │   └── list                        查看项目空间列表
│       │   └── experiment                      项目中的实验
│       │       └── list                        查看实验列表
│       └── experiment                          实验详情
│           ├── feature                         实验特性
│           │   └── list                        查看特性列表
│           ├── environment                     实验环境
│           │   └── get                         查看运行环境
│           ├── metrics                         查看指标统计
│           ├── config                          实验配置
│           │   └── list                        查看配置项
│           └── inspect                         汇总查看实验信息
├── offline                                     离线业务
│   └── experiment                              离线实验
│       ├── list                                查看实验列表
│       ├── trial                               实验 Trial
│       │   └── list                            查看 Trial 列表
│       └── clone                               克隆实验
├── train                                       训练任务
│   ├── list                                    查看任务列表
│   ├── instance                                执行实例
│   │   └── list                                查看实例列表
│   ├── history                                 执行记录
│   │   ├── list                                查看执行记录
│   │   └── logs                                执行日志
│   │       └── download                        下载日志
│   ├── start                                   执行任务
│   ├── config                                  任务配置
│   │   ├── export                              导出配置
│   │   └── update                              更新自定义参数
│   ├── cancel                                  取消执行
│   ├── delete                                  删除任务
│   └── clone                                   克隆任务
├── sample-task                                 样本任务
│   ├── list                                    分页查询样本任务，默认使用旧任务管理
│   ├── period                                  新版样本任务执行周期
│   │   └── list                                分页查询执行周期
│   └── execution                               新版样本任务执行记录
│       └── list                                分页查询执行记录
├── model                                       模型查询与部署
│   ├── list                                    查询当前业务的模型列表
│   ├── detail                                  查询模型详情
│   ├── source                                  查询模型溯源或关联训练任务信息
│   └── deploy                                  使用部署模板将模型部署为服务
├── resource                                    资源管理
│   └── template                                资源模板查询
│       ├── list                                查询资源模板列表
│       └── detail                              查询资源模板详情
├── deployment                                  部署管理
│   └── template                                部署模板查询
│       ├── list                                查询部署模板列表
│       └── detail                              查询部署模板详情
├── algorithm                                   算法仓
│   ├── list                                    查看算法仓列表
│   ├── download                                下载算法仓文件
│   └── clone                                   克隆算法仓
├── service                                     服务管理
│   ├── list                                    查看服务列表
│   ├── mock                                    使用样例报文测试服务响应
│   ├── logs                                    选择服务主机和文件并查看日志
│   ├── host                                    服务主机查询与测试
│   │   ├── list                                查看指定服务的主机列表
│   │   └── mock                                使用样例报文测试指定主机
│   └── deployment                              服务部署视图
│       └── list                                查看指定服务的部署列表
├── dataset                                     数据集管理
│   ├── list                                    分页查询数据集
│   ├── detail                                  查看数据集详情
│   └── files                                   管理数据集目录和文件
│       ├── list                                查看指定目录内容
│       └── upload                              向指定目录追加文件
├── feature-task                                特征任务
│   ├── list                                    分页查询当前业务下的特征任务
│   └── execution                               特征任务执行记录
│       ├── list                                分页查询特征任务的执行记录
│       └── logs                                执行记录日志
│           └── search                          查询和搜索训练日志
├── featureset                                  特征集
│   ├── wide                                    宽表特征集
│   │   ├── list                                查看列表
│   │   ├── config                              查看配置
│   │   └── export                              导出特征集中的特征为 CSV 文件
│   └── model                                   模型特征集
│       ├── list                                查看列表
│       ├── config                              查看配置
│       └── export                              导出特征集中的特征为 CSV 文件
├── jupyter                                     文件、非交互执行、Notebook 与终端
│   ├── doctor                                  检查连接状态
│   ├── exec                                    非交互执行远端程序
│   ├── files                                   远端文件与目录
│   │   ├── list                                列出目录
│   │   ├── stat                                查询文件信息
│   │   ├── read                                读取文本
│   │   ├── write                               写入文本
│   │   ├── mkdir                               创建目录
│   │   ├── upload                              上传单文件
│   │   ├── download                            下载单文件
│   │   ├── move                                移动或重命名
│   │   ├── copy                                复制文件至目录
│   │   └── delete                              删除文件或空目录
│   ├── notebook                                Notebook
│   │   └── run                                 执行 Notebook
│   └── terminal                                远程终端
│       ├── list                                查看终端列表
│       ├── open                                创建并连接终端
│       ├── attach                              连接已有终端
│       └── close                               关闭终端
└── webstudio                                   Web Studio 实例
    ├── list                                    查看实例列表
    ├── login                                   选择默认实例并刷新连接缓存
    ├── show                                    查看默认实例
    ├── start                                   启动实例
    └── stop                                    停止实例
```

### 1.2 参数与选项

`ml tree` 无需参数。各命令的参数与选项见对应章节。

### 1.3 说明

从上到下按顺序输入命令层级；使用 `--help` 查看具体用法。`ml tree` 中各命令的说明结尾不显示标点符号。

### 1.4 示例

```bash
ml tree
ml train history logs download --help
```

## 2. 安装与首次使用

### 2.1 命令格式

```text
install.cmd
ml env use NAME
ml login
ml business use
```

### 2.2 参数与选项

`NAME` 为 `ml env list` 中的环境名称。

### 2.3 说明

首次安装采用包内默认环境。重装或升级后保留之前选择的环境及自动保活设置，其他配置仍由安装包更新。若原配置损坏、无效或所选环境已被新包删除、改名，配置更新会停止并保留原文件；按提示修复配置，或通过 `--config CONFIG_PATH` 指定原配置并使用 `ml env use NAME` 选择新包支持的环境后重试。

完整解压管理员提供的安装包，运行 `install.cmd` 后重新打开终端。安装分两个阶段：先安装 CLI，再安装 OpenCode skill 和 `/ml` command。第二阶段失败不影响 CLI 使用，解决提示的问题后重新运行安装程序即可重试。资源默认位于当前用户的 `~/.config/opencode`，设置 `OPENCODE_CONFIG_DIR` 可指定目录。每次成功安装会先备份再完整替换 `skills/wiserec-platform` 和 `commands/ml.md`，请勿直接修改这些文件。安装程序还会把权限规则合并进该目录的 `opencode.json`（仅有严格 JSON 的 `opencode.jsonc` 时写入该文件）。权限规则先写入并核对，通过后才安装 skill 和 `/ml` command。无法识别 OpenCode、配置无法解析、文件含注释或核对失败时，原文件不改或从备份恢复，并且不安装新的 skill 和 `/ml` command；已经存在的旧版本保持原样。替换前会先备份旧的 skill 和 `/ml` command，复制失败时恢复这份备份，并把这次的权限改动从备份恢复，同时删除 `wiserec-managed.json`。官方安装程序会显示失败原因和下一步。CLI 仍可使用，修正问题后重新运行安装程序即可重试。与要写入的键同名时，安装程序的值直接生效，并醒目打印每个键的原值和新值。`"*"` 的确认规则放在最前，其他被覆盖的键移入受管理规则。原值记在配置文件同目录的 `wiserec-managed.json`，不往 OpenCode 配置里写额外字段。不冲突的用户键不修改。重复安装不会重复追加，也不再打印已经接管的键。写入后会让 OpenCode 重新加载配置，并核对受管理规则已经生效。加载失败或规则缺失则恢复原文件。失败时只显示退出码和第一行错误，并隐去 key、token、secret、password，以及 Authorization 里的 Bearer 和 Basic。首次备份为 `opencode.json.bak` 或 `opencode.jsonc.bak`，已有备份不会被覆盖。备份可能含有 API 密钥。备份从创建起就只允许当前用户读写。其他系统上仅所有者可读写。Windows 上用 `whoami` 得到的 `DOMAIN\user` 调用 `icacls`；`icacls` 或 `whoami` 失败时会警告。不冲突的用户规则保留，相对顺序不变。`permission.bash` 和 `permission.shell` 里不是同一条键的规则不删除。`"*": "ask"` 放在第一项，其他受管理规则追加在最后。不是同一条键的通配放行会列出警告，后面的确认或拒绝规则在命中时仍然生效。`"*": "ask"` 作用于所有 shell 命令，不只是 `ml`。使用权限数组时，对象里保留的 `"*": "allow"` 会被后面的确认规则盖过，未再被更后规则命中的命令需要确认。只有项目配置或 Agent 配置里确有可能盖过这些规则的条目时才警告。全局配置里 `agent.<name>.permission.bash` 的宽泛 allow，以及 Agent markdown 里的 `bash: allow`，也会警告。安装输出会列出本次写入和从旧记录迁出的规则。使用权限数组时，会话中的“始终允许”可以覆盖需要确认的规则，不能覆盖拒绝规则。不要对 `ml` 命令选择“始终允许”，否则在重新打开 OpenCode 之前，连拒绝规则也会失效。命令里出现 TAB 时，整条命令都不会做权限检查，包括只有一条命令的情况。任一子命令被拒绝时，整条命令会被拒绝。精确列出的只读 `ml` 命令可直接执行，高风险命令需要在 OpenCode 中确认，读取凭据会被拒绝。执行 `python -m wiserec_cli.opencode_install --uninstall` 会删掉安装程序新增的键，并把被覆盖的键恢复成原值。`wiserec-managed.json` 缺失或损坏时会明确警告，并只删除与 WiseRec 规则完全一致的条目，逐条说明无法恢复的原值；效果不同的用户规则保留。安装时若清单缺失且配置里已有这些规则，或清单损坏，也会警告。`[IO.File]::ReadAllText` 和 `${路径}` 不在规则覆盖范围内。重新打开 OpenCode 会话后，可输入 `/ml 查询当前业务下的模型`，也可输入 `/ml` 查看用法。直接安装 Wheel 不自动安装 OpenCode 资源。使用前准备好所需 Python 环境和 Microsoft Edge，依次选择环境、登录、选择业务。

### 2.4 示例

```bash
ml env list
ml env use dev
ml login
ml business use
ml business show
ml train list
```

## 3. 全局用法

### 3.1 命令格式

```text
ml [OPTIONS] COMMAND [ARGS]...
ml tree
```

### 3.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--help` | 显示命令帮助；可放在各级命令后 |
| `--no-history` | 放在命令前，不保存本次调用；环境变量 `ML_HISTORY=0` 可关闭自动记录 |
| `ml tree` | 显示完整命令树及简短用途，无需登录或选择业务 |
| `--output` / `-o` | 部分查询命令支持 `table` 或 `json`，以对应命令帮助为准 |

### 3.3 说明

不传命令时显示帮助。`ml tree` 无需登录；参数详情使用对应命令的 `--help`。带 `--output` 的命令可切换输出格式，以命令帮助为准。

表格中的时间按北京时间显示，格式为 `YYYY-MM-DD HH:mm:ss`，不额外打印时区提示行。

分页统计、空结果、目录位置、字段、诊断结果、进度和交互确认直接显示正文，不加消息前缀。需要额外关注的操作提示使用青色 `[提示]`，操作完成使用绿色 `[成功]`，异常但不阻断主操作的情况使用黄色 `[警告]`，执行失败使用红色 `[错误]`。提示及成功消息仅前缀着色；警告及错误的摘要同色，补充说明、命令、地址及 UUID 保持默认色。

结果正文和表格输出到标准输出流；操作提示、进度、交互输入、警告及错误输出到标准错误流。JSON、文件内容及远端程序输出保留原格式。未知命令或参数错误显示简短错误和对应的 `--help` 用法，不显示异常堆栈。重定向消息到文件时自动关闭颜色，设置 `NO_COLOR` 环境变量也可关闭颜色。警告不单独改变退出码；操作成功返回 `0`，失败返回非零，已有超时及中断退出码保持不变。

提示未登录或未选择业务时，分别执行 `ml login`、`ml business use`。查询不到目标时核对环境、业务和页码；操作超时后先查询远程状态，再决定是否重试。

### 3.4 示例

```bash
ml --help
ml tree
ml train --help
ml train list --help
ml train list -o json
```

## 4. 登录与退出

### 4.1 命令格式

```text
ml login [OPTIONS]
ml logout [OPTIONS]
ml auth status
ml auth ping start
ml auth ping status
ml auth ping stop
```

### 4.2 参数与选项

| 命令或选项 | 用途 |
| --- | --- |
| `ml login` | 打开 Edge 完成登录 |
| `ml login --show-secrets` | 登录后显示敏感认证信息，仅在确需排查时使用 |
| `ml logout` | 清除当前环境的登录状态 |
| `ml logout --all` | 清除所有环境的登录状态 |
| `ml logout --forget-browser` | 同时清除浏览器登录会话 |
| `ml auth status` | 查看当前账号和登录状态，不显示敏感信息 |
| `ml auth ping start` | 为当前终端启动自动保活 |
| `ml auth ping status` | 查看保活进程和最近请求结果，不发送请求 |
| `ml auth ping stop` | 停止当前环境的自动保活 |

### 4.3 说明

登录前须在 `config.json` 中为当前环境配置非空的 `alias`。提示“正在登录【环境别名】”，交互终端用单行旋转提示展示当前阶段，不显示百分比；非交互输出只显示简短静态提示。登录时隐藏浏览器驱动的 Warning 输出，登录失败等错误仍正常显示。成功后显示环境别名、账号、中文名、部门和当前选中的 `businessId`，缺失信息显示“未获取”。需要选择业务或申请权限时，按额外提示操作。环境名称不回退显示 `name`，Cookie 和 CSRF Token 仅在显式指定 `--show-secrets` 时显示。

登录取得当前账号后，会查询该账号是否拥有任意环境的有效 CLI 授权。若没有，按提示打开配置的权限服务地址下的 `/apply` 申请权限；地址无法打开时，将 `*.hwcloudtest.cn` 加入代理排除。账号、环境、授权均启用且授权未过期才算有效，申请通过前不会自动启动保活。

登录后用 `auth status` 查看账号、剩余空闲时间及当前业务。默认空闲 30 分钟后校验登录，持续使用会延长会话；`--forget-browser` 会清除浏览器登录状态。

交互终端登录并选择业务后默认自动保活，空闲 10 分钟时请求平台。保活启动成功时不显示提示，启动失败等需要处理的信息仍会显示。`ping status` 查看当前环境仍在运行的保活终端数及最近结果；`ping stop` 停止，`ping start` 恢复。关闭最后一个登记终端或退出登录后停止保活，休眠或断网时无法保活。

### 4.4 示例

```bash
ml login
ml auth status
ml auth ping status
ml logout
```

## 5. 环境管理

### 5.1 命令格式

```text
ml env list
ml env show
ml env use NAME
```

### 5.2 参数与选项

| 参数 | 用途 |
| --- | --- |
| `NAME` | 要切换到的环境原始标识，取自 `config.json` 中 `profiles[].name`，不是显示别名 |

### 5.3 说明

`list` 显示“当前在用环境”“环境标识”“环境名”“管理台地址”“状态”五列。“环境标识”显示 profile 的 `name`，“环境名”显示 `alias`，未配置别名时显示 `name`。星号表示当前环境，支持彩色输出的终端中该环境整行以加粗绿色文字显示；`show` 显示当前环境，`use` 切换环境。切换仍使用 `name`，例如 `ml env use dev`，不能使用别名。

`ml env list` 最多发送一次批量请求，查询当前环境保存账号的有效授权。状态为：无有效授权显示“未授权”；有授权但未登录或未完成业务选择显示“已授权”；该账号登录有效且已选择业务显示“登录使用中”；有授权但该账号的登录凭据过期显示“登录已过期”。其他环境保存的不同账号不会作为当前账号的登录状态。各环境检查使用自身保存的业务 ID，不会切换环境，也不替代业务命令执行前的实时鉴权。

当前账号没有任何有效环境授权时，仅显示“错误：请打开XXX/apply进行CLI权限申请（若地址无法打开，将*.hwcloudtest.cn加入代理排除），权限通过后方可执行CLI命令”，其中 XXX 为 `config.json` 中的 `access_control.url`，不显示列表；尚无账号时提示先执行 `ml login`。查询失败、权限校验关闭或服务地址未配置时仅提示错误，不误报为“未授权”。权限服务需支持完整环境授权状态查询，旧服务会提示更新，不会回退到逐个请求。切换命令使用切换后环境的账号检查有效授权，切换后请核对账号和业务选择。

### 5.4 示例

```bash
ml env list
ml env use dev
ml env show
ml auth status
```

## 6. 业务选择

### 6.1 命令格式

```text
ml business list
ml business show
ml business use [OPTIONS]
ml business refresh
```

### 6.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--tenant ID` | 选择租户 |
| `--team ID` | 在指定租户内选择团队，需同时提供 `--tenant` |
| `--department ID` | 同名租户有歧义时指定部门，需同时提供 `--tenant` |
| `--search 关键词` | 按部门名称或 ID 的部分内容筛选交互列表，不能与 `--tenant` 同时使用 |

### 6.3 说明

`business use` 引导选择部门、租户和团队：输入序号选择，`b` 返回，`q` 取消，核对后输入 `y` 保存。`--search` 筛选部门；直接指定 `--tenant` 无需交互确认。取消时保留原选择。使用 `show` 核对选择，`refresh` 刷新目录。

### 6.4 示例

```bash
ml business list
ml business use
ml business use --search 云平台
ml business use --tenant mep --team team-a
ml business show
ml business refresh
```

## 7. 访问授权

### 7.1 命令格式

```text
ml access status [--diagnose]
```

### 7.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--diagnose` | 显示授权连接的排查信息 |

### 7.3 说明

先登录并选择业务。授权失败时按提示处理；需要排查连接时使用 `--diagnose`。分享诊断输出前隐藏账号与内部地址。

### 7.4 示例

```bash
ml access status
ml access status --diagnose
```

## 8. 当前用户

### 8.1 命令格式

```text
ml user info [--output table|json]
```

### 8.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 8.3 说明

显示当前登录用户的信息。需要将结果交给其他工具处理时可选 JSON 输出。

### 8.4 示例

```bash
ml user info
ml user info -o json
```

## 9. MEP 配置查询

### 9.1 命令格式

```text
ml mep config get [KEY] [--output table|json]
```

### 9.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `KEY` | 要查询的配置项名称；不填时查询默认项 |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 9.3 说明

此命令查询平台上的一个 MEP 配置项。若不确定配置项名称，请向管理员确认。

### 9.4 示例

```bash
ml mep config get
ml mep config get mep_service_access_type -o json
```

## 10. 训练看板

### 10.1 命令格式

```text
ml mtp swanboard project list
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard experiment feature list EXPERIMENT_ID
ml mtp swanboard experiment environment get EXPERIMENT_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID
ml mtp swanboard experiment config list EXPERIMENT_ID
ml mtp swanboard experiment inspect EXPERIMENT_ID
```

### 10.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `project list` | `--page`、`--page-size`、`--team-id`、`--creator` |
| `project namespace list` | `--team-id` |
| `project experiment list` | `--team-id` |
| `experiment feature list` | `--page`、`--page-size` |
| `experiment metrics` | 可重复使用 `--tag` 指定指标；不传时查询 `loss` 和 `accuracy` |
| 以上查询命令 | 均可使用 `--output` / `-o` 选择表格或 JSON |

### 10.3 说明

建议按“项目 → 项目空间 → 实验”的顺序取得所需 ID，再查询特性、环境、指标和配置。`inspect` 汇总实验信息，其中特性只展示第一页；需要更多特性时使用 `feature list` 翻页。各类 ID 不可混用。

### 10.4 示例

```bash
ml mtp swanboard project list --page 1
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss
ml mtp swanboard experiment inspect EXPERIMENT_ID -o json
```

## 11. 离线实验

### 11.1 命令格式

```text
ml offline experiment list [OPTIONS]
ml offline experiment trial list PROJECT_ID [OPTIONS]
ml offline experiment clone PROJECT_ID --name NAME [OPTIONS]
```

### 11.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `experiment list` | `--page`、`--page-size`、`--name` / `--project-name`、`--description`、`--create-user`、`--update-user`、`--team-id` |
| `experiment trial list` | `--page`、`--page-size`、`--name`、`--type`、`--creator`、`--updater`、`--ai-module` |
| `experiment clone` | 必填 `--name`；可选 `--dry-run` 预览、`--yes` / `-y` 跳过确认 |
| 以上命令 | `--output` / `-o` 选择表格或 JSON |

### 11.3 说明

`list` 查询当前业务的离线实验，`trial list` 查询某个实验下的 trial。克隆会创建新实验，不复制 trial；默认先预览并询问确认。仅想核对创建内容时使用 `--dry-run`。

### 11.4 示例

```bash
ml offline experiment list --name 训练 --page 1
ml offline experiment trial list PROJECT_ID --type batch
ml offline experiment clone PROJECT_ID --name 训练副本 --dry-run
ml offline experiment clone PROJECT_ID --name 训练副本
```

## 12. 训练任务

### 12.1 命令格式

```text
ml train list [OPTIONS]
ml train instance list TASK_ID
ml train history list TASK_ID
ml train start TASK_ID
ml train config export TASK_ID [--file PATH]
ml train history logs download TASK_ID JOB_ID [--file PATH]
ml train cancel TASK_ID [--yes]
ml train delete TASK_ID [--yes]
ml train clone TASK_ID --name NAME [OPTIONS]
ml train config update TASK_ID --customize-config VALUE
```

### 12.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--name`、`--page`、`--page-size`、`--output` / `-o` |
| `instance list`、`history list` | 必填 `TASK_ID`；可选 `--output` / `-o` |
| `start` | 必填 `TASK_ID`；执行后显示作业 ID |
| `config export` | 必填 `TASK_ID`；可选 `--file PATH` 指定保存位置 |
| `history logs download` | 必填 `TASK_ID`、`JOB_ID`；可选 `--file PATH`、`--output` / `-o` |
| `cancel`、`delete` | 必填 `TASK_ID`；可选 `--yes` / `-y` 跳过确认 |
| `clone` | 必填 `TASK_ID`、`--name NAME`；可选 `--customize-config VALUE`、`--yes` / `-y` |
| `config update` | 必填 `TASK_ID`、`--customize-config VALUE`；参数按字符串原样传递 |

### 12.3 说明

先用 `list` 获取任务 ID，`history list` 获取作业 ID。实例和执行记录默认展示第一页 10 条；`start` 返回作业 ID，不代表训练完成。

`cancel` 取消查询到的执行实例；`delete` 软删除任务；`clone` 创建副本；`config update` 更新自定义参数。操作结果不明时先查询状态。

配置导出为 YAML，日志默认下载为 ZIP；同名文件自动编号，`--file` 的父目录须存在。

### 12.4 示例

```bash
ml train list --name demo
ml train instance list TASK_ID
ml train history list TASK_ID
ml train start TASK_ID
ml train config export TASK_ID --file ./task.yaml
ml train history logs download TASK_ID JOB_ID --file ./logs.zip
ml train cancel TASK_ID
ml train delete TASK_ID
ml train clone TASK_ID --name 新任务 --customize-config 0096999
ml train config update TASK_ID --customize-config 0096999
```

## 13. 算法仓

### 13.1 命令格式

```text
ml algorithm list [OPTIONS]
ml algorithm download ALGORITHM_ID [--file PATH]
ml algorithm clone SOURCE_ID --name NAME --version VERSION [--yes]
```

### 13.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name` / `--algorithm-name`、`--bucket-name`、`--output` / `-o` |
| `download` | 必填 `ALGORITHM_ID`；可选 `--file PATH` |
| `clone` | 必填 `SOURCE_ID`、`--name NAME`、`--version VERSION`；可选 `--yes` / `-y` |

### 13.3 说明

先从列表获取算法仓 ID。下载保存为 ZIP，同名文件自动编号；`--file` 的父目录须存在。下载地址可能含临时签名，请勿公开分享。

克隆默认预览创建内容并询问确认，成功后显示结果及返回的新 ID。

### 13.4 示例

```bash
ml algorithm list --name mnist --page 1
ml algorithm download ALGORITHM_ID --file ./mnist.zip
ml algorithm clone SOURCE_ID --name mnist_copy --version VERSION
```

## 14. 服务管理

### 14.1 命令格式

```text
ml service list [OPTIONS]
ml service mock SERVICE_ID [--request-sample-file PATH] [--transmission-tag 0|1] [-o table|json]
ml service logs SERVICE_ID [--pod POD_NAME --cluster-name CLUSTER_NAME] [--type TYPE] [--file FILE_NAME] [-k TEXT] [-n N] [--list] [--no-input]
ml service host list SERVICE_ID [--pod-ip IP] [-o table|json]
ml service host mock SERVICE_ID --pod-ip POD_IP [--request-sample-file PATH] [--transmission-tag 0|1] [-o table|json]
ml service deployment list SERVICE_ID [-o table|json]
```

### 14.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`；可用 `--name` / `--service-name`、`--model-name`、`--model-version` 筛选；可选 `--output` / `-o` |
| `mock` | 必填 `SERVICE_ID`；`--transmission-tag` 默认 `0`，表示不调用透传接口，设为 `1` 表示调用透传接口，仅支持这两个整数；`--output` / `-o` 支持 `table`、`json`，默认沿用当前环境输出配置 |
| `mock`、`host mock` | 可选 `--request-sample-file PATH` 读取本地 UTF-8 JSON 文件，兼容 BOM；不传则使用服务文档中的请求样例 |
| `logs` | 必填 `SERVICE_ID`；可选成对的 `--pod` 与 `--cluster-name`，以及 `--type`、`--file`；`--keyword` / `-k` 可重复，`--lines` / `-n` 默认 200；`--list` 只列文件，`--no-input` 禁止交互；高级选项 `--search-order` 默认 tail、`--grep-scope` 默认 C、`--grep-line` 默认 0 |
| `host mock` | 必填 `SERVICE_ID` 和 `--pod-ip POD_IP`，按所传值查询主机视图；`--transmission-tag` 默认 `0`，仅支持 `0`、`1`，含义同 `mock`；可选 `--output` / `-o` |
| `host list` | 必填 `SERVICE_ID`；可选 `--pod-ip IP` 按 Pod IP 筛选，不传则不按 IP 筛选，不能传空值；可选 `--output` / `-o` |
| `deployment list` | 必填 `SERVICE_ID`；可选 `--output` / `-o` |

### 14.3 说明

先登录并选择业务，从 `list` 获取服务 ID。服务列表默认每页 10 条；主机和部署详情显示第一页 10 条，时间按北京时间显示。主机列表不展示主机ID列；podIP 按接口返回的完整 `IP:端口` 优先单行展示，便于复制，其他长字段可换行。

`ml service host list SERVICE_ID --pod-ip IP` 按指定 Pod IP 查询主机；主机测试命令 `host mock` 也使用所传 `--pod-ip` 查询主机视图。

`ml service mock SERVICE_ID` 自动查询服务名称、服务版本、所属租户，默认查询服务文档并使用其中的 JSON 请求样例执行一次测试。指定 `--request-sample-file PATH` 时使用自定义报文，不查询服务文档；因此只有使用默认样例时，服务才须已有有效请求样例。表格按主机展示主机名称、机器规格、站点、结果码、结果报文和耗时(ms)，结果报文解析为带缩进的 JSON，长内容完整换行显示。耗时使用平台返回值。

两个测试命令都可使用 `--request-sample-file PATH` 读取本地 UTF-8 JSON 文件，兼容 BOM，保留中文、空白和换行，不修改源文件。非法 JSON 在平台请求前提示“样例报文不是标准的JSON格式，请检查！”，文件不存在、不可读或编码错误时同样停止。文件路径含空格时加引号，报文正文直接写入文件，无需在命令行中转义 JSON。

`mock -o json` 保留接口其他字段，将 `result.nodeList` 中各节点的 `mockResponse` 转为 JSON 值，并以 `mockResponseRaw` 保留原始字符串。无效报文保留原文并提示错误，其他节点继续展示；没有节点、节点结果码缺失或非零、报文无效时退出码为 1。全部节点结果码为 0 且报文有效时退出码为 0，仅代表节点调用成功，具体业务结果须查看报文。接口失败或必要信息缺失时停止；认证失败、超时或断连不自动重发测试，执行结果可能未知。结果写入标准输出，诊断写入标准错误。

`ml service host mock` 先按 `--pod-ip` 查询主机视图，再使用默认文档样例或 `--request-sample-file` 指定的报文测试查到的主机。请求中的 `hostId` 取自该记录的 `nodeId`，`hostAddress` 原样取自 `nodeHost`，不手填主机ID，也不拼接端口。查无主机时提示“目前主机不存在，请检查！”，停止后续调用；匹配多台、查询失败或必要字段缺失时同样停止。表格按每个返回节点分别使用“字段 / 值”两列展示，行顺序为主机名称、机器规格、站点、结果码、耗时(ms)、结果报文，结果报文在最后一行完整展示缩进 JSON。JSON 输出和失败处理同 `mock`；Pod IP 提示写入标准错误，JSON 结果可单独重定向保存。

推荐使用 `ml service logs SERVICE_ID`。主机以表格展示编号、集群、pod名称、podIP、主机IP、状态、创建时间和更新时间，时间按北京时间显示；每页 10 条，先显示第一页，输入 n/p 按需翻页，输入 q 退出；选中后立即继续，不扫描剩余页。整个服务仅一台主机或仅一个文件时自动选择；类别无默认值，交互时以“编号、日志类别”表格展示，在“请选择日志类别”提示后输入编号，也可通过 `--type` 指定。文件选择仅展示一次文件表格，再输入编号，不重复列出文件名称。自动获取集群，Python 主机自动设置对应请求类型。`infer-python` 支持 run、interface、metrics、engine、ascend、mslite、alarm；`rtc` 支持 rtc、run、interface、dcs、metrics、gc、interface_manager、interface_extend、engine、monitor、catalina、dmq。文件列表和正文使用相同类别。

指定 `--pod` 时必须同时提供 `--cluster-name`；仅查询第一页，使用第一条主机的类型，直接查询指定 Pod 和集群，不验证其归属。请确保该服务主机类型一致且 Pod、集群填写正确。

非交互环境或指定 `--no-input` 时，选择不唯一会报错并提示补充参数；不默认选择第一台主机。未知主机类型、无匹配主机或文件会报错，文件列表为空时提示暂无日志文件。`--list` 不可与 `--file`、关键词、行数及正文检索选项混用，显式传入默认值也视为冲突；冲突时在请求平台前报错。默认读取末尾 200 行，不持续刷新；日志正文写入标准输出，选择提示和上下文写入标准错误，可将正文重定向保存。


### 14.4 示例

```bash
ml service list --name demo --model-name model --model-version MODEL_VERSION
ml service list --page 2 --page-size 20 -o json
ml service mock SERVICE_ID
ml service mock SERVICE_ID --transmission-tag 1
ml service mock SERVICE_ID --request-sample-file './sample.json'
ml service mock SERVICE_ID -o json > service-mock-result.json
ml service logs SERVICE_ID
ml service logs SERVICE_ID -k error -n 500
ml service logs SERVICE_ID --list
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME --no-input
ml service host list SERVICE_ID
ml service host list SERVICE_ID --pod-ip POD_IP -o json
ml service host mock SERVICE_ID --pod-ip POD_IP
ml service host mock SERVICE_ID --pod-ip POD_IP --request-sample-file './sample.json'
ml service host mock SERVICE_ID --pod-ip POD_IP --transmission-tag 1 -o json
ml service host mock SERVICE_ID --pod-ip "IPv6"
ml service deployment list SERVICE_ID -o json
```

## 15. 数据集

### 15.1 命令格式

```text
ml dataset list [OPTIONS]
ml dataset detail DATASET_ID [-o table|json]
ml dataset files list DATASET_ID [--dir REMOTE_DIR] [-o table|json]
ml dataset files upload DATASET_ID LOCAL_FILE [--dir REMOTE_DIR] [--timeout SECONDS] [-o table|json]
```

### 15.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`；可用 `--name` / `--dataset-name`、`--create-user`、`--update-user`、`--bucket-name` 筛选；可选 `--output` / `-o` |
| `detail` | 必填 `DATASET_ID`；可选 `--output` / `-o` |
| `files list` | 必填 `DATASET_ID`；`--dir` 默认 `/`；可选 `--output` / `-o` |
| `files upload` | 必填 `DATASET_ID`、`LOCAL_FILE`；`--dir` 默认 `/`；`--timeout` 默认 1800 秒，限制单次网络操作等待时间；可选 `--output` / `-o` |

### 15.3 说明

先登录并选择业务。`list` 默认显示第一页 10 条，`detail` 查看指定数据集。大小自动换算，时间按北京时间显示；JSON 保留平台返回的其他字段。

`files list` 查看当前目录，在表格上方显示“当前位置：完整路径”。支持颜色的终端中，文件夹整行显示为黄色，文件行保持默认颜色。完整路径列可用于下一次查询，例如 `/event/20240815`。空目录也显示当前位置；提示结果不完整时，不代表已列出所有文件。JSON 输出包含 `currentDir` 和保留原字段的 `response`。

`files upload` 向已有数据集追加单个文件，自动查询数据集名称。仅支持 `.txt`、`.csv`、`.zip`、`.tar`、`.gz`、`.json`，扩展名大小写均可。文件名以英文字母或数字开头，仅可包含英文字母、数字、下划线、连字符和点。本地路径可包含中文，但文件名不可包含中文。当前保守限制为 2,000,000,000 字节。终端显示发送进度；发送完成不等于服务端处理完成。超时或断连后先查询目录核实，不自动重传。同名文件与压缩包处理规则由平台决定，当前不提供覆盖、解压或断点续传选项。上传结果 JSON 保留平台响应；请求成功后可查询目录确认处理结果。

### 15.4 示例

```bash
ml dataset list --name dog_cat --create-user l00123456
ml dataset list --bucket-name sfs-turbo-mep-guian2 --page 2 --page-size 20
ml dataset detail DATASET_ID
ml dataset detail DATASET_ID -o json
ml dataset files list DATASET_ID
ml dataset files list DATASET_ID --dir /event
ml dataset files list DATASET_ID --dir /event/20240815 -o json
ml dataset files upload DATASET_ID ./sample.csv
ml dataset files upload DATASET_ID ./sample.csv --dir /logs --timeout 1800
```

## 16. 特征集

### 16.1 命令格式

```text
ml featureset wide export SET_ID [--lang zh_cn|en_us] [--file PATH] [--output text|json]
ml featureset model export SET_ID [--lang zh_cn|en_us] [--file PATH] [--output text|json]
ml featureset wide list [OPTIONS]
ml featureset model list [OPTIONS]
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

### 16.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `wide list`、`model list` | `--name`、`--page`、`--page-size`、`--output` / `-o` |
| `wide config`、`model config` | 必填 `SET_ID`；直接输出 JSON |
| `wide export`、`model export` | 必填 `SET_ID`；`--lang` 默认 `zh_cn`，可选 `en_us`；`--file PATH` 指定文件路径；`--output` / `-o` 默认 `text`，可选 `json` |

### 16.3 说明

`wide` 查询宽表特征集，`model` 查询模型特征集。列表展示 ID、名称、类型、场景和创建、修改信息；时间按北京时间显示。先从列表取得 `SET_ID`，再查看配置。配置查询固定输出 JSON，不提供 `--output` 选项。

导出前须登录并选择当前环境的业务。`wide export` 与 `model export` 分别用于导出宽表和模型特征集，原样保存服务端 CSV，保留编码、列及字段值。默认保存到当前目录，优先使用响应文件名，缺失时使用 `featuresInSet.csv`。重名时依次尝试 `featuresInSet (1).csv`、`featuresInSet (2).csv`，指定文件名同样自动编号，不覆盖已有文件；目标父目录须已存在。失败时清理临时文件。默认摘要显示最终绝对路径及自动换算的 B、KB、MB、GB 等大小单位，按 1024 换算，最多保留两位小数；JSON 摘要包含 `setId`、`lang`、`file` 和整数 `bytes`。`--lang` 控制服务端导出语言，`--output` 仅控制摘要格式。

### 16.4 示例

```bash
ml featureset wide export SET_ID
ml featureset model export SET_ID --lang en_us
ml featureset wide export SET_ID --file ./exports/features.csv -o json
ml featureset wide list --name demo
ml featureset model list --page 2 -o json
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

## 17. Jupyter Notebook 与远程终端

### 17.1 命令格式

```text
ml jupyter doctor [--studio-id ENV_ID]
ml jupyter notebook run SOURCE [OPTIONS]
ml jupyter terminal list [--studio-id ENV_ID]
ml jupyter terminal open [--studio-id ENV_ID]
ml jupyter terminal attach NAME [--studio-id ENV_ID]
ml jupyter terminal close NAME [--studio-id ENV_ID]
```

### 17.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `SOURCE` | 要执行的本地 `.ipynb` Notebook 文件 |
| `--download DIR` | Notebook 结果保存位置，默认 `results` |
| `--kernel NAME` | 指定 Kernel |
| `--cwd DIR` | 指定远程工作目录 |
| `--timeout SECONDS` | 代码执行时限，默认 600 秒 |
| `--startup-timeout SECONDS` | Kernel 启动等待时限，默认 60 秒 |
| `--output` / `-o` | Notebook 摘要使用 `text` 或 `json` |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，不改变默认选择 |

### 17.3 说明

使用前需由管理员开通 Jupyter 能力。`doctor` 检查连接；`notebook run` 在前台执行并保存结果，执行失败时也会尽可能保存已有输出。远程终端需服务端启用，`open` 创建终端，`attach` 连接现有终端，`close` 关闭终端。按 `Ctrl+]` 可断开当前连接而保留远程终端。

### 17.4 示例

```bash
ml jupyter doctor
ml jupyter notebook run analysis.ipynb --download results
ml jupyter terminal list
ml jupyter terminal open
ml jupyter terminal attach NAME
ml jupyter terminal close NAME
```

## 18. Web Studio

### 18.1 命令格式

```text
ml webstudio list [OPTIONS]
ml webstudio login ENV_ID [--refresh]
ml webstudio show
ml webstudio start ENV_ID
ml webstudio stop ENV_ID
```

### 18.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name`、`--status`、`--relator`、`--env-id`、`--business-id`、`--output` / `-o` |
| `login` | 必填实例 ID `ENV_ID`；`--refresh` 显式强制重新建立连接，普通登录同样获取新凭据 |
| `start`、`stop` | 必填实例 ID `ENV_ID` |
| `show` | 无参数 |

### 18.3 说明

先登录平台并选择业务，再使用 `list` 找到实例。`login` 选择默认实例并建立 Jupyter 连接；`show` 查看当前默认实例。`start` 和 `stop` 改变远程实例状态，并清除当前环境的连接缓存，不会改变默认选择。启动超时或中断时，先用 `list --env-id ENV_ID` 核对状态，再决定是否重试。

执行 Jupyter 命令时，标准错误输出显示目标提示：`目标Web Studio名称：STUDIO_NAME，envId：ENV_ID`，方便核对实例；`--output json` 的标准输出仍为 JSON 结果。

在 Jupyter 命令中使用 `--studio-id ENV_ID` 可临时操作其他实例，并复用该实例的有效连接缓存。连接按配置、环境、账号、业务和实例隔离；平台登录凭据变化后自动重新获取连接。

当前环境的 `jupyter.connection_cache_ttl_seconds` 默认 `3600` 秒（1 小时），可设为 `0` 禁用，最大 `3600` 秒。缓存保存临时 Token 和会话 Cookie，请勿分享用户配置目录中的 `webstudio-connections` 文件。到期后自动重新连接，`ml logout` 清除当前环境缓存，`ml logout --all` 清除全部缓存。每条命令仍按配置执行在线权限检查。

只读请求明确返回 HTTP 401 时最多刷新重试一次；HTTP 403 不自动重试。写操作、已提交的执行以及结果不明确的请求不自动重放。实例重启或连接失效后，可运行 `ml webstudio login ENV_ID --refresh`。

### 18.4 示例

```bash
ml webstudio list --status online
ml webstudio start ENV_ID
ml webstudio login ENV_ID
ml webstudio show
ml jupyter doctor --studio-id ENV_ID
ml webstudio login ENV_ID --refresh
ml webstudio stop ENV_ID
```

## 19. Jupyter 文件操作

### 19.1 命令格式

```text
ml jupyter files list [PATH] [OPTIONS]
ml jupyter files stat PATH [OPTIONS]
ml jupyter files read PATH [OPTIONS]
ml jupyter files write PATH (--from-file LOCAL | --stdin) [OPTIONS]
ml jupyter files mkdir PATH [OPTIONS]
ml jupyter files upload LOCAL REMOTE [OPTIONS]
ml jupyter files download REMOTE LOCAL [OPTIONS]
ml jupyter files move SOURCE TARGET [OPTIONS]
ml jupyter files copy SOURCE TARGET_DIR [OPTIONS]
ml jupyter files delete PATH [OPTIONS]
```

### 19.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `PATH`、`REMOTE`、`SOURCE`、`TARGET` | 远端路径，相对 Jupyter 根目录；`list` 省略 PATH 时查看根目录 |
| `LOCAL` | 本地文件路径；下载目标须含文件名且父目录存在 |
| `TARGET_DIR` | 已有远端目录；复制后的文件名以输出的 path 为准 |
| `--from-file LOCAL` / `--stdin` | 写入 UTF-8 文本，二选一；stdin 从标准输入读取至 EOF |
| `--overwrite` | write、upload、download 允许覆盖已有文件，默认不覆盖 |
| `--start-line N` / `--end-line N` | read 的行范围，含首尾；起始行默认 1 |
| `--output text\|json` / `-o` | 默认 text；Agent 使用 json |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，默认使用已选实例 |

### 19.3 说明

先选择环境、登录并选择业务。Web Studio 模式下执行 `ml webstudio login ENV_ID`；直连模式使用管理员提供的 Jupyter 配置。文件操作无需先打开远程终端。

远端路径从 Jupyter 文件浏览器最顶层开始，不是本机目录或服务器 `/`。先用 `files list` 查看根目录，再使用返回的 path；`projects` 仅为示例，不一定存在。路径不得以 `/` 开头或包含 `..`，终端中的 `cd` 不影响文件命令。

`list/stat/read` 分别查看目录、信息和正文。mkdir 的父目录须存在；move 不覆盖目标；delete 立即删除文件或空目录，不再确认。上传、下载、复制与删除不递归处理目录。避免与浏览器同时修改同一文件；行范围读取仍会下载完整文件，不宜用于超大文件。

JSON 结果位于 `result`，外层标明服务器、实例和业务。read 的正文在 `result.content`，时间按北京时间显示。成功退出 0，操作失败退出 1，参数错误退出 2。

### 19.4 示例

```bash
ml webstudio list --status online
ml webstudio login ENV_ID
ml jupyter files list --output json
ml jupyter files list projects --output json
ml jupyter files mkdir projects/demo
ml jupyter files write projects/demo/main.py --from-file ./main.py --output json
ml jupyter files stat projects/demo/main.py --output json
ml jupyter files read projects/demo/main.py --start-line 1 --end-line 80
ml jupyter files write projects/demo/main.py --from-file ./main.py --overwrite
ml jupyter files upload ./data.csv projects/demo/data.csv
ml jupyter files download projects/demo/data.csv ./downloaded.csv
ml jupyter files copy projects/demo/main.py projects
ml jupyter files move projects/demo/data.csv projects/demo/input.csv
ml jupyter files delete projects/demo/input.csv
```

## 20. Jupyter 非交互执行

### 20.1 命令格式

```text
ml jupyter exec [OPTIONS] -- PROGRAM [ARGS...]
```

### 20.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `PROGRAM [ARGS...]` | 远端程序及参数；放在 `--` 后，不隐式解释 Shell |
| `--cwd PATH` | 已有远端目录，相对 Jupyter 根目录；默认根目录 |
| `--timeout SECONDS` | 程序运行时限，默认 60 秒，最小 0.1 秒 |
| `--startup-timeout SECONDS` | Kernel 就绪等待时限，默认 60 秒 |
| `--kernel NAME` | Python Kernel 名称，默认使用当前环境配置 |
| `--max-output BYTES` | stdout/stderr 各自保留的字节上限，默认 1048576，最大 10485760 |
| `--output text\|json` / `-o` | 默认 text 为缩进 JSON；json 为单行结构化结果 |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，默认使用已选实例 |

### 20.3 说明

连接准备同文件操作。远端须为 Linux/macOS 等 POSIX 系统并提供 Python Kernel，本机可使用 Windows。每次执行使用独立 Kernel，不继承已有 Notebook 变量；程序通过远端 PATH 查找，也可指定程序绝对路径。

不支持交互输入；管道和重定向须显式使用 `sh -c`。执行完成后返回 stdout、stderr 和退出码，超过输出上限会标记 `truncated`。不用于启动后台常驻服务，完成或超时时会清理同组子进程，主动脱离进程组的进程不保证清理。

JSON 的 `result` 包含执行 ID、状态、原始退出码和输出。断线或 Ctrl+C 后先检查远端状态，不自动重跑；`cleanup_errors` 非空时按 kernel_id 检查遗留资源。

| 状态 | CLI 退出码 | 含义 |
| --- | --- | --- |
| `SUCCEEDED` | 0 | 执行成功 |
| `FAILED` | 原始退出码 1–123，其余为 1 | 执行或启动失败 |
| `TIMED_OUT` | 124 | 远端确认超时并终止进程组 |
| `LOST` | 2 | 连接中断或结果不完整，远端状态未知 |
| `INTERRUPTED` | 130 | 本地中断，远端不一定已停止 |

### 20.4 示例

```bash
ml jupyter exec --cwd projects/demo --output json -- python main.py
ml jupyter exec --cwd projects/demo --timeout 120 --output json -- python -m pytest -q
ml jupyter exec --cwd projects/demo --output json -- sh -c 'pwd && ls -la'
```


## 21. 模型查询

### 21.1 命令格式

```text
ml model list [--page PAGE] [--page-size SIZE] [--name NAME] [--type TYPE] [--owner OWNER] [--team-id TEAM_ID] [--output table|json]
ml model detail MODEL_ID [--output table|json]
ml model source MODEL_ID [--train-task] [--output table|json]
```

### 21.2 参数与选项

| 命令 | 参数或选项 | 用途 |
| --- | --- | --- |
| `list` | `--page PAGE` | 页码，默认 1，最小 1 |
| `list` | `--page-size SIZE` | 每页条数，默认 10，最小 1 |
| `list` | `--name NAME` | 模型名称条件，默认空字符串 |
| `list` | `--type TYPE` | 模型类型条件，未指定时不限制 |
| `list` | `--owner OWNER` | 归属者条件，未指定时不限制 |
| `list` | `--team-id TEAM_ID` | 团队条件，默认空字符串 |
| `detail`、`source` | `MODEL_ID` | 必填模型 ID，可从模型列表复制 |
| `source` | `--train-task` | 查询关联训练任务，默认不启用 |
| 三个命令 | `--output table\|json` / `-o` | 默认沿用当前环境输出配置，table 为面向人工的展示，json 为完整接口响应 |

### 21.3 说明

先选择环境、登录并选择业务。查询使用当前环境的业务编码；四个列表条件可以组合使用，匹配规则由平台决定。每次查询指定的一页，不自动获取全部模型；列表固定查询云侧模型，其他查询条件暂不开放修改。

列表展示模型 ID、名称、模型版本、业务编码、类型、创建时间、更新时间、归属者和团队，并显示分页信息。首列 ID 完整展示；长字段换行，缺失或空值显示 `-`，空列表显示“暂无模型”。带时区的时间转换为北京时间；不含时区的已格式化时间保持原值。

详情按“字段：值”展示算法类型、标签、大小、存储、来源等信息。模型大小取自模型包大小（`pkgSize`），按 1024 进制转换为 B、KB、MB、GB 等单位；KB 及以上保留两位小数，0 显示 `0 B`。JSON 输出保留接口中的原始字节数、时间及扩展字段，便于程序处理。

溯源先读取模型详情中的来源标识，再查询来源模型信息，展示输出名称、模型版本、敏感、业务编码、状态、创建时间、描述、来源和存储桶。敏感值为 1 显示“是”，否则“否”；状态值为 1 显示“已发布”，否则“未发布”。创建时间按北京时间展示。详情与溯源响应须明确返回成功状态，来源标识缺失时停止溯源；溯源 JSON 输出保留来源接口的完整原始响应。

指定 `--train-task` 时，根据溯源信息中的训练执行标识继续查询训练任务，依次展示 jobId、任务Id、任务名称、业务编码、任务类型、镜像、资源规格和历史记录数目。训练执行标识缺失或任一步查询失败时停止并报错。此模式的 JSON 输出为训练任务接口完整原始响应，不混入模型详情或溯源结果；不指定此选项时仍只查询和输出模型溯源信息。

### 21.4 示例

```bash
ml model list
ml model list --page 2 --page-size 20
ml model list --name MODEL_NAME --type MODEL_TYPE
ml model list --owner OWNER --team-id TEAM_ID
ml model list -o json
ml model detail MODEL_ID
ml model detail MODEL_ID -o json
ml model source MODEL_ID
ml model source MODEL_ID -o json
ml model source MODEL_ID --train-task
ml model source MODEL_ID --train-task -o json
```

## 22. 本地命令历史

### 22.1 命令格式

```text
ml history
ml history list [--limit COUNT] [--search TEXT] [--env ENV_NAME] [--status STATUS] [-o table|json]
ml history clear [--env ENV_NAME] [--before "YYYY-MM-DD HH:mm:ss"] [--yes]
ml --no-history COMMAND [ARGS]...
```

### 22.2 参数与选项

| 参数或选项 | 说明 |
| --- | --- |
| `ml history` | 无需参数，交互终端中每页 20 条，非交互时显示最近 20 条 |
| `--limit` | 最多显示条数，范围 1 至 1000；交互浏览默认包含全部匹配记录，非交互或 JSON 默认 20 条 |
| `--search` | 按命令内容包含关键字筛选，不区分大小写 |
| `--env` | 按执行前的环境筛选；清理时仅删除该环境记录 |
| `--status` | `success`、`failed` 或 `interrupted` |
| `--before` | 删除严格早于指定北京时间的记录，与环境筛选取交集 |
| `--yes` | 跳过清理确认；非交互执行清理时必须提供 |
| `--output` / `-o` | list 支持 table 或 json，默认 table |
| `--no-history` | 全局选项，放在子命令前，仅本次不记录 |

### 22.3 说明

`ml history` 和表格模式的 `ml history list` 在输入、输出均连接交互终端时启用翻页，每页 20 条，列表不显示序号。输入 `n` 后按回车查看下一页，`p` 返回上一页，`q` 或 Ctrl+C 退出。首尾页不循环，无效输入可重新输入。浏览使用进入时的固定记录快照，重新执行命令才能看到新记录。空列表直接返回；管道、重定向及 JSON 输出不等待输入。指定 `--limit` 时仅浏览该数量的匹配记录。

历史自动保存到本次配置文件同级的 UTF-8 文本文件 `history.jsonl`，每行一条记录，最多保留最近 1000 条，超过后清理开始时间最早的记录。同目录的 `history.lock` 用于协调多个终端。使用 `--config` 或 `ML_CONFIG` 指定其他配置时，历史随配置目录隔离。同一目录下的配置共用一份历史。

命令结束后记录开始时间、耗时、成功或失败状态、退出码、执行前后环境及经过脱敏的命令。正常 Ctrl+C 记录为中断；强制终止进程或断电可能不留记录，不显示执行中命令。时间按北京时间展示，不额外打印时区提示。环境切换记录中的环境列表示执行前环境，详情可查看切换后环境。

查看和清理历史无需登录、联网或有效的平台配置内容。帮助、版本、命令树、历史管理自身及内部后台活动不记录。设置 `ML_HISTORY=0` 关闭自动记录，仍可查询已有记录；环境变量的设置方式依使用的终端而定。

记录写入前隐藏敏感参数，不读取文件或标准输入内容，不保存输出及平台响应。Jupyter exec 的任意子进程参数整体隐藏；含脱敏或截断标记的命令不可直接完整复用。请勿在普通参数中嵌入敏感内容，不希望留存的调用使用 `--no-history`。本功能不会接管终端方向键，也不自动重新执行历史命令。

clear 先匹配记录再确认，确认期间新完成的记录保留。没有匹配项时显示清理 0 条。末尾损坏或无效的记录会被跳过并提示，下次更新时移除损坏行。目录不可写或文件忙时，自动保存只告警，不改变原命令结果；主动查询或清理失败则报错。

### 22.4 示例

```bash
ml history
ml history list --limit 50
ml history list --search "dataset files" --env ENV_NAME
ml history list --status failed -o json
ml history clear --before "2026-10-01 00:00:00"
ml history clear --env ENV_NAME --yes
ml history clear --yes
ml --no-history dataset list
ml --config CONFIG_PATH history
```


## 23. 资源模板查询

### 23.1 命令格式

```text
ml resource template list [OPTIONS]
ml resource template detail RESOURCE_TEMPLATE_ID [--output table|json]
```

### 23.2 参数与选项

| 命令 | 参数或选项 | 用途 |
| --- | --- | --- |
| `list` | `--page`、`--page-size` | 默认第 1 页、每页 10 条，均须为正整数 |
| `list` | `--name` | 模板名称条件，默认空字符串 |
| `list` | `--env` | 模板所属环境条件，默认不筛选，不切换 CLI 连接环境 |
| `list` | `--framework-name` | 推理框架包名称条件，默认空字符串 |
| `list` | `--framework-type` | 框架类型条件，默认不筛选 |
| `list` | `--resource-type`、`--template-type` | 资源类型和模板类型条件，均默认 `docker` |
| `detail` | `RESOURCE_TEMPLATE_ID` | 必填资源模板 ID，从列表第一列获取 |
| 两个命令 | `--output table\|json` / `-o` | 默认沿用当前环境输出配置 |

### 23.3 说明

先选择环境、登录并选择业务。列表条件可组合，匹配规则由平台决定；每次仅查询指定页。其他筛选条件暂不开放。

列表展示资源模板 ID、模板名称、环境、YAML 模板名、镜像名称、镜像标签、业务编码、集群名称、创建时间、更新时间和状态，并显示分页信息。首列 ID 完整展示，长字段换行；状态为 0 显示“在用”，其他有效值显示“停用”，缺失值显示 `-`。时间按北京时间展示；不带时区的时间已是北京时间，不重复转换。

详情按“1、基本信息”“2、推理框架”“3、扩展信息”展示，下级配置组及扩展信息类别使用层级编号，表格内字段和数据行不编号，带编号的标题统一使用青色。资源类型为 docker 显示“容器”，其他有效值显示“虚拟机”；框架类型 rtc、gateway、algo 分别显示“推理框架”“网关框架”“算子框架”，其他值保留原文，缺失值显示 `-`。镜像名称与标签使用空格分隔；配额类型为 guaranteed 显示“核心配额”，其他有效值显示“弹性配额”。默认资源规格由 CPU、以 G 为单位的内存及 NPU 组合，例如 `1C2G`、`4C8G1NPU`，NPU 为零时省略。环境变量、Hosts 映射、主机调度和启动参数分别展示，启动参数保持原顺序，自定义启动命令仅显示。

框架名称由关联框架包的名称与标识通过 `@` 连接，参数配置逐组展示，密码和 Secret 等值原样显示。未关联框架时显示提示；关联框架查询失败时保留资源模板详情并报错。参数配置解析失败时仍显示其他详情，命令返回失败。

列表 JSON 输出为完整接口响应；详情 JSON 输出包含 `resourceTemplate` 和 `frameworkPackage` 两个接口响应，未关联框架或框架查询失败时后者为 null，查询失败仍返回非零退出码。JSON 保留额外字段、原始时间、状态和框架配置字符串，敏感值不脱敏。

### 23.4 示例

```bash
ml resource template list
ml resource template list --name TEMPLATE_NAME --env TEMPLATE_ENV
ml resource template list --framework-name FRAMEWORK_NAME --framework-type FRAMEWORK_TYPE
ml resource template list --resource-type RESOURCE_TYPE --template-type TEMPLATE_TYPE
ml resource template list --page 2 --page-size 20 -o json
ml resource template detail RESOURCE_TEMPLATE_ID
ml resource template detail RESOURCE_TEMPLATE_ID -o json
```


## 24. 部署模板查询

### 24.1 命令格式

```text
ml deployment template list [OPTIONS]
ml deployment template detail DEPLOY_TEMPLATE_ID [--output table|json]
```

### 24.2 参数与选项

| 命令 | 参数或选项 | 用途 |
| --- | --- | --- |
| `list` | `--page`、`--page-size` | 默认第 1 页、每页 10 条，均须为正整数 |
| `list` | `--name` | 部署模板名称条件，未指定时不筛选 |
| `list` | `--framework-name` | 推理框架包名称条件，默认空字符串 |
| `list` | `--env` | 模板所属环境条件，默认不筛选，不切换 CLI 连接环境 |
| `list` | `--framework-type` | 框架类型条件，默认不筛选 |
| `detail` | `DEPLOY_TEMPLATE_ID` | 必填部署模板 ID，从列表第一列获取 |
| 两个命令 | `--output table\|json` / `-o` | 默认沿用当前环境输出配置 |

### 24.3 说明

先选择环境、登录并选择业务。列表开放部署模板名称、框架包名称、模板环境和框架类型四个筛选条件，可组合使用，匹配规则由平台决定。每次只查询指定页，其他条件保持平台默认值。

列表展示部署模板 ID、模板名称、环境、业务编码、组件包、模板类型、资源模板、推理类型、是否默认模板、创建时间、更新时间和是否系统模板。首列 ID 完整展示，长字段换行；多个组件以 `名称@标识` 形式用英文逗号连接，多个资源模板名称也用英文逗号连接。默认模板和系统模板标志为数字 0 或字符串 "0" 时显示“否”，其他有效值显示“是”，缺失值显示 `-`。时间按北京时间展示，毫秒时间戳正确转换。

详情按“1、基本信息”“2、健康检查参数”“3、容器资源模板”三个区块展示，仅区块标题编号，表格内字段和关联资源行不编号，带编号的标题统一使用青色。基本信息中的资源模板类型为 docker 时显示“容器”，其他有效值显示“虚拟机”，缺失值显示 `-`。基本信息区分自定义组件与平台公共组件，推理类型 online 显示“在线推理”、offline 显示“离线推理”，其他值保留原文；最大并发数与调用方超时分别展示，超时单位为毫秒。健康检查类型为 httpGet 时显示“http”，为 tcpSocket 时显示“tcp”，其他类型保留原值。健康检查时间参数按字段标注秒，不健康阈值展示原值。

详情自动展开全部关联容器资源模板，使用部署模板的模板类型、业务编码和每个关联名称查询，不分页，再按名称完全相等筛选。关联资源表展示模板名称、YAML 模板名、镜像名称、镜像标签、集群名称、实例数、创建时间、更新时间和状态，不展示容器类别。资源状态为 0 显示“在用”，其他有效值显示“停用”。没有关联项时正常显示提示；关联项查询失败、没有精确匹配或存在多个同名项时，保留其他结果并返回非零退出码，同名项全部展示。

列表 JSON 为完整接口响应。详情 JSON 包含 `deploymentTemplate` 和 `resourceTemplates`，后者逐项包含查询名称 `requestedName`、完整关联查询响应 `response`、精确匹配数据 `exactMatches` 及错误 `error`；正常项的 error 为 null。保留原始时间、标志及额外字段，敏感值不脱敏。

### 24.4 示例

```bash
ml deployment template list
ml deployment template list --name TEMPLATE_NAME --env TEMPLATE_ENV
ml deployment template list --framework-name FRAMEWORK_NAME --framework-type FRAMEWORK_TYPE
ml deployment template list --page 2 --page-size 20 -o json
ml deployment template detail DEPLOY_TEMPLATE_ID
ml deployment template detail DEPLOY_TEMPLATE_ID -o json
```


## 25. 模型部署

### 25.1 命令格式

```text
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID [OPTIONS]
```

### 25.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `MODEL_ID` | 必填模型 ID，从 `ml model list` 获取 |
| `--template DEPLOY_TEMPLATE_ID` | 必填部署模板 ID，从 `ml deployment template list` 获取 |
| `--service-timeout MILLISECONDS` | 调用方最大容忍超时时间，单位毫秒，必须为正整数；显式参数优先，否则读取模板，两处均缺失时必须补充 |
| `--execute-limit COUNT` | 单实例最大并发数，必须为非负整数；显式参数优先，否则读取模板，两处均缺失时必须补充 |
| `--qps COUNT` | 单实例最大 QPS，必须为正整数；未指定时不提交该字段 |
| `--update-mode rolling\|in-place` | 滚动更新或原地更新，默认 rolling |
| `--health-check-mode default\|response-code\|response-code-and-data` | 默认检查、响应码匹配、响应码及数据匹配，默认 default；无需额外匹配参数 |
| `--health-port PORT` | 健康检查端口，默认 18090，范围 1 至 65535 |
| `--description TEXT` | 服务文档描述，默认空字符串 |
| `--request-file FILE`、`--response-file FILE` | UTF-8 输入和输出报文文件，路径相对于当前工作目录，文本原样读取；未指定时为空字符串 |
| `--dry-run` | 查询、校验并预览，不提交部署 |
| `--yes` | 跳过交互确认；非交互环境提交时必填 |
| `--output table\|json` / `-o` | 默认沿用当前环境输出配置 |

### 25.3 说明

先选择环境、登录并选择业务，准备模型及部署模板 ID。部署模板必须关联至少一个有效容器资源模板，关联几个资源模板就部署几个区域，不支持区域选择或配置覆盖文件。每个关联名称必须精确匹配唯一资源模板，缺失、同名歧义或查询失败时不提交部署。模板及资源必须提供必填配置，框架配置必须为有效的非空 JSON 对象。

服务名称及服务版本分别沿用所选模型的名称及版本，不另行指定。最大并发数和调用超时优先使用命令参数，未传时读取部署模板；模板和命令均未提供时，一次列出缺少的参数并给出带占位符的重试命令，不提交部署。组件包包括自定义和公共组件。各区域沿用资源模板的镜像、资源规格、框架参数、环境变量、Hosts、主机标签、启动参数及自定义启动命令。实际提交实例数固定为 1，不继承资源模板实例数，不配置弹性伸缩。GPU、NPU 数量缺失、为 null 或空字符串时按 0 提交，已有值原样保留；CPU 和内存仍须配置。资源模板中的主机标签、Hosts 映射、环境变量和启动参数未配置或为 null 时按空列表提交，无需为了部署专门配置；非空配置须为列表。自定义启动命令和 SFS 路径缺失或为 null 时按空字符串提交；模型来源环境、团队缺失时使用空字符串，标签、历史副本及组件包列表缺失或为 null 时使用空列表。已有值保留，非字符串命令或路径、非列表集合仍报错。

健康检查优先使用部署模板值，仅在缺失、null 或空字符串时采用默认值：检查类型 httpGet、检查方法 health、检查超时 5 秒、拉起超时 120 秒、延迟检查 120 秒、检查间隔 10 秒、不健康阈值 3、优雅下线时间 10 秒。告警上报领域取当前业务所属真实租户的首个服务组，不提供选择参数。

提交前按基本信息、部署区域、扩展参数、服务文档四部分展示。基本信息仅展示模型名称、模型版本、部署方式、更新模式、环境、推理类型、单实例最大 QPS、最大并发数、调用超时及自定义和公共组件包，未指定 QPS 显示 `-`。区域标题使用集群名称。每个区域单独展示基本信息、推理框架及完整分组参数、弹性开关和扩展信息，框架名使用名称与标识通过 `@` 连接；实例数展示实际提交值 1，区域名称和描述为空时显示“未填写”。服务文档显示描述及完整输入、输出报文，保留多行文本格式。编号标题统一青色加粗，表格内不编号。交互环境确认后提交；拒绝确认则取消。JSON 模式的摘要及确认写入标准错误，标准输出仅包含发布接口响应；`--dry-run -o json` 输出完整待提交请求，包括原样框架参数及敏感值。

接口结果码为 0 时显示部署成功和服务 ID；非零时显示失败原因并返回非零退出码，不解析描述文本判断结果。响应缺少有效结果码、请求超时或连接异常时，提交结果未确认，应先用 `ml service list` 查询，再决定是否重试。发布请求不自动重放。预览后账号、环境或业务变化时停止提交，需要重新执行命令。

### 25.4 示例

```bash
ml model list
ml deployment template list
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run -o json
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --service-timeout 3000 --execute-limit 100
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --qps 100 --update-mode in-place
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --health-check-mode response-code --health-port 18090
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --description SERVICE_DESCRIPTION --request-file REQUEST_FILE --response-file RESPONSE_FILE
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes -o json
```

## 运行上下文

### 命令格式

```text
ml [--config PATH] context [--json]
```

### 参数与选项

| 参数 | 说明 |
| --- | --- |
| `--config PATH` | 全局选项，指定配置文件；也可使用 ML_CONFIG |
| `--json` | 输出结构化 JSON；默认输出表格 |

### 说明

无需登录，不请求平台接口。显示实际运行模式、当前环境、平台地址、CLI 路径、配置路径和状态目录；不显示凭据或地址中的认证参数。“真实平台”表示连接真实服务，不代表当前环境一定是生产环境。独立演示环境还显示工作区和场景。配置无效时返回错误，不推测运行状态。

### 示例

```bash
ml context
ml context --json
ml --config /path/to/config.json context
```


## 特征任务列表

### 命令格式

```text
ml feature-task list [--name TEXT] [--category TYPE] [--create-user USER] [--page INTEGER] [--page-size INTEGER] [--output table|json]
```

### 参数与选项

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--name TEXT` | 空 | 按任务名称查询，匹配规则由平台决定 |
| `--category TYPE` | `dpp-all` | 按任务类型查询，使用下表中的原始值 |
| `--create-user USER` | 空 | 按创建者查询 |
| `--page INTEGER` | `1` | 查询页码，必须为正整数 |
| `--page-size INTEGER` | `10` | 每页条数，必须为正整数 |
| `--output`、`-o` | 当前环境配置 | `table` 或 `json` |

### 说明

先选择环境、登录并使用 `ml business use` 选择业务。查询当前环境下已选业务的特征任务，不支持通过本命令指定其他业务。三个筛选条件可组合使用，一次只查询指定的一页。

表格依次展示任务 ID、任务名称、任务类型、业务场景、状态、创建者、修改者、更新时间、大小、描述。任务 ID 完整展示，其他长文本可换行。更新时间按北京时间显示为 `YYYY-MM-DD HH:mm:ss`；大小按 1024 进制换算，零显示 `0B`，非零且不足 1 GiB 显示两位小数的 `M`，其余显示两位小数的 `G`。缺失值显示 `-`，未知任务类型保留原值。列表下方显示页码、每页条数和总条数。

JSON 输出包含 `items`、`count`、`pageIndex`、`pageSize`；记录保留原始字段、任务类型、毫秒时间戳和字节数，适用于脚本处理。

| 任务类型原始值 | 展示名称 |
| --- | --- |
| `dpp-all` | 全部 |
| `feature_preprocess_realtime` | 特征预处理(实时) |
| `train_fi` | FI直连任务 |
| `data_sync` | 数据同步任务 |
| `data-preproc` | 数据预处理任务 |
| `feature_generate` | 特征生成任务 |
| `feature_evaluation` | 特征评估任务 |
| `feature_improve` | 特征加工任务 |
| `work_flow` | 特征工作流任务 |
| `feature-push` | 特征同步任务 |
| `train_spark` | Spark训练任务 |
| `train_fi_sync_hdfs` | FI直连同步HDFS任务 |
| `train_fi_data_monitor` | FI直连数据监控任务 |
| `generate_samples` | 样本生成任务 |
| `sample-monitor` | 样本监控任务 |
| `online_storage` | 在线存储任务 |
| `streaming_feature` | 流特征任务 |

### 示例

```bash
ml feature-task list
ml feature-task list --name TASK_NAME --category train_fi
ml feature-task list --create-user USER --page 2 --page-size 20
ml feature-task list --category feature_generate -o json
```


## 特征任务执行记录

### 命令格式

```text
ml feature-task execution list TASK_ID [--page INTEGER] [--page-size INTEGER] [--include-history] [--output table|json]
```

### 参数与选项

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 必填 | 特征任务 ID |
| `--page` | `1` | 正整数页码 |
| `--page-size` | `10` | 每页条数，正整数 |
| `--include-history` | 不开启 | 包含历史执行实例 |
| `--output`、`-o` | 当前环境配置 | `table` 或 `json` |

### 说明

先选择环境、登录并选择业务。一次查询指定页，保留服务端排序，默认不包含历史执行实例。

表格展示 job ID、算法名称、CPU、GPU、内存、状态、集群、节点数、大小、执行时长、最新实例、检查时间、开始时间、结束时间。首列 ID 完整展示，其余长内容可换行。时间按北京时间显示；大小按 1024 进制转换为 B、K、M、G；执行时长按分钟换算为小时和分钟；最新实例显示“是”或“否”，缺失字段显示 `-`。JSON 输出包含 `items`、`count`、`pageIndex`、`pageSize`，保留完整记录及原始值。

### 示例

```bash
ml feature-task execution list TASK_ID
ml feature-task execution list TASK_ID --page 2 --page-size 20 --include-history
ml feature-task execution list TASK_ID -o json
```

## 特征任务执行日志

### 命令格式

```text
ml feature-task execution logs search JOB_ID [--start-line INTEGER] [--end-line INTEGER] [--keyword TEXT] [--scope A|B|C] [--scope-lines INTEGER] [--output text|json]
```

### 参数与选项

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `JOB_ID` | 必填 | 执行记录 job ID |
| `--start-line` | `1` | 起始行，正整数 |
| `--end-line` | `2000` | 结束行，正整数，不得小于起始行 |
| `--keyword` | 不指定 | 关键词，可重复传入，不允许空白字符串 |
| `--scope` | 不指定 | A 为关键词后，B 为关键词前，C 为关键词前后 |
| `--scope-lines` | 不指定 | 搜索范围行数，正整数 |
| `--output`、`-o` | `text` | `text` 原样展示日志正文，`json` 输出完整响应 |

### 说明

先选择环境、登录并选择业务。业务来源于当前环境的选择，不支持参数覆盖。未指定关键词或范围选项时不发送对应条件；多个关键词的匹配关系由服务端决定。不自动轮询日志。默认原样显示第一个日志条目的正文，保留空格、制表符和换行，不添加标题、表格或额外换行；无日志时不输出正文。`-o json` 保留完整接口响应，包括所有日志条目及总行数。认证提示和错误写入标准错误，不混入日志正文或 JSON 输出。

### 示例

```bash
ml feature-task execution logs search JOB_ID
ml feature-task execution logs search JOB_ID --start-line 2001 --end-line 4000
ml feature-task execution logs search JOB_ID --keyword ERROR --keyword Exception --scope C --scope-lines 20
```


## 样本任务列表

### 命令格式

```bash
ml sample-task list [--source legacy|new] [--page PAGE] [--page-size SIZE] [--name TASK_NAME] [--creator USER] [--updater USER] [--type TYPE] [--status all|stopped|started] [--sort desc] [--output table|json]
```

### 参数与选项

| 参数 | 说明 |
| --- | --- |
| `--source` | 默认 `legacy`，查询“任务管理”；`new` 查询“任务管理（新）” |
| `--page` | 正整数，默认第 1 页 |
| `--page-size` | 正整数，默认每页 10 条 |
| `--name` | 可选任务名称 |
| `--creator` / `--updater` | 可选创建者、修改者 |
| `--type` | 可重复指定类型，使用下表中对应来源的枚举值 |
| `--status` | 仅旧版支持：`all` 全部、`stopped` 已停止、`started` 已启动；默认全部 |
| `--sort` | 仅新版支持，目前仅支持 `desc`，新版默认使用该值 |
| `--output` / `-o` | `table` 或 `json`，未指定时使用当前环境配置 |

### 说明

先通过 `ml env use ENV_NAME` 选择环境、`ml login` 登录，再通过 `ml business use` 选择租户或团队。请求使用当前环境所选业务，不支持通过参数覆盖业务 ID。

不加参数默认查询旧任务管理。旧版默认查询特征预处理实时、特征预处理离线、特征装配和标签装配四种类型；指定 `--type` 后替换此默认范围。新版默认不限类型。两套列表分别查询，每次只取指定的一页，不自动合并或拉取全部任务。来源不支持的筛选项会报错。

| 旧版类型 | 中文名称 |
| --- | --- |
| `feature_preprocess_realtime` | 特征预处理(实时) |
| `feature_preprocess_offline` | 特征预处理(离线) |
| `feature_assemble` | 特征装配 |
| `label_assemble` | 标签装配 |
| `feature_monitor` | 样本监控 |
| `new_feature_assemble` | 新特征装配 |
| `spark_jar` | spark_jar |

| 新版类型 | 中文名称 |
| --- | --- |
| `FEATURE_ASSEMBLE` | 特征装配任务 |
| `LABEL_ASSEMBLE` | 标签装配任务 |
| `FEATURE_SYNC` | 特征同步任务 |
| `FEATURE_IMPORT_OFFLINE` | 离线特征导入任务 |
| `FEATURE_IMPORT_REALTIME` | 实时特征导入任务 |
| `OFFLINE_FEATURE_SYNC` | 离线特征回流同步任务 |
| `FEATURE_PREPROCESS_OFFLINE` | 预处理任务 |
| `FEATURE_QUALITY_MONITOR` | 监控任务 |
| `OFFLINE_FEEDBACK` | 离线回流任务 |
| `REAL_TIME_FEEDBACK` | 实时回流任务 |
| `REALTIME_LABEL_CALC` | 实时标签计算任务 |
| `SAMPLE_GENERATION_OFFLINE` | 样本生成离线任务 |
| `SAMPLE_GENERATION_REALTIME` | 样本生成实时任务 |

表格展示任务 ID、名称、中文类型、创建者、修改者、最近修改时间和描述；新版还展示创建时间、开始执行时间和任务状态。开始执行时间使用平台返回的最近执行时间。空值显示为 `-`，任务 ID 完整显示。时间戳和带时区的时间按北京时间展示，无时区时间按服务端原值展示。表格显示来源与分页信息。

JSON 输出包含 `source`、`page`、`pageSize`、`total`、`items`，其中任务记录保留服务端原字段、原始时间和空值。空列表为正常结果；请求失败则返回非零退出码并输出错误信息。

### 示例

```bash
ml sample-task list
ml sample-task list --source legacy --status stopped --type feature_preprocess_offline
ml sample-task list --source new
ml sample-task list --source new --type FEATURE_ASSEMBLE --type FEATURE_SYNC
ml sample-task list --name TASK_NAME --creator USER --updater USER
ml sample-task list --source new --page 2 --page-size 20 -o json
```


## 样本任务执行周期

### 命令格式

```bash
ml sample-task period list TASK_ID [--page PAGE] [--page-size SIZE] [--start-time TIME] [--end-time TIME] [--state STATE] [--output table|json]
```

### 参数与选项

| 参数 | 说明 |
| --- | --- |
| `TASK_ID` | 必填，新版样本任务 ID |
| `--page` | 正整数，默认 1 |
| `--page-size` | 正整数，默认 20 |
| `--start-time` / `--end-time` | 可选周期日期边界，按北京时间输入 `YYYY-MM-DD HH:mm:ss`；可只指定一端 |
| `--state` | 可重复指定运行状态，默认不限状态 |
| `--output` / `-o` | `table` 或 `json`，默认使用当前环境配置 |

### 说明

先选择环境、登录并通过 `ml business use` 选择租户或团队。仅用于“任务管理（新）”，无需添加 `--source new`。可通过 `ml sample-task list --source new` 获取任务 ID。开始日期不得晚于结束日期。

| 状态值 | 中文名称 |
| --- | --- |
| `INIT` | 初始化 |
| `CANCELED` | 已取消 |
| `QUEUE` | 排队中 |
| `APPLY_FOR_RESOURCE` | 申请资源 |
| `WAIT_FOR_QUOTA_QUEUE` | 等待中 |
| `RUNNING` | 运行中 |
| `COMPLETED` | 运行成功 |
| `FAILED` | 执行失败 |
| `LACK_RESOURCE` | 资源不足 |
| `TIMEOUT` | 超时 |
| `QUEUE_TIMEOUT` | 排队超时 |
| `QUOTA_WAIT_TIMEOUT` | 配额等待失败 |
| `FORCE_STOP` | 强制停止 |

表格为无表头的四列网格，每格展示页内编号、周期和中文状态，按返回顺序从左往右填充，每页编号从 1 开始。只补齐最后一行；例如 7 条显示两行，最后一格为空。默认 20 条最多五行，指定更大的每页条数时相应增加行数。窄终端允许格内换行。空列表不绘制网格。

每次只查询指定页，显示任务 ID 和分页总数。JSON 包含 `taskId`、`page`、`pageSize`、`total`、`items`，记录保留原始字段，不增加网格编号、不转换状态。错误返回非零退出码。

### 示例

```bash
ml sample-task period list TASK_ID
ml sample-task period list TASK_ID --state COMPLETED --state FAILED
ml sample-task period list TASK_ID --start-time "2026-10-01 00:00:00" --end-time "2026-10-21 23:59:59"
ml sample-task period list TASK_ID --page 2 --page-size 20 -o json
```

## 样本任务执行记录

### 命令格式

```bash
ml sample-task execution list TASK_ID [--page PAGE] [--page-size SIZE] [--include-history] [--output table|json]
```

### 参数与选项

| 参数 | 说明 |
| --- | --- |
| `TASK_ID` | 必填，新版样本任务 ID |
| `--page` | 正整数，默认 1 |
| `--page-size` | 正整数，默认 10 |
| `--include-history` | 包含历史实例，默认关闭 |
| `--output` / `-o` | `table` 或 `json`，默认使用当前环境配置 |

### 说明

先选择环境、登录并选择租户或团队。仅用于“任务管理（新）”，无需添加 `--source new`。默认不包含历史实例，每次只查询指定页。

表格展示 JOB ID、算法名称、状态、文件大小、周期时间、执行时长、最新实例、检查时间、开始时间和结束时间。JOB ID 完整显示；周期时间保留原值，时间戳及带时区时间转换为北京时间。文件大小按 1024 进制显示，执行时长按分钟转换，例如 232 分钟显示为 `3h52min`，最新实例显示为“是”或“否”，空值显示为 `-`。

状态 `COMPLETED` 显示为“执行完成”、`FAILED` 为“执行失败”、`CANCELED` 为“取消”，未知状态保留原值。JSON 包含 `taskId`、`page`、`pageSize`、`total`、`items`，保留原始记录及所有额外字段，不进行展示转换。空列表正常返回，接口错误返回非零退出码。

### 示例

```bash
ml sample-task execution list TASK_ID
ml sample-task execution list TASK_ID --include-history
ml sample-task execution list TASK_ID --page 2 --page-size 20
ml sample-task execution list TASK_ID -o json
```
