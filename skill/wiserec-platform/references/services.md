# 服务与服务日志

## 定位服务与主机

```powershell
ml service list --name SERVICE_NAME -o json
ml service host list SERVICE_ID -o json
ml service deployment list SERVICE_ID -o json
```

- 主机视图和部署视图只返回第一页 10 条，不能当作完整集合。主机视图中的 `nodeName` 是 Pod 名称。
- 主机视图在部署 ID 后展示“主机ID”，取自 `nodeId`，缺失时显示 `-`。
- 部署视图首列为 `blockId`。

## 测试服务

```powershell
ml service mock SERVICE_ID -o json
ml service mock SERVICE_ID --transmission-tag 1 -o json
```

自动查询基本信息与服务文档，使用默认请求样例执行一次测试。`result.nodeList` 包含各节点结果，`mockResponse` 为解析后的 JSON 值，`mockResponseRaw` 保留原始字符串。表格模式展示六列及完整的缩进 JSON 报文。

`--transmission-tag` 默认 `0`，不调用透传接口；指定 `1` 调用透传接口，仅支持这两个整数。

必要信息或有效样例缺失时停止。失败节点或无效报文仍会展示，但退出码为 1；无节点也退出 1。全部节点结果码为 0 且报文有效才退出 0，内部业务结果仍须查看报文。超时、断连或认证失败不自动重发，不要盲目重试。

## 测试指定主机

```powershell
ml service host mock SERVICE_ID --node-id NODE_ID --pod-ip IP:PORT -o json
ml service host mock SERVICE_ID --node-id NODE_ID --pod-ip IP:PORT --transmission-tag 1 -o json
ml service host mock SERVICE_ID --node-id NODE_ID --pod-ip "[IPv6]:PORT" -o json
```

必须通过 `--node-id` 提供主机列表中 `nodeId` 的值，不可为空，按字符串传给 `node.hostId`。同时必须提供完整 IPv4 或 IPv6 地址及 1–65535 的端口，无默认端口。不接受域名、URL、路径或查询参数，不根据 Pod IP 或主机 IP 猜测测试地址，也不验证地址归属。请求在原有服务测试的 `data` 中增加 `node.hostId` 和 `node.hostAddress`，其他字段、透传选项、输出及错误处理与服务测试相同。目标地址提示写入 stderr，stdout 保持 JSON 结果。

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
