# 训练任务、样本任务、离线实验、算法仓与训练看板

以下命令的列表和查询均支持 `-o json`，具体筛选和分页参数查 `--help`。

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
ml train detail TASK_ID -o json
ml train instance list TASK_ID -o json
ml train history list TASK_ID -o json
ml train history logs download TASK_ID JOB_ID --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select 2 --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select '1,3' --directory 'D:\logs' -o json
ml train instance logs download TASK_ID JOB_ID --select all --directory 'D:\logs' -o json
```

- WiseRec 和 MLOps 均支持训练任务列表、执行实例列表、执行记录列表及两种日志下载。先用 `ml tree` 查看当前环境支持的其他训练命令。
- `detail` 仅适用于 WiseRec。使用 `train list` 中的任务 ID，结果含基本信息、首个样本的数据集、输出引用及首个样本的配置引用、算法参数及自定义参数。
- `instance list` 和 `history list` 只返回第一页 10 条。按日志来源从对应列表取得 `jobId`。执行记录默认下载普通日志，加 `--type plog` 下载 plog。
- `history list -o table` 的最后两列是“排队时长”和“配额等待时间”。`queueTime` 原值为分钟，例如 `157` 显示为 `2h37min`。`waitTime` 原值为秒，例如 `3631` 显示为 `1h0min31s`。零值分别显示为 `0min` 和 `0s`，缺失值显示 `-`。`-o json` 保留原始字段和值。
- `instance list -o table` 的最后一列也是“配额等待时间”，沿用相同的 `waitTime` 换算规则。
- `ml train start TASK_ID` 返回 `jobId` 只表示请求已被接受，之后用 `history list` 确认状态。
- `cancel`、`delete`、`clone` 默认询问确认，授权后加 `--yes`。`cancel` 逐个取消全部执行实例，需看逐条结果和退出码，没有实例时退出 1。`clone` 成功后可能返回新任务 ID。
- `ml train config update TASK_ID --customize-config VALUE` 不询问确认，直接修改任务；值按字符串原样传递，含双引号时注意 [session.md](session.md) 的引号说明，更新后导出配置核对。
- `config export` 的文件父目录须已存在；历史记录和执行实例的日志下载均使用 `--directory DIR` 指定已有目录，默认当前目录，不接受 `--file`，同名文件自动编号且不覆盖。
- 使用 `ml train instance logs download TASK_ID JOB_ID --select SELECTION --directory DIR` 非交互下载。按用户指定的表格编号传值，编号以本次归档列表为准。多个编号用英文逗号分隔，PowerShell 中把列表用引号包住。用户明确要求全部时传 `all`。省略 `--select` 时在终端交互选择。命令先请求归档，提示归档中时稍后重跑同一命令。已有记录时，每条归档在表格中占一行，显示编号、任务名称、`jobId`、`roleJobId`、节点、状态及北京时间的起止时间。
- 输入 `1,2,3` 按输入顺序下载，使用中文逗号时按提示重输。输入 `all` 按表格顺序串行下载全部归档成功的记录，跳过仍在归档的记录。输入 `q` 取消。选中后显示 OBS 链接并保存 ZIP，单份失败后继续其余下载。加 `-o json` 可获取下载摘要。

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
- 周期的表格输出为无表头四列网格，按返回顺序从左往右填充，编号每页从 1 开始，只补齐最后一行；20 条为五行，7 条为两行，空列表不绘制网格。
- `execution list` 默认第 1 页、每页 10 条，不包含历史实例；`--include-history` 开启后包含历史实例。任务 ID 和记录中的 JOB ID 不互换。
- 执行记录表格展示 JOB ID、算法名称、中文状态、文件大小、周期时间、执行时长、最新实例及检查、开始、结束时间。大小按 1024 进制，执行时长按分钟转换，时间戳按北京时间展示。
- 两种执行查询的 JSON 均为 `taskId`、`page`、`pageSize`、`total`、`items`，保留原始状态、时间和额外字段，不加入网格编号。每次只查询指定页，不把第一页当成全部结果。

## 算法仓

```powershell
ml algorithm list --name NAME -o json
ml algorithm download ALGORITHM_ID --file 'D:\download\algo.zip'
ml algorithm clone ALGORITHM_ID --name NEW_NAME --version VERSION --yes
```

- 下载先获取签名链接再保存 ZIP；父目录必须已存在，不覆盖同名文件。不要把签名链接写入回复或日志。
- 克隆默认询问确认，授权后加 `--yes`；结果不明时先按新名称和版本查询，再决定是否重试。

## 结果核验

写请求超时或连接中断时，先查询目标任务、实例或资源的实际状态，再决定是否重试。分页字段和响应字段以实际返回为准，文档中的示例不代表完整响应。
