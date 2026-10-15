# 数据集与特征集

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

## 特征集

```powershell
ml featureset wide list --name NAME -o json
ml featureset model list --name NAME -o json
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

`config` 固定输出 JSON，不加 `-o`。宽表特征集与模型特征集的 ID 不互换。
