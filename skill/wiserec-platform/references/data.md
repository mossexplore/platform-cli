# 数据集、特征任务与特征集

以下查询与操作默认使用 `--agent` 获取紧凑精简 JSON（不要与 `-o json` 同传）；仅在需要完整原始响应（如被截断的超长数据集描述）时去掉 `--agent` 改用 `-o json`。

**高频最短链路**：
- **数据集查文件/上传**：`ml dataset list --name 'NAME,NAME' --agent`（跨租户按每条 `businessId` 区分）→ `ml dataset files list DATASET_ID --dir / --agent` / `ml dataset files upload DATASET_ID LOCAL_FILE --dir / --agent`（返回 `accepted` 后用 `files list` 核验）
- **特征任务查日志**：`ml feature-task list --name 'NAME,NAME' --agent` → `ml feature-task execution list TASK_ID --agent`（取 `jobId`）→ `ml feature-task execution logs search JOB_ID --agent`
- **质量监控装配**：`ml quality wide-featureset list --agent`（取 `setId`）→ `feature-assemble list --set-id SET_ID --agent`（取 `definitionId`）→ `feature-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --agent`

- 从特征任务定位上游数据时，先用 `ml feature-task detail TASK_ID --agent` 查关联信息。详情可能只给出名称或引用。缺少 ID 时，在当前环境支持的列表中按名称查找并核对，或请用户提供 ID。
- 质量监控宽表查询（`ml quality wide-featureset`）与特征集配置查询（`ml featureset wide`）为不同入口，ID 与筛选字段不混用。

## 数据集

```powershell
ml dataset list --name 'DATASET_NAME,DATASET_NAME' --agent
ml dataset list --name DATASET_NAME --agent
ml dataset list -A --name DATASET_NAME --agent
ml dataset detail DATASET_ID --agent
ml dataset files list DATASET_ID --dir / --agent
ml dataset files upload DATASET_ID 'D:\data\sample.csv' --dir / --agent
```

- 数据集内部路径与 Jupyter 路径无关：以 `/` 表示数据集根目录，用 `/` 分隔，不允许反斜杠及 `.`、`..` 路径段。
- `dataset files list --agent` 返回顶层 `currentDir`、`hasMore`、`fields` 与 `items`（含 `fullPath`）。`hasMore=true` 表示结果不完整，命令没有目录分页选项，不要自行构造参数。
- 上传是追加单个文件，不会覆盖，也没有 `--overwrite`。仅支持 `.txt`、`.csv`、`.zip`、`.tar`、`.gz`、`.json`，大小不超过 2,000,000,000 字节；文件名须以英文字母或数字开头，只含英文字母、数字、下划线、短横线和点。
- 上传默认网络超时 1800 秒，shell 工具 `timeout` 须大于该值。成功后重新 `files list` 核验；失败或超时不自动重传，先查远端是否已收到。

## 特征任务与执行日志

WiseRec 和 MLOps 均支持特征任务列表、详情、执行记录及日志搜索。列表查询使用当前选中的业务。

```powershell
ml feature-task list --name 'NAME,NAME' --agent
ml feature-task list --name NAME --create-user USER --page 1 --page-size 10 --agent
ml feature-task list --category train_fi --agent
ml feature-task detail TASK_ID --agent
ml feature-task execution list TASK_ID --page 1 --page-size 10 --agent
ml feature-task execution list TASK_ID --include-history --agent
ml feature-task execution logs search JOB_ID --agent
ml feature-task execution logs search JOB_ID --start-line 1 --end-line 2000 --keyword ERROR --keyword timeout --scope C --scope-lines 10 --agent
```

- 特征任务列表默认 `--category dpp-all`，第 1 页、每页 10 条；`--category` 可选：`dpp-all`、`feature_preprocess_realtime`、`train_fi`、`data_sync`、`data-preproc`、`feature_generate`、`feature_evaluation`、`feature_improve`、`work_flow`、`feature-push`、`train_spark`、`train_fi_sync_hdfs`、`train_fi_data_monitor`、`generate_samples`。该命令与 `ml sample-task list` 是不同的任务入口，不混用筛选参数。
- 从 `ml feature-task list --agent` 获取 `taskId`，再用 `ml feature-task detail TASK_ID --agent` 查询算法、数据集、特征集引用或参数。无需提供团队 ID。时间已转为北京时间；需要完整原始 `result` 时改用 `-o json`。
- 执行记录默认第 1 页、每页 10 条，不包含历史实例；使用 `--include-history` 包含历史实例。`--agent` 返回 `pagination`、`pageIndex`、`pageSize`、`returnedCount`、`total`、`fields`、`items`。
- 日志查询使用执行记录中的 `jobId`，不能传任务 ID。默认行范围为 1 到 2000；起止行均为正整数，结束行不得小于起始行。
- `--keyword` 可重复指定。`--scope A|B|C` 分别表示关键词后、前、前后；`--scope-lines` 为正整数范围行数。不需要的筛选项不传。
- 日志在 `--agent` 下返回紧凑 JSON `{"logs": [...]}`（正文在 `logs[0].log`）；不带 `--agent` 默认原样输出文本。日志可能包含凭据，只提取用户需要的内容。

## 特征集

```powershell
ml featureset wide list --name NAME --agent
ml featureset model list --name NAME --agent
ml featureset wide config SET_ID --agent
ml featureset model config SET_ID --agent
```

`config` 固定输出 JSON（加 `--agent` 为紧凑单行并完整保留嵌套结构、空集合和 null），不加 `-o`。宽表特征集与模型特征集的 ID 不互换。

### 特征集 CSV 导出

```powershell
ml featureset wide export SET_ID --lang zh_cn --file 'D:\data\wide.csv' --agent
ml featureset model export SET_ID --lang en_us --file 'D:\data\model.csv' --agent
```

`--lang` 支持 `zh_cn` 和 `en_us`，默认中文。`--file` 可省略；命令会生成保存路径，重名自动编号。`--agent` 输出紧凑导出结果 JSON；按返回的实际路径查找文件，不假定指定的文件名就是最终文件名。导出会写入本地文件。

普通和 gzip 压缩的 CSV 均可导出，保存时保留 BOM 和换行。接口返回 JSON 错误、登录页或空响应时，按错误提示核对权限、登录或服务端响应。

## 质量监控报告

```powershell
ml quality feature list --name FEATURE_NAME --table-name TABLE_NAME --agent
ml quality feature list --feature-value-type DISCRETE --indicator-type VECTOR --page 1 --page-size 100 --agent
ml quality wide-featureset list --name SET_NAME --page 1 --page-size 10 --agent
```

- 对应质量监控报告的“特征列表”和“宽表特征集”，查询当前环境已选业务。宽表查询与 `ml featureset wide list` 的入口和列不同。
- 默认第 1 页、每页 10 条；`--page` ≥ 1，`--page-size` 为 1～100，每次只取一页。名称、表名默认空字符串；两个类型筛选默认省略。
- 特征值类型与指标类型独立筛选，均接受连续/CONTINUOUS、离散/DISCRETE、有序/ORDINAL、分类/CATEGORICAL、序列/SEQUENCE、长序列/LONG_SEQUENCE、向量/VECTOR，英文忽略大小写。
- `--agent` 返回 `pagination`、`pageIndex`、`pageSize`、`returnedCount`、`total`、`fields`、`items`，保留原始数值和类型；分页优先采用响应值，缺失时采用请求值。不要从表格反向重建原始数据。

### 宽表特征集装配查询

```powershell
ml quality wide-featureset feature-assemble list --set-id SET_ID --agent
ml quality wide-featureset label-assemble list --set-id SET_ID --agent
ml quality wide-featureset feature-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --page 1 --page-size 10 --agent
ml quality wide-featureset label-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --page 2 --page-size 100 --agent
```

- 先用 `ml quality wide-featureset list --agent` 定位特征集，再查询对应装配的样本定义，最后使用该分组下的样本定义 ID 查询特征。不传 `--type`，由命令分组决定装配类型。
- 样本定义列表不分页，`--agent` 返回 `pagination: "unpaged"`、`returnedCount`、`featureSetId`、`fields`、`items`。若返回 ID 与请求 ID 不同，先核对，不擅自推断两者可互换；后续查询显式传入经确认的 `--set-id`。
- 装配特征列表默认第 1 页、每页 10 条，最大 100 条，每次只取一页。请求必须同时指定特征集 ID 和样本定义 ID，不混用特征 ID。`--agent` 输出保留原始数值与周期编码。
