# 服务与服务日志

以下查询与操作默认使用 `--agent`（不与 `-o json` 同传）；仅在需要原始完整字段（如 `nodeId`、`deployId`、`mockResponseRaw`）时去掉 `--agent` 改用 `-o json`。

**高频最短链路**：
- **查服务与 Pod 诊断**：`ml service list --name 'NAME,NAME' --agent` → `ml service host list SERVICE_ID --agent`（取 `nodeName`、`clusterName`，`fixedFirstPage` 仅返回首页 10 条）→ `ml service host pod-event --pod POD_NAME --cluster-name CLUSTER_NAME --agent` / `ml service host log-stdout --pod POD_NAME --agent`
- **业务日志检索**：先 `--type TYPE --list --no-input --agent` 取文件名 → 再 `--type TYPE --file FILE_NAME -k KEY -n 200 --no-input --agent` 查正文

## 定位服务与主机

```powershell
ml service list --name 'SERVICE_NAME,SERVICE_NAME' --agent
ml service host list SERVICE_ID [--pod-ip POD_IP] --agent
ml service deployment list SERVICE_ID --agent
```

- `host list` 和 `deployment list` 仅返回首页 10 条，不能当作全量；`nodeName` 为 Pod 名称，`nodeHost` 为 Pod IP。
- `--pod-ip` 仅传 IP（不带端口），空值会报错。

## 服务与主机 Mock 测试

```powershell
ml service mock SERVICE_ID [--request-sample-file '.\sample.json'] [--transmission-tag 0|1] --agent
ml service host mock SERVICE_ID --pod-ip POD_IP [--request-sample-file '.\sample.json'] [--transmission-tag 0|1] --agent
```

- **真实调用且无内置确认**：无 `--dry-run` / `--yes`，执行前核对服务 ID、样例与用户意图；超时或断连不盲目重试。
- **参数规则**：不传 `--request-sample-file` 时自动读取服务文档样例；自定义报文只通过 `--request-sample-file` 传本地 UTF-8 JSON 文件（勿构造 `--request-file`）。`--transmission-tag` 默认 `0`，仅支持 `0|1`。`host mock` 仅需 `--pod-ip`（不带端口），无匹配或多台匹配时停止。
- **结果与退出码**：`--agent` 返回顶层 `nodeList`；全节点 `retCode=0` 且报文有效退出 `0`，否则退出 `1`（退出 `1` 时 stdout 仍可能含节点结果，须结合 stderr 与报文核对）。

## Pod 事件与标准输出日志

```powershell
ml service host pod-event --pod POD_NAME --cluster-name CLUSTER_NAME --agent
ml service host pod-event SERVICE_ID --no-input --agent
ml service host log-stdout --pod POD_NAME [-c CONTAINER] --agent
ml service host log-stdout SERVICE_ID --no-input --agent
```

- **双模式寻址**：已知 `--pod`（`pod-event` 需配 `--cluster-name`）时可省 `SERVICE_ID`；仅传 `SERVICE_ID` 时仅单台主机自动选中，多台主机在非交互下须传 `--no-input` 并补齐参数。
- **`pod-event`**：返回无分页列表 JSON（`items` 含 `type`、`reason`、`message`、`lastTimestamp`、`count`）。
- **`log-stdout`**：`-c` / `--container` 默认 `appcontainer`，合法容器名动态取自返回中的 `containerStates`（顶层含 `containerStates` 与 `data`）。

## 业务日志检索（`service host log-search`）

非交互环境必加 `--no-input` 并显式指定 `--type`（该命令不支持 `-o json`，加 `--agent` 时 `--list` 返回文件列表 JSON，正文返回 `{"content":"..."}`）：

```powershell
ml service host log-search SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --list --no-input --agent
ml service host log-search SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME -k error -n 200 --no-input --agent
```

- `--pod` 与 `--cluster-name` 必须成对提供（CLI 从主机列表首条读取 `infraType`）；未指定时仅唯一主机自动选中，多文件同理需补 `--file`。
- `--list` 与正文选项互斥；`-k` 可重复，`-n` 默认 `200`；高级选项：`--search-order tail|head`（默认 `tail`）、`--grep-scope A|B|C`、`--grep-line N`。
- **`--type` 类别**（无默认值，取决于主机 `infraType`，**禁传 `rtc_python`**）：
  - `infer-python`：`run`、`interface`、`metrics`、`engine`、`ascend`、`mslite`、`alarm`
  - `rtc`：`rtc`、`run`、`interface`、`dcs`、`metrics`、`gc`、`interface_manager`、`interface_extend`、`engine`、`monitor`、`catalina`、`dmq`
- 日志可能含敏感信息，仅摘录任务所需片段。
