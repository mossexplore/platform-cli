# 服务与服务日志

## 定位服务与主机

```powershell
ml service list --name SERVICE_NAME -o json
ml service host list SERVICE_ID -o json
ml service deployment list SERVICE_ID -o json
```

- 主机视图和部署视图只返回第一页 10 条，不能当作完整集合。主机视图中的 `nodeName` 是 Pod 名称。
- 部署视图首列为 `blockId`。

## 读取日志

在 shell 工具中必须加 `--no-input`，并明确传入 `--type`：

```powershell
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --list --no-input
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME -k error -n 200 --no-input
```

- 日志命令不支持 `-o json`：`--list` 输出文件表格，正文为原始文本，提示信息在 stderr。
- `--pod` 与 `--cluster-name` 必须成对提供，CLI 不验证 Pod 是否属于该服务。不指定 Pod 时，只有唯一主机才会自动选择；文件同理。有多个候选时补充参数或请用户选择，不取第一项。
- `--list` 不能与 `--file`、关键词、行数等正文检索选项同时使用。`-k` 可重复；`-n` 默认 200 行。高级选项 `--search-order`、`--grep-scope`、`--grep-line` 见 `--help`。
- 日志不会持续刷新。空文件列表不会检索正文；指定的主机或文件不存在会失败。

## 日志类别

日志类别没有默认值，取决于主机的 infraType：

| 主机 infraType | 可用 `--type` |
| --- | --- |
| `infer-python` | run、interface、metrics、engine、ascend、mslite、alarm |
| `rtc` | rtc、run、interface、dcs、metrics、gc、interface_manager、interface_extend、engine、monitor、catalina、dmq |

`rtc_python` 是 CLI 内部使用的请求类型，不要传给 `--type`。主机类型未知时 CLI 会报错，不要绕过。

日志内容可能包含敏感信息，只摘录任务需要的部分。
