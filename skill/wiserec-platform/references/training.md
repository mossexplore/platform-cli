# 训练任务、样本任务、算法仓、离线实验与训练看板

以下查询与操作默认使用 `--agent`（不与 `-o json` 同传），无需预先执行 `--help`。

**高频最短链路**：
- **查任务并下日志**：`ml train list --name NAME --exact --agent` → `ml train logs download TASK_ID --directory DIR --agent`。用户已给作业 ID 时同时传入。
- **训练看板**：`project list` → `project namespace list PROJECT_ID` → `project experiment list PROJECT_ID NAMESPACE_ID` → `experiment metrics EXPERIMENT_ID`

## 训练任务

- **概念区分**：**执行实例（`train instance`）**代表当前**正在运行/排队中**的作业；**执行记录（`train history`）**代表**历史已执行过**（完成/失败/取消/超时等）的作业。查运行中状态/日志用 `instance`，查历史结果/日志用 `history`；用户笼统问“当前状态”时先查 `instance list`，无运行中实例再查 `history list`。
- WiseRec / MLOps 均支持；MLOps `train list --page-size` 最大 200，`instance list` / `history list` 为 1–200（默认第 1 页 10 条）。

```powershell
ml train list --name NAME --exact --agent
ml train detail TASK_ID --agent
ml train instance list TASK_ID --page 1 --page-size 20 --agent
ml train history list TASK_ID --latest-flag all --page 1 --page-size 20 --agent
ml train logs download TASK_ID JOB_ID --directory 'D:\logs' --agent
ml train logs download TASK_ID JOB_ID --role-job-id ROLE_JOB_ID --type plog --directory 'D:\logs' --agent
```

### 训练日志统一下载

- WiseRec 和 MLOps 均需先登录并选择业务。保存目录须已存在。省略作业 ID 时优先选最新执行实例，其次选最新历史记录，选定后锁定作业。多角色时按目标传可重复的 `--role-job-id` 或 `--all`。
- 历史普通日志默认每 30 秒只读重查，最多等待 120 秒，可调整 `--poll-interval` 和 `--wait-timeout`。单轮检查用 `--no-wait`。工具超时需覆盖等待、查询和文件传输。历史 plog 直接检查并取址。
- 执行实例首次请求作业归档，`archiving` 表示仍在处理中，此时向用户报告状态。归档失败时报告作业 ID 和失败原因，询问是否重新下载**该作业的全部日志**。仅在用户针对整个作业明确同意后执行一次 `ml train logs download TASK_ID JOB_ID --retry --directory DIR --agent`，由服务端决定是否重新归档。禁止自动重跑、逐角色重试或在重试失败后沿用上次确认。
- `succeeded` 表示已保存全部文件；`not_ready` 表示单轮检查后历史日志暂不可用，`wait_timeout` 表示等待到期。遇到 `partial` 或 `failed` 时检查逐项结果及错误阶段，报告已保存路径，不展示签名链接。
- 旧入口仍支持原参数。脚本显式调用 `instance logs download` 时使用 `--select`；旧 `history logs download` 的普通日志未就绪时会提交手动归档。新流程使用统一入口。

### 写操作与配置
- `ml train start TASK_ID --agent` 返回 `jobId` 仅表示已受理，之后用 `history list` 确认状态。
- `cancel` / `delete` / `clone` 经用户授权后加 `--yes`；`cancel` 无运行实例时退出 `1`，有部分失败须核对逐项结果。
- `ml train config update TASK_ID --customize-config VALUE --agent` **无内置确认**直接生效，按原样传字符串（含双引号见 [session.md](session.md)），更新后用 `config export`（父目录须已存在）核对；禁止传入改码程序。

## 样本任务

```powershell
ml sample-task list --source legacy --name NAME --type feature_preprocess_offline --status stopped --agent
ml sample-task list --source new --name NAME --type FEATURE_ASSEMBLE --page 1 --page-size 20 --agent
ml sample-task period list TASK_ID --start-time '2026-10-01 00:00:00' --end-time '2026-10-21 23:59:59' --state COMPLETED --state FAILED --agent
ml sample-task execution list TASK_ID --include-history --page 1 --page-size 20 --agent
```

- **来源差异**：默认 `--source legacy`（旧版默认仅查 `feature_preprocess_realtime`/`feature_preprocess_offline`/`feature_assemble`/`label_assemble` 4 类，传 `--type` 会替换默认范围）；`--source new` 不限类型。`--status all|stopped|started` 仅旧版支持；`--sort desc` 仅新版支持，勿跨来源混传。
- **`--type` 枚举**（可重复）：
  - 旧版：`feature_preprocess_realtime`、`feature_preprocess_offline`、`feature_assemble`、`label_assemble`、`feature_monitor`、`new_feature_assemble`、`spark_jar`
  - 新版：`FEATURE_ASSEMBLE`、`LABEL_ASSEMBLE`、`FEATURE_SYNC`、`FEATURE_IMPORT_OFFLINE`、`FEATURE_IMPORT_REALTIME`、`OFFLINE_FEATURE_SYNC`、`FEATURE_PREPROCESS_OFFLINE`、`FEATURE_QUALITY_MONITOR`、`OFFLINE_FEEDBACK`、`REAL_TIME_FEEDBACK`、`REALTIME_LABEL_CALC`、`SAMPLE_GENERATION_OFFLINE`、`SAMPLE_GENERATION_REALTIME`
- **周期与执行记录**（新旧共用，无需 `--source`）：`period list` 默认每页 20 条，起止时间为北京时间，`--state` 可重复，可选：`INIT`、`CANCELED`、`QUEUE`、`APPLY_FOR_RESOURCE`、`WAIT_FOR_QUOTA_QUEUE`、`RUNNING`、`COMPLETED`、`FAILED`、`LACK_RESOURCE`、`TIMEOUT`；`execution list` 默认每页 10 条，`--include-history` 包含历史实例。

## 算法仓

仅 WiseRec 支持。

```powershell
ml algorithm list --name NAME --exact --agent
ml algorithm download ALGORITHM_ID --file 'D:\download\algo.zip' --agent
ml algorithm clone ALGORITHM_ID --name NEW_NAME --version VERSION --yes --agent
```

- `download` 父目录须已存在且不覆盖同名文件，不泄露签名链接；`clone` 授权后加 `--yes`。

## 离线实验

```powershell
ml offline experiment list --name NAME --agent
ml offline experiment trial list PROJECT_ID --agent
ml offline experiment clone PROJECT_ID --name NEW_NAME --dry-run --agent
ml offline experiment clone PROJECT_ID --name NEW_NAME --yes --agent
```

克隆先 `--dry-run` 核对，用户授权后再 `--yes` 提交。

## 训练看板（MTP Swanboard）

```powershell
ml mtp swanboard project list --agent
ml mtp swanboard project namespace list PROJECT_ID --agent
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID --agent
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy --agent
```

- 项目 ID、空间 ID、实验 ID 不互换；`--team-id` 仅筛选不切业务。
- `metrics` 返回统计值而非完整时间序列（`--tag` 可重复）；`inspect` 会发多次请求且特性仅含首页，只需单项时直接调子命令。
