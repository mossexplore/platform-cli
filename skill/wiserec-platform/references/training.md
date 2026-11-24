# 训练任务、样本任务、离线实验、算法仓与训练看板

以下命令的列表和查询均支持 `-o json`，具体筛选和分页参数查 `--help`。

## 常见操作流：训练任务排障与取日志

1. `ml train list --name NAME -o json` 定位 `taskId`（`detail` 可查数据集、配置及参数引用）。
2. `ml train instance list TASK_ID -o json` 查当前运行或排队的实例。用 `ml train history list TASK_ID -o json` 获取可供详情和下载命令查找的 `jobId`。加 `--latest-flag all` 可查看历史实例的记录，仅在 `all` 结果中出现的记录会超出详情和下载命令的查找范围。
3. 下载执行记录日志时，禁止调用 `ml train history detail`。非交互下载优先复用已知的作业和角色 ID。如果需要定位角色，在 `history list -o json` 的 `items` 中按 `jobId` 找到目标记录。`jobType=dps-train` 时，从该记录的 `roleJobInfo` 按用户指定的角色选择 `roleJobId`，下载时传 `--role-job-id`。普通训练直接使用 `TASK_ID` 和 `JOB_ID`。
4. 运行 `ml train history logs download TASK_ID JOB_ID [--type log|plog] [--role-job-id ROLE_JOB_ID] --directory DIR -o json`。普通训练的 `status` 或分布式训练对应角色的 `items[].status` 为 `not_ready` 时，表示归档请求已提交，稍后重跑同一命令。
5. 取执行实例归档日志：运行 `ml train instance logs download TASK_ID JOB_ID --select SELECTION --directory DIR -o json`（非交互必须传 `--select` 编号或 `all`）。

这两种下载都可能触发平台归档。执行前核对作业 ID，并确认用户授权包含归档。

## 训练看板（MTP Swanboard）

按“项目 → 项目空间 → 实验 → 实验数据”逐级定位：

```powershell
ml mtp swanboard project list -o json
ml mtp swanboard project namespace list PROJECT_ID -o json
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID -o json
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy -o json
```

- 项目 ID、空间 ID 和实验 ID 不互换。`--team-id` 只筛选结果，不切换当前业务。
- `metrics` 返回统计值，不是完整时间序列；`--tag` 可重复。
- `inspect` 会发起多次请求，其中特性只含第一页；只需单项信息时直接用对应子命令。

## 离线实验

```powershell
ml offline experiment list --name NAME -o json
ml offline experiment trial list PROJECT_ID -o json
ml offline experiment clone PROJECT_ID --name NEW_NAME --dry-run -o json
ml offline experiment clone PROJECT_ID --name NEW_NAME --yes -o json
```

克隆前先用 `--dry-run` 核对源实验和新名称；用户授权后再加 `--yes` 提交。结果不明时先按新名称查询，不重复提交。

## 训练任务

```powershell
ml train list --name NAME -o json
ml train list -A --name NAME
ml train detail TASK_ID -o json
ml train instance list TASK_ID --page 2 --page-size 20 -o json
ml train history list TASK_ID --page 2 --page-size 20 -o json
ml train history list TASK_ID --latest-flag all -o json
ml train history logs download TASK_ID JOB_ID --directory 'D:\logs' -o json
ml train history logs download TASK_ID JOB_ID --role-job-id ROLE_JOB_ID --directory 'D:\logs' -o json
ml train history logs download TASK_ID JOB_ID --type plog --role-job-id ROLE_JOB_ID --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select 2 --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select '1,3' --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select all --directory 'D:\logs' -o json
```

- WiseRec 和 MLOps 均支持训练任务查询、启动、取消、软删除、克隆、配置管理、执行实例及执行记录查询和日志下载。MLOps 的 `train list --page-size` 最大为 200。
- `detail` 使用 `train list` 中的任务 ID，结果含基本信息、首个样本的数据集、输出引用及首个样本的配置引用、算法参数及自定义参数。
- `instance list` 和 `history list` 默认返回第一页 10 条，支持 `--page` 和 `--page-size`（每页 1 至 200 条），按接口返回顺序展示。按日志来源从对应列表取得 `jobId`。执行记录默认下载普通日志，加 `--type plog` 下载 plog。
- WiseRec 和 MLOps 的 `history list` 均需先登录并选择业务。`--latest-flag` 仅接受 `true` 和 `all`，默认 `true` 仅查询最新实例，`all` 同时查询历史实例。该命令只查询并分页展示记录。
- `history detail` 和 `history logs download` 均在最新实例的执行记录中自动翻页匹配 `JOB_ID`。`history detail` 遇到 `jobType=dps-train` 时展示角色列表，首列为完整角色作业 ID，JSON 保留角色及额外字段。分布式训练使用 `-o json` 或非交互下载时须以 `--role-job-id` 指定角色。多个目标角色按用户指定范围逐个调用。普通训练不接受此参数。
- `history logs download` 自行查询执行记录。分布式训练直接读取该记录的 `roleJobInfo`，按 `--role-job-id` 匹配并校验角色。分布式记录的 `roleJobInfo` 为 `null` 或空数组时，命令立即退出，提示“该job无分布式角色，无日志可下载”。交互终端使用表格输出时，省略 `--role-job-id` 会显示角色选择表，依次为编号、roleJobId、名称、算法名称、状态、节点数、CPU、GPU、内存、执行节点和开始时间。开始时间按北京时间显示，可按编号选择角色。下载普通日志时，先检查日志状态，就绪后获取并校验下载地址，再保存文件。检查发现日志未就绪，或获取下载地址时返回 `failedUploadSwitch=false`，才按作业提交手动归档。提交成功后提示“手动归档中，请稍后再次下载日志！”，退出码为 `1`。普通训练的 JSON 顶层返回 `status=not_ready`，分布式训练顶层返回 `status=failed`，触发归档的条目显示 `items[].status=not_ready`。稍后重试时会重新检查日志状态。同次命令内同一作业最多提交一次归档，随后继续处理其余选中角色。
- 下载 plog 时，CLI 检查 `sysParam` JSON 字符串中的 `plogUploadSuccess`，其值须为字符串 `"1"`。普通训练检查执行记录自身，分布式训练检查角色。校验通过后直接获取 plog 链接并下载，跳过普通日志检查和手动归档。执行记录或所选角色无 plog 时，提示“该记录没有 plog 日志”。分布式 plog 文件命名为 `<roleJobId>_plog.zip`。
- 历史日志下载按实际执行顺序显示进度，进度写入 stderr。执行实例日志也显示查询、归档、选取及下载步骤，并在交互终端显示接收字节数。逐条失败的 JSON 摘要含 `stage` 和带阶段名称的 `error`，可据此定位日志检查、地址或传输问题。
- 下载日志 ZIP 时优先使用终端的 `HTTPS_PROXY`，其次使用 `ALL_PROXY`，并按 `NO_PROXY` 绕过代理。没有环境代理配置时，Windows 和 macOS 使用手动配置的系统 HTTPS 代理。仅使用 PAC 的环境可在当前终端设置 `HTTPS_PROXY` 后重试。已取到链接但下载失败时，按错误类别核对代理、DNS 或连接超时，不复述签名参数。
- `history list` 和 `instance list` 的 `-o json` 保留原始状态与时长字段（`runningTime`、`queueTime` 为分钟，`waitTime` 为秒）；表格模式会自动换算为中文状态和可读时长。
- `ml train start TASK_ID` 返回 `jobId` 只表示请求已被接受，之后用 `history list` 确认状态。
- `cancel`、`delete`、`clone` 默认询问确认，授权后加 `--yes`。`cancel` 逐个取消全部执行实例，需看逐条结果和退出码，没有实例时退出 1。`clone` 成功后可能返回新任务 ID。
- `ml train config update TASK_ID --customize-config VALUE` 不询问确认，直接修改任务；值按字符串原样传递，含双引号时注意 [session.md](session.md) 的引号说明，更新后导出配置核对；仅更新非代码业务参数，不通过参数传入改码程序。
- `config export` 的文件父目录须已存在；历史记录和执行实例的日志下载均使用 `--directory DIR` 指定已有目录，默认当前目录，不接受 `--file`，同名文件自动编号且不覆盖。
- 使用 `ml train instance logs download TASK_ID JOB_ID --select SELECTION --directory DIR` 非交互下载。按用户指定的表格编号传值，编号以本次归档列表为准。多个编号用英文逗号分隔，PowerShell 中把列表用引号包住。用户明确要求全部时传 `all`。归档选择表显示编号、任务名称、`jobId`、`roleJobId`、节点名称、状态、失败原因、北京时间的起止时间和是否可以下载。
- 执行实例日志下载需要先归档。只有“归档成功”的记录可下载。“归档中”时稍后重试，“归档失败”时报告表中的失败原因。`--select '1,2,3'` 按指定顺序下载。`--select all` 按表格顺序串行下载归档成功的记录，跳过归档中或归档失败的记录。选中后获取 OBS 链接并保存 ZIP，单份下载失败后继续。`-o json` 返回下载摘要，须核对逐条结果与失败数量。回复中只提供保存路径和结果。

## 样本任务

先从对应任务管理列表获取任务 ID：

```powershell
ml sample-task list --name NAME -o json
ml sample-task list --source new --name NAME -o json
ml sample-task list --creator USER --updater USER --page 2 --page-size 20 -o json
ml sample-task list --type feature_preprocess_offline --status stopped -o json
ml sample-task list --source new --type FEATURE_ASSEMBLE --type FEATURE_SYNC -o json
```

- 默认 `--source legacy` 查询旧“任务管理”，`--source new` 查询“任务管理（新）”；两者默认第 1 页、每页 10 条。
- 旧版默认查询特征预处理实时、特征预处理离线、特征装配和标签装配四种类型，并非全部类型。重复 `--type` 替换默认范围；新版未指定类型时不限类型。两套类型枚举不同，见 `ml sample-task list --help`。
- `--status all|stopped|started` 仅旧版支持，默认全部；`--sort desc` 仅新版支持，新版默认降序。不要跨来源传筛选项。
- JSON 为 `source`、`page`、`pageSize`、`total`、`items`，记录保留服务端原字段。

新旧任务共用执行周期和执行记录命令，直接传任务 ID，无需 `--source`：

```powershell
ml sample-task period list TASK_ID -o json
ml sample-task period list TASK_ID --state COMPLETED --state FAILED --page 2 --page-size 20 -o json
ml sample-task period list TASK_ID --start-time '2026-10-01 00:00:00' --end-time '2026-10-21 23:59:59'
ml sample-task execution list TASK_ID -o json
ml sample-task execution list TASK_ID --include-history --page 2 --page-size 20 -o json
```

- `period list` 默认第 1 页、每页 20 条。起止时间按北京时间输入 `YYYY-MM-DD HH:mm:ss`，可只指定一端，开始时间不得晚于结束时间。`--state` 可重复指定，未指定不限状态；状态枚举见命令帮助。
- 周期表格采用无表头四列网格，每格显示页内编号、周期和中文状态。按返回顺序从左往右填充，编号每页从 1 开始，末行未填满的单元格留空。空列表提示「暂无执行周期」。
- `execution list` 默认第 1 页、每页 10 条，不包含历史实例；`--include-history` 开启后包含历史实例。任务 ID 和记录中的 JOB ID 不互换。
- 执行记录表格展示 JOB ID、算法名称、中文状态、文件大小、周期时间、执行时长、最新实例及检查、开始、结束时间。大小按 1024 进制，执行时长按分钟转换，时间戳按北京时间展示。
- 两种执行查询的 JSON 均为 `taskId`、`page`、`pageSize`、`total`、`items`，保留原始状态、时间和额外字段，不加入网格编号。每次只查询指定页，不把第一页当成全部结果。

## 算法仓

算法仓查询、下载与克隆仅在 WiseRec 环境可用。

```powershell
ml algorithm list --name NAME -o json
ml algorithm download ALGORITHM_ID --file 'D:\download\algo.zip'
ml algorithm clone ALGORITHM_ID --name NEW_NAME --version VERSION --yes
```

- 下载先获取签名链接再保存 ZIP；父目录必须已存在，不覆盖同名文件。不要把签名链接写入回复或日志。
- 算法仓 ZIP 下载使用与训练日志相同的代理设置。优先使用 `HTTPS_PROXY`，其次使用 `ALL_PROXY`，并按 `NO_PROXY` 绕过代理。没有环境代理配置时，Windows 和 macOS 读取手动配置的系统 HTTPS 代理。
- 克隆默认询问确认，授权后加 `--yes`；结果不明时先按新名称和版本查询，再决定是否重试。

## 结果核验

写请求超时或连接中断时，先查询目标任务、实例或资源的实际状态，再决定是否重试。分页字段和响应字段以实际返回为准，文档中的示例不代表完整响应。
