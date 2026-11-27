# 训练任务、样本任务、离线实验、算法仓与训练看板

以下查询与操作默认使用 `--agent` 获取紧凑精简 JSON（不要与 `-o json` 同传）；仅在需要完整原始响应时去掉 `--agent` 改用 `-o json`。直接按下方与 [命令速查](commands.md) 的参数签名调用，无需预先执行 `--help`。

**高频最短链路**：
- **查任务并下日志**：`ml train list --name 'NAME,NAME' --agent` → `ml train history list TASK_ID --latest-flag all --agent`（普通看 `plogReady`，分布式看 `roleJobInfo[].roleJobId`/`plogReady`）→ `ml train history logs download TASK_ID JOB_ID [--role-job-id ID] [--type plog] --directory DIR --agent`
- **训练看板**：`project list` → `project namespace list PROJECT_ID` → `project experiment list PROJECT_ID NAMESPACE_ID` → `experiment metrics EXPERIMENT_ID`

## 下载训练执行记录日志

参数齐全时直接运行 `ml train history logs download TASK_ID JOB_ID --agent`（未就绪时自动触发归档属低风险操作，含 `product` 环境在内均无需二次确认）。仅分布式训练（`jobType=dps-train`）支持 `--role-job-id`，在非交互或 Agent/JSON 模式下必填，多个指定角色逐个下载；普通训练不要传 `--role-job-id`。交互终端使用表格输出时可按编号选角色。

- **缺少 ID**：已知完整任务名时优先用 `ml train list --name 'NAME,NAME' --agent` 精确查 `TASK_ID`（未命中或仅知关键词时回退 `--name NAME`），用 `ml train history list TASK_ID --agent`（默认第 1 页 10 条，未找到可加 `--page-size 200` 或翻页，查询历史实例加 `--latest-flag all`）查 `JOB_ID` 或从目标记录的 `roleJobInfo` 取 `roleJobId`。下载流程中禁止调用 `ml train history detail`。
- **可选参数**：默认下载普通日志，`--type plog` 仅在记录已有 plog（Agent 模式下 `plogReady=true`）时下载，无 plog 直接报错且不触发归档。`--directory DIR` 指定已存在的保存目录，默认当前目录。`--agent` 输出紧凑结果摘要。
- **下载结果**：成功时报告保存路径。普通日志未就绪时，命令会提交归档并以退出码 1 返回；普通训练顶层 `status` 为 `not_ready`，分布式训练顶层 `status` 为 `failed` 且 `items[].status` 为 `not_ready`，均表示已触发归档，稍后重跑同一命令，勿误判为下载异常。提示“该job无分布式角色，无日志可下载”时，报告该作业没有可下载的角色日志。

`ml train instance list TASK_ID --agent` 的 `runningTime` 单位为分钟（若运行中实例接口未返回该字段，可结合 `createTime` 推算）。取执行实例归档日志时，用 `ml train instance list TASK_ID --agent` 查运行或排队实例，再用 `ml train instance logs download ... --agent` 按编号下载。

## 训练看板（MTP Swanboard）

按“项目 → 项目空间 → 实验 → 实验数据”逐级定位：

```powershell
ml mtp swanboard project list --agent
ml mtp swanboard project namespace list PROJECT_ID --agent
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID --agent
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy --agent
```

- 项目 ID、空间 ID 和实验 ID 不互换。`--team-id` 只筛选结果，不切换当前业务。
- `metrics` 返回统计值，不是完整时间序列；`--tag` 可重复。
- `inspect` 会发起多次请求，其中特性只含第一页；只需单项信息时直接用对应子命令。

## 离线实验

```powershell
ml offline experiment list --name NAME --agent
ml offline experiment trial list PROJECT_ID --agent
ml offline experiment clone PROJECT_ID --name NEW_NAME --dry-run --agent
ml offline experiment clone PROJECT_ID --name NEW_NAME --yes --agent
```

克隆前先用 `--dry-run` 核对源实验和新名称；用户授权后再加 `--yes` 提交。结果不明时先按新名称查询，不重复提交。

## 训练任务

```powershell
ml train list --name 'NAME,NAME' --agent
ml train list --name NAME --agent
ml train list -A --name NAME --agent
ml train detail TASK_ID --agent
ml train instance list TASK_ID --page 2 --page-size 20 --agent
ml train history list TASK_ID --page 2 --page-size 20 --agent
ml train history list TASK_ID --latest-flag all --agent
ml train history logs download TASK_ID JOB_ID --directory 'D:\logs' --agent
ml train history logs download TASK_ID JOB_ID --role-job-id ROLE_JOB_ID --directory 'D:\logs' --agent
ml train history logs download TASK_ID JOB_ID --type plog --role-job-id ROLE_JOB_ID --directory 'D:\logs' --agent
ml train instance logs download TASK_ID JOB_ID --select 2 --directory 'D:\logs' --agent
ml train instance logs download TASK_ID JOB_ID --select '1,3' --directory 'D:\logs' --agent
ml train instance logs download TASK_ID JOB_ID --select all --directory 'D:\logs' --agent
```

- WiseRec 和 MLOps 均支持训练任务查询、启动、取消、软删除、克隆、配置管理、执行实例及执行记录查询和日志下载。MLOps 的 `train list --page-size` 最大为 200。
- `detail` 使用 `train list` 中的任务 ID，结果含基本信息、首个样本的数据集、输出引用及首个样本的配置引用、算法参数及自定义参数。
- `instance list` 和 `history list` 默认返回第一页 10 条，支持 `--page` 和 `--page-size`（每页 1 至 200 条），按接口返回顺序展示。
- WiseRec 和 MLOps 的 `history list` 均需先登录并选择业务。`--latest-flag` 仅接受 `true` 和 `all`，默认 `true` 仅查询最新实例，`all` 同时查询历史实例。该命令只查询并分页展示记录。
- `history detail` 查询指定执行记录。遇到 `jobType=dps-train` 时包含 `roleJobInfo` 角色列表及各角色的 `roleJobId`、`plogReady`。
- 日志下载失败时，前置校验阶段（如查询记录、角色或参数校验）仅在 stderr 报错且无 JSON 输出；单条下载阶段失败时，可结合 stderr 和 JSON 摘要中的 `stage`、`error` 定位问题。
- 下载日志 ZIP 时优先使用终端的 `HTTPS_PROXY`，其次使用 `ALL_PROXY`，并按 `NO_PROXY` 绕过代理。没有环境代理配置时，Windows 和 macOS 使用手动配置的系统 HTTPS 代理。仅使用 PAC 的环境可在当前终端设置 `HTTPS_PROXY` 后重试。已取到链接但下载失败时，按错误类别核对代理、DNS 或连接超时，不复述签名参数。
- `history list` 和 `instance list` 在 `--agent` 下保留原始状态代码与源单位时长（`runningTime`、`queueTime` 为分钟，`waitTime` 为秒，见顶层 `fields` 说明），时间已转为北京时间。
- `ml train start TASK_ID --agent` 返回 `jobId` 只表示请求已被接受，之后用 `history list` 确认状态。
- `cancel`、`delete`、`clone` 默认询问确认，授权后加 `--yes`。`cancel` 逐个取消全部执行实例，需看逐条结果和退出码，没有实例时退出 1。`clone` 成功后返回新任务 ID。
- `ml train config update TASK_ID --customize-config VALUE --agent` 不询问确认，直接修改任务；值按字符串原样传递，含双引号时注意 [session.md](session.md) 的引号说明，更新后导出配置核对；仅更新非代码业务参数，不通过参数传入改码程序。
- `config export` 的文件父目录须已存在；历史记录和执行实例的日志下载均使用 `--directory DIR` 指定已有目录，默认当前目录，不接受 `--file`，同名文件自动编号且不覆盖。
- 使用 `ml train instance logs download TASK_ID JOB_ID --select SELECTION --directory DIR --agent` 非交互下载。按用户指定的表格编号传值，编号以本次归档列表为准。多个编号用英文逗号分隔，PowerShell 中把列表用引号包住。用户明确要求全部时传 `all`。归档选择表显示编号、任务名称、`jobId`、`roleJobId`、节点名称、状态、失败原因、北京时间的起止时间和是否可以下载。
- 执行实例日志下载需要先归档。只有“归档成功”的记录可下载。“归档中”时稍后重试，“归档失败”时报告表中的失败原因。`--select '1,2,3'` 按指定顺序下载。`--select all` 按表格顺序串行下载归档成功的记录，跳过归档中或归档失败的记录。选中后获取 OBS 链接并保存 ZIP，单份下载失败后继续。`--agent` 返回下载摘要，须核对逐条结果与失败数量。回复中只提供保存路径和结果。

## 样本任务

先从对应任务管理列表获取任务 ID：

```powershell
ml sample-task list --name NAME --agent
ml sample-task list --source new --name NAME --agent
ml sample-task list --creator USER --updater USER --page 2 --page-size 20 --agent
ml sample-task list --type feature_preprocess_offline --status stopped --agent
ml sample-task list --source new --type FEATURE_ASSEMBLE --type FEATURE_SYNC --agent
```

- 默认 `--source legacy` 查询旧“任务管理”，`--source new` 查询“任务管理（新）”；两者默认第 1 页、每页 10 条。
- 旧版默认查询特征预处理实时、特征预处理离线、特征装配和标签装配四种类型，并非全部类型。重复 `--type` 替换默认范围；新版未指定类型时不限类型。旧版 `--type` 可选：`feature_preprocess_realtime`、`feature_preprocess_offline`、`feature_assemble`、`label_assemble`、`feature_monitor`、`new_feature_assemble`、`spark_jar`；新版 `--type` 可选：`FEATURE_ASSEMBLE`、`LABEL_ASSEMBLE`、`FEATURE_SYNC`、`FEATURE_IMPORT_OFFLINE`、`FEATURE_IMPORT_REALTIME`、`OFFLINE_FEATURE_SYNC`、`FEATURE_PREPROCESS_OFFLINE`、`FEATURE_QUALITY_MONITOR`、`OFFLINE_FEEDBACK`、`REAL_TIME_FEEDBACK`、`REALTIME_LABEL_CALC`、`SAMPLE_GENERATION_OFFLINE`、`SAMPLE_GENERATION_REALTIME`。
- `--status all|stopped|started` 仅旧版支持，默认全部；`--sort desc` 仅新版支持，新版默认降序。不要跨来源传筛选项。
- `--agent` 输出含 `source`、`pagination`、`pageIndex`、`pageSize`、`returnedCount`、`total`、`fields`、`items`。

新旧任务共用执行周期和执行记录命令，直接传任务 ID，无需 `--source`：

```powershell
ml sample-task period list TASK_ID --agent
ml sample-task period list TASK_ID --state COMPLETED --state FAILED --page 2 --page-size 20 --agent
ml sample-task period list TASK_ID --start-time '2026-10-01 00:00:00' --end-time '2026-10-21 23:59:59' --agent
ml sample-task execution list TASK_ID --agent
ml sample-task execution list TASK_ID --include-history --page 2 --page-size 20 --agent
```

- `period list` 默认第 1 页、每页 20 条。起止时间按北京时间输入 `YYYY-MM-DD HH:mm:ss`，可只指定一端，开始时间不得晚于结束时间。`--state` 可重复指定（未指定不限状态），可选：`INIT`、`CANCELED`、`QUEUE`、`APPLY_FOR_RESOURCE`、`WAIT_FOR_QUOTA_QUEUE`、`RUNNING`、`COMPLETED`、`FAILED`、`LACK_RESOURCE`、`TIMEOUT`。
- `execution list` 默认第 1 页、每页 10 条，不包含历史实例；`--include-history` 开启后包含历史实例。任务 ID 和记录中的 JOB ID 不互换。
- 两种执行查询在 `--agent` 下均返回 `taskId`、`pagination`、`pageIndex`、`pageSize`、`returnedCount`、`total`、`fields`、`items`。每次只查询指定页，不把第一页当成全部结果。

## 算法仓

算法仓查询、下载与克隆仅在 WiseRec 环境可用。

```powershell
ml algorithm list --name 'NAME,NAME' --agent
ml algorithm list --name NAME --agent
ml algorithm download ALGORITHM_ID --file 'D:\download\algo.zip' --agent
ml algorithm clone ALGORITHM_ID --name NEW_NAME --version VERSION --yes --agent
```

- 下载先获取签名链接再保存 ZIP；父目录必须已存在，不覆盖同名文件。不要把签名链接写入回复或日志。
- 算法仓 ZIP 下载使用与训练日志相同的代理设置。优先使用 `HTTPS_PROXY`，其次使用 `ALL_PROXY`，并按 `NO_PROXY` 绕过代理。没有环境代理配置时，Windows 和 macOS 读取手动配置的系统 HTTPS 代理。
- 克隆默认询问确认，授权后加 `--yes`；结果不明时先按新名称和版本查询，再决定是否重试。

## 结果核验

写请求超时或连接中断时，先查询目标任务、实例或资源的实际状态，再决定是否重试。分页字段和响应字段以实际返回为准，文档中的示例不代表完整响应。
