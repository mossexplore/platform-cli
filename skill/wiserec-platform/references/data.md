# 数据集、特征任务与特征集

## 数据集

```powershell
ml dataset list --name DATASET_NAME -o json
ml dataset detail DATASET_ID -o json
ml dataset files list DATASET_ID --dir / -o json
ml dataset files upload DATASET_ID 'D:\data\sample.csv' --dir / -o json
```

- 数据集内部路径与 Jupyter 路径无关：以 `/` 表示数据集根目录，用 `/` 分隔，不允许反斜杠及 `.`、`..` 路径段。
- 目录 JSON 外层为 `currentDir` 与 `response`，条目在 `response.result.fileInfos.files`。`hasMore=true` 表示结果不完整，命令没有目录分页选项，不要自行构造参数。
- 上传是追加单个文件，不会覆盖，也没有 `--overwrite`。仅支持 `.txt`、`.csv`、`.zip`、`.tar`、`.gz`、`.json`，大小不超过 2,000,000,000 字节；文件名须以英文字母或数字开头，只含英文字母、数字、下划线、短横线和点。
- 上传默认网络超时 1800 秒，shell 工具 `timeout` 须大于该值。成功后重新 `files list` 核验；失败或超时不自动重传，先查远端是否已收到。

## 特征任务与执行日志

```powershell
ml feature-task list --name NAME --create-user USER --page 1 --page-size 10 -o json
ml feature-task list --category train_fi -o json
ml feature-task execution list TASK_ID --page 1 --page-size 10 -o json
ml feature-task execution list TASK_ID --include-history -o json
ml feature-task execution logs search JOB_ID
ml feature-task execution logs search JOB_ID --start-line 1 --end-line 2000 --keyword ERROR --keyword timeout --scope C --scope-lines 10 -o json
```

- 特征任务列表默认 `--category dpp-all`，第 1 页、每页 10 条；类型枚举见 `ml feature-task list --help`。该命令与 `ml sample-task list` 是不同的任务入口，不混用筛选参数。
- 执行记录默认第 1 页、每页 10 条，不包含历史实例；使用 `--include-history` 包含历史实例。列表 JSON 为 `items`、`count`、`pageIndex`、`pageSize`。
- 日志查询使用执行记录中的 `jobId`，不能传任务 ID。默认行范围为 1 到 2000；起止行均为正整数，结束行不得小于起始行。
- `--keyword` 可重复指定。`--scope A|B|C` 分别表示关键词后、前、前后；`--scope-lines` 为正整数范围行数。不需要的筛选项不传。
- 日志默认原样输出文本，保留空格和换行；`-o json` 输出完整响应，日志正文位于 `result.logs[0].log`。日志可能包含凭据，只提取用户需要的内容。

## 特征集

```powershell
ml featureset wide list --name NAME -o json
ml featureset model list --name NAME -o json
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

`config` 固定输出 JSON，不加 `-o`。宽表特征集与模型特征集的 ID 不互换。


### 特征集 CSV 导出

```powershell
ml featureset wide export SET_ID --lang zh_cn --file 'D:\data\wide.csv' -o json
ml featureset model export SET_ID --lang en_us --file 'D:\data\model.csv' -o json
```

`--lang` 支持 `zh_cn` 和 `en_us`，默认中文。`--file` 可省略；命令会生成保存路径，重名自动编号。默认输出文本摘要，`-o json` 输出导出结果；按返回的实际路径查找文件，不假定指定的文件名就是最终文件名。导出会写入本地文件。
