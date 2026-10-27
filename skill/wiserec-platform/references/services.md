# 服务与服务日志

## 定位服务与主机

```powershell
ml service list --name SERVICE_NAME -o json
ml service host list SERVICE_ID -o json
ml service host list SERVICE_ID --pod-ip POD_IP -o json
ml service deployment list SERVICE_ID -o json
```

- 主机视图和部署视图只返回第一页 10 条，不能当作完整集合。主机视图中的 `nodeName` 是 Pod 名称。
- 主机视图不展示主机ID列；podIP 按 `nodeHost` 原值完整显示，优先单行保留 IP 和端口，其他长字段可换行。JSON 输出继续保留 `nodeId`。
- `host list --pod-ip IP` 按 Pod IP 筛选，传入值用于接口的 `hostIp`，无需端口；不传时不按 IP 筛选，空值会报错。主机测试也按所传 `--pod-ip` 查询主机视图。
- 部署视图首列为 `blockId`。

## 测试服务

```powershell
ml service mock SERVICE_ID -o json
ml service mock SERVICE_ID --request-sample '{"data":{"queryTexts":["自定义测试"]}}' -o json
ml service mock SERVICE_ID --transmission-tag 1 -o json
```

自动查询基本信息，默认查询服务文档并使用其中的请求样例执行一次测试。传入 `--request-sample JSON` 时跳过文档查询，使用传入的原始 JSON 字符串。两种测试均支持该选项，非法 JSON 会在平台请求前提示“样例报文不是标准的JSON格式，请检查！”。`result.nodeList` 包含各节点结果，`mockResponse` 为解析后的 JSON 值，`mockResponseRaw` 保留原始字符串。表格模式展示六列及完整的缩进 JSON 报文。

`--transmission-tag` 默认 `0`，不调用透传接口；指定 `1` 调用透传接口，仅支持这两个整数。

必要信息或默认文档样例缺失时停止；提供自定义报文时无需已有服务文档。失败节点或无效报文仍会展示，但退出码为 1；无节点也退出 1。全部节点结果码为 0 且报文有效才退出 0，内部业务结果仍须查看报文。超时、断连或认证失败不自动重发，不要盲目重试。

## 测试指定主机

```powershell
ml service host mock SERVICE_ID --pod-ip POD_IP -o json
ml service host mock SERVICE_ID --pod-ip POD_IP --request-sample '{"data":{"queryTexts":["自定义测试"]}}' -o json
ml service host mock SERVICE_ID --pod-ip POD_IP --transmission-tag 1 -o json
ml service host mock SERVICE_ID --pod-ip "IPv6" -o json
```

仅需提供 `--pod-ip`，先查询主机视图。返回记录的 `nodeId` 转为字符串填入 `node.hostId`，`nodeHost` 原样填入 `node.hostAddress`，不手工指定主机ID或拼接端口。查无主机时提示“目前主机不存在，请检查！”，停止后续调用；匹配多台、查询失败或必要字段缺失时同样停止。表格按每个返回节点使用“字段 / 值”两列展示，主机名称、机器规格、站点、结果码、耗时(ms) 依次列出，结果报文在最后一行完整展示缩进 JSON。其他请求字段、透传选项、JSON 输出及错误处理与服务测试相同。Pod IP 提示写入 stderr，stdout 保持 JSON 结果。

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
