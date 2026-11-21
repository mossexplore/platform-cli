# 服务与服务日志

## 定位服务与主机

用 `ml service --help` 在 `Commands` 面板找到子命令，再用对应子命令的 `--help` 核对用法、参数和必填项。服务 ID 示例需换成当前业务中实际查询到的 ID。

```powershell
ml service list --name SERVICE_NAME -o json
ml service list -A --name SERVICE_NAME
ml service host list SERVICE_ID -o json
ml service host list SERVICE_ID --pod-ip POD_IP -o json
ml service deployment list SERVICE_ID -o json
```

- 主机视图和部署视图只返回第一页 10 条，不能当作完整集合。主机视图中的 `nodeName` 是 Pod 名称。
- 主机视图不展示主机ID列与部署ID列；podIP 按 `nodeHost` 原值完整显示，优先单行保留 IP 和端口，其他长字段可换行。JSON 输出继续保留 `nodeId` 与 `deployId`。
- `host list --pod-ip IP` 按 Pod IP 筛选，传入值用于接口的 `hostIp`，无需端口；不传时不按 IP 筛选，空值会报错。主机测试也按所传 `--pod-ip` 查询主机视图。
- 部署视图首列为 `blockId`。

## 测试服务

```powershell
ml service mock SERVICE_ID -o json
ml service mock SERVICE_ID --request-sample-file '.\sample.json' -o json
ml service mock SERVICE_ID --request-sample-file '.\sample.json' --transmission-tag 1 -o json
```

- **前置与授权**：命令会实际调用一次服务（无 `--dry-run` 或 `--yes`），执行前先核对服务 ID、样例和用户测试意图。超时、断连或认证失败不盲目重试。
- **样例来源**：默认查询服务文档并使用其中的请求样例；指定 `--request-sample-file PATH` 时读取本地 UTF-8 JSON 文件（兼容 BOM，不修改原文件）并跳过文档查询。自定义报文只通过文件传入，勿构造 `--request-file` 等未定义参数；非法 JSON（“样例报文不是标准的JSON格式，请检查！”）、文件不可读或默认文档样例缺失时停止。
- **文档输入报文为空**：提示「[错误] 服务文档输入报文为空，请在该服务中补充相关信息后再次调用！」。文档样例支持 JSON 文本、对象和数组，文本可带 UTF-8 BOM。
- **透传控制**：`--transmission-tag` 默认 `0`（不调用透传接口），仅支持 `0` 或 `1`。
- **结果与退出码**：`result.nodeList` 包含各节点结果（`mockResponse` 为解析后的 JSON，`mockResponseRaw` 为原始字符串）。全部节点结果码为 0 且报文有效时退出 `0`；存在失败节点、无效报文或无节点时退出 `1`（即使退出 `1`，stdout 仍可能包含节点结果，需结合 stderr 一起核对，内部业务结果仍须查看报文）。

## 测试指定主机

```powershell
ml service host mock SERVICE_ID --pod-ip POD_IP -o json
ml service host mock SERVICE_ID --pod-ip POD_IP --request-sample-file '.\sample.json' -o json
ml service host mock SERVICE_ID --pod-ip POD_IP --transmission-tag 1 -o json
ml service host mock SERVICE_ID --pod-ip POD_IP --request-sample-file '.\sample.json' --transmission-tag 1 -o json
```

- **参数定位**：除 `SERVICE_ID` 外仅需 `--pod-ip`（无需手工填写主机 ID 或端口）。CLI 会先查询主机视图，若查无主机（“目前主机不存在，请检查！”）、匹配多台或必要字段缺失则停止。
- **其余规则**：请求样例、透传选项、`result.nodeList`、退出码及错误处理与 `ml service mock` 相同；Pod IP 提示写入 stderr，stdout 保持 JSON 结果。

## 查询 Pod 事件

```powershell
ml service host pod-event --pod POD_NAME --cluster-name CLUSTER_NAME -o json
ml service host pod-event SERVICE_ID --pod POD_NAME -o json
ml service host pod-event SERVICE_ID --no-input -o json
```

- **双模式寻址**：已知 `POD_NAME` 和 `CLUSTER_NAME`（来自 `ml service host list SERVICE_ID`）时可直接传 `--pod` 和 `--cluster-name`，无需 `SERVICE_ID`；传 `SERVICE_ID --pod POD_NAME` 时自动从主机列表补全集群名称；仅传 `SERVICE_ID` 且多台主机时，非交互模式需传 `--no-input` 并补齐参数。
- **输出**：表格展示 `类型`、`事件原因`、`消息`、`最后更新时间`（北京时间 `YYYY-MM-DD HH:mm:ss`）、`次数`，`eventContents` 为空时提示 `暂无 Pod 事件`；`-o json` 返回完整 `result`。

## 查询标准输出日志

```powershell
ml service host log-stdout --pod POD_NAME -o json
ml service host log-stdout --pod POD_NAME -c filebeat --no-input
ml service host log-stdout SERVICE_ID --no-input
```

- **双模式寻址**：已知 `POD_NAME` 时可直接 `--pod POD_NAME` 免 `SERVICE_ID` 查询；仅传 `SERVICE_ID` 时，仅单台主机自动选中，多台主机在非交互环境下需指定 `--pod`。
- **动态容器校验**：`-c` / `--container` 默认 `appcontainer`，容器集合动态取自接口返回的 `result.containerStates`（非固定 4 个）。若指定容器不在实际列表中，会停止查询并提示“该容器没有<容器类型>类型日志，请确认容器类型是否正确！”。
- **输出**：默认 `text` 先逐行打印全部容器状态（`容器名称：<name>，重启次数：<restartCount>，状态：<state>`），再输出 `详细日志：` 与展开换行的日志正文；`-o json` 返回完整 `result`（包含全部 `containerStates` 与 `data`）。

## 日志检索

在 shell 工具中必须加 `--no-input`，并明确传入 `--type`：

```powershell
ml service host log-search SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --list --no-input
ml service host log-search SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME -k error -n 200 --no-input
```

- 日志命令不支持 `-o json`：`--list` 输出文件表格，正文为原始文本，提示信息在 stderr。
- `--pod` 与 `--cluster-name` 必须成对提供。显式指定时，CLI 仍查询该服务的主机列表第一页，从首条记录读取 `infraType`，不核验指定 Pod 的归属。第一页为空时会报“主机列表为空，无法获取 infraType”。未指定 Pod 时，只有唯一主机才会自动选择。文件选择同理，有多个候选时补充参数或请用户选择。
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
