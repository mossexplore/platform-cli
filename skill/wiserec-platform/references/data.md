# 数据集、特征任务、特征集与质量监控

以下查询与操作默认使用 `--agent`（不与 `-o json` 同传）；仅在需要完整原始响应（如被截断的超长数据集描述）时改用 `-o json`。

**高频最短链路**：
- **数据集查文件/上传**：`ml dataset list --name 'NAME,NAME' --agent`（跨租户按每条 `businessId` 区分）→ `ml dataset files list DATASET_ID --dir / --agent` / `ml dataset files upload DATASET_ID LOCAL_FILE --dir / --agent`（返回 `accepted` 后用 `files list` 核验）
- **特征任务查日志**：`ml feature-task list --name 'NAME,NAME' --agent` → `ml feature-task execution list TASK_ID --agent`（取 `jobId`）→ `ml feature-task execution logs search JOB_ID --agent`
- **质量监控装配**：`ml quality wide-featureset list --agent`（取 `setId`）→ `feature-assemble list --set-id SET_ID --agent`（取 `definitionId`）→ `feature-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --agent`

## 数据集

```powershell
ml dataset list --name 'DATASET_NAME,DATASET_NAME' --page 1 --page-size 10 --agent
ml dataset detail DATASET_ID --agent
ml dataset files list DATASET_ID --dir / --agent
ml dataset files upload DATASET_ID 'D:\data\sample.csv' --dir / --agent
```

- **路径规则**：以 `/` 表示数据集根目录并用 `/` 分隔（与 Jupyter 路径无关），禁止 `\`、`.`、`..`。
- **目录与上传**：`files list --agent` 返回顶层 `currentDir`、`hasMore`、`fields`、`items`（含 `fullPath`）；`hasMore=true` 表示结果不完整且无目录分页参数。`files upload` 仅追加单文件（无 `--overwrite`），仅支持 `.txt`/`.csv`/`.zip`/`.tar`/`.gz`/`.json`（≤ 2,000,000,000 字节），文件名以字母/数字开头且仅含字母、数字、`_`、`-`、`.`；**网络超时默认 1800 秒**，工具超时须大于该值，失败/超时先 `files list` 核验再决定是否重试。

## 特征任务与执行日志

WiseRec / MLOps 均支持。

```powershell
ml feature-task list --name 'NAME,NAME' --category dpp-all --page 1 --page-size 10 --agent
ml feature-task detail TASK_ID --agent
ml feature-task execution list TASK_ID --include-history --page 1 --page-size 10 --agent
ml feature-task execution logs search JOB_ID --start-line 1 --end-line 2000 --keyword ERROR --scope C --scope-lines 10 --agent
```

- **`--category` 枚举**（默认 `dpp-all`）：`dpp-all`、`feature_preprocess_realtime`、`train_fi`、`data_sync`、`data-preproc`、`feature_generate`、`feature_evaluation`、`feature_improve`、`work_flow`、`feature-push`、`train_spark`、`train_fi_sync_hdfs`、`train_fi_data_monitor`、`generate_samples`（与 `sample-task list` 不同入口，勿混用参数）。
- 定位上游数据先查 `feature-task detail TASK_ID --agent`（详情可能仅含名称/引用，缺少 ID 时按名称在对应列表核对）。
- **日志搜索**：入参为执行记录的 `jobId`（非 `taskId`），默认行 1–2000；`--keyword` 可重复，`--scope A|B|C` 分别表示后/前/前后。`--agent` 返回 `{"logs":[...]}`（正文在 `logs[0].log`），日志可能含凭据，仅摘录所需内容。

## 特征集

```powershell
ml featureset wide list --name NAME --agent
ml featureset model list --name NAME --agent
ml featureset wide config SET_ID --agent
ml featureset wide export SET_ID --lang zh_cn --file 'D:\data\wide.csv' --agent
```

- 宽表（`wide`）与模型（`model`）特征集 ID 不互换，且与 `ml quality wide-featureset` 为不同入口。
- `config` 固定输出 JSON（`--agent` 为紧凑单行并完整保留嵌套、空集合与 null，不加 `-o`）。
- `export` 支持 `--lang zh_cn|en_us`（默认 `zh_cn`），`--file` 可省且重名自动编号，按返回的实际路径读取导出文件。

## 质量监控报告

```powershell
ml quality feature list --name NAME --table-name TBL --feature-value-type DISCRETE --indicator-type VECTOR --page 1 --page-size 100 --agent
ml quality wide-featureset list --name SET_NAME --page 1 --page-size 10 --agent
ml quality wide-featureset feature-assemble list --set-id SET_ID --agent
ml quality wide-featureset feature-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --page 1 --page-size 10 --agent
```

- 分页列表默认每页 10 条、最大 100 条；`--feature-value-type` 与 `--indicator-type` 独立筛选，均接受 `连续/CONTINUOUS`、`离散/DISCRETE`、`有序/ORDINAL`、`分类/CATEGORICAL`、`序列/SEQUENCE`、`长序列/LONG_SEQUENCE`、`向量/VECTOR`（忽略大小写）。
- 装配查询分 `feature-assemble` 与 `label-assemble` 两个分组（不传 `--type`）。样本定义列表不分页（返回 `featureSetId`，若与请求不同先核对，后续显式传经确认的 `--set-id`）；装配特征列表必同时传 `--set-id` 与 `--definition-id`（不混用特征 ID）。
