# Go CLI 服务主机诊断命令设计方案

## 1. 背景与目标

在平台服务列表的主机视图中，每个部署元素（Pod/主机）具备四类高频操作：**主机测试**、**日志检索**、**Pod 事件**、**标准输出日志**。此前 `ml service` 存在三方面问题：

1. **资源层级割裂**：主机测试在 `ml service host mock` 下，而同样针对单主机的业务日志检索却挂在 `ml service logs` 下；
2. **两类日志语义易混淆**：业务落盘日志（日志检索）与容器标准输出日志（stdout）职责不同，均叫 `logs` 会产生歧义；
3. **主机寻址方式不统一**：不同命令对 `SERVICE_ID`、`--pod`、`--cluster-name` 的依赖各异，增加使用成本。

本次设计仅针对 **Go CLI（`cli-go`）**，不涉及 `cli-python`；在 **`wiserec`** 与 **`mlops`** 两种管理台下保持完全一致的命令结构、参数与输出行为。

---

## 2. 命令树重构设计

按“服务级放 `service` 根下，单主机/Pod 级全部归入 `service host` 下”的原则，将原 `ml service logs` 迁入 `ml service host log-search` 并直接移除 `ml service logs`，同时新增 `pod-event` 与 `log-stdout`：

```text
ml service                      服务查询、模拟调用与主机诊断
├── deployment                  服务部署视图查询
│   └── list                    查询指定服务的部署视图
├── host                        服务主机查询、测试与诊断
│   ├── list                    查询指定服务的主机视图
│   ├── log-search              检索指定主机的业务日志文件
│   ├── log-stdout              查询指定主机的标准输出日志
│   ├── mock                    使用样例报文测试指定主机
│   └── pod-event               查询指定主机的 Pod 事件
├── list                        分页查询当前业务的服务
└── mock                        使用样例报文测试服务响应
```

- `log-search` 与 `log-stdout` 采用统一 `log-*` 前缀，在 `ml tree` 与 `--help` 中相邻展示，语义明确；
- 均不设置 `platform=wiserec` 注解，`wiserec` 与 `mlops` 同等支持；
- 所有分组与子命令 `Short` 说明结尾不带标点，符合 `ml tree` 规范；
- 对 Go CLI 已演进的 `ml service` 及其 `host` 子命令改用 Cobra 原生帮助输出，避免沿用旧版 Python 静态帮助快照；在 `ml service` 根命令上拒绝未知子命令（如已移除的 `ml service logs`），返回参数错误。

---

## 3. 统一双模式主机寻址规则

`ml service host pod-event` 与 `ml service host log-stdout` 统一采用 **`[SERVICE_ID]` 可选位置参数 + `--pod` 命名选项** 的双模式寻址：

| 使用场景 | 调用方式 | 执行逻辑 |
| --- | --- | --- |
| 日常排查（只知道 `SERVICE_ID`） | `ml service host pod-event SERVICE_ID`<br>`ml service host log-stdout SERVICE_ID` | 查询主机列表；仅 1 台主机时自动选中，多台主机时复用分页交互选择器；非交互或 `--no-input` 时提示补充参数 |
| 脚本/直达（已知 Pod 信息） | `ml service host pod-event --pod POD_NAME --cluster-name CLUSTER_NAME`<br>`ml service host log-stdout --pod POD_NAME` | 无需 `SERVICE_ID`，直接调用目标接口，不发起多余的 `queryServiceHostList` 查询 |
| 省略集群名（`pod-event`） | `ml service host pod-event SERVICE_ID --pod POD_NAME` | 分页扫描该服务主机列表，按 `nodeName == POD_NAME` 精确匹配并自动补全 `clusterName`（查无或重名时报错） |

参数校验：
- 既未传 `SERVICE_ID` 也未满足直达条件时，返回退出码 `2`；
- `pod-event` 仅传 `--cluster-name` 而未传 `--pod` 时，返回退出码 `2`；
- 已显式传入的 `--pod`、`--cluster-name`、`-c/--container` 及位置参数均不能为空白。

---

## 4. 命令详细规格

### 4.1 `ml service host pod-event`（Pod 事件）

- **命令格式**：
  ```text
  ml service host pod-event [SERVICE_ID] [--pod POD_NAME] [--cluster-name CLUSTER_NAME] [--no-input] [-o table|json]
  ```
- **接口约定**：
  - `POST <api_endpoint>/ai/backend/mep/services/rtcContainer/queryPodEvent`
  - 请求头自动携带当前环境 `businessid`（取自 `business.json` 当前环境 `selected.businessId`）；
  - 请求体：
    ```json
    {
      "businessId": "<selected.businessId>",
      "podName": "<POD_NAME>",
      "clusterName": "<CLUSTER_NAME>"
    }
    ```
- **输出规则**：
  - `table`（默认）：列抬头固定为 `类型`（`type`）、`事件原因`（`reason`）、`消息`（`message`）、`最后更新时间`（`lastTimestamp`）、`次数`（`count`）；
    - `lastTimestamp` 按北京时间（UTC+8）格式化为 `YYYY-MM-DD HH:mm:ss`（例如 `2026-11-19T11:30:23Z` 展示为 `2026-11-19 19:30:23`）；
    - `result.eventContents` 为空数组 `[]` 时正常展示空表头并输出 `暂无 Pod 事件`，退出码为 `0`。
  - `json`（`-o json`）：完整输出接口 `result`，不裁剪扩展字段。

### 4.2 `ml service host log-stdout`（标准输出日志）

- **命令格式**：
  ```text
  ml service host log-stdout [SERVICE_ID] [--pod POD_NAME] [-c|--container CONTAINER_NAME] [--no-input] [-o text|json]
  ```
- **接口约定**：
  - `POST <api_endpoint>/ai/backend/mep/services/rtcContainer/queryPodLog`
  - 请求头自动携带当前环境 `businessid`；
  - 请求体：
    ```json
    {
      "businessId": "<selected.businessId>",
      "podName": "<POD_NAME>",
      "containerName": "<CONTAINER_NAME>"
    }
    ```
- **动态容器发现与校验规则**：
  - 容器个数及名称并非固定 4 个，而是以请求 `containerName: "appcontainer"` 时响应体中 `result.containerStates` 的实际元素列表为准；
  - `-c / --container` 默认值为 `appcontainer`，不做静态白名单限制，仅校验非空白：
    1. 默认或 `-c appcontainer`：发起 1 次 `queryPodLog`（`containerName: "appcontainer"`），校验 `result.containerStates` 中存在 `appcontainer` 后直接展示；
    2. 指定其他容器 `<NAME>`：先以 `containerName: "appcontainer"` 请求 `queryPodLog` 获取真实 `result.containerStates`；若 `<NAME>` 不在其中，立即中止（不发第二次请求）并返回错误：`该容器没有<NAME>类型日志，请确认容器类型是否正确！`；若存在，再以 `containerName: "<NAME>"` 请求目标容器日志并展示。
- **输出规则**：
  - `text`（默认）：每次按 `result.containerStates` 顺序逐行展示全部容器状态，随后打印 `详细日志：`，并将 `result.data.content` 按真实换行原文输出（空内容时提示 `暂无日志内容`）：
    ```text
    容器名称：appcontainer，重启次数：0，状态：running
    容器名称：filebeat，重启次数：0，状态：running
    容器名称：registercontainer，重启次数：0，状态：running
    容器名称：init1container，重启次数：4051，状态：running
    详细日志：
    2026-11-19T11:46:10.523164588Z the request body contain reqData
    2026-11-19T11:46:10.523533608Z [2026-11-19 19:46:10 +0800] [16]: [INFO] start check doing task
    ```
  - `json`（`-o json`）：校验通过后输出目标容器对应的完整 `result`。

### 4.3 `ml service host log-search`（日志检索）

- **命令格式**：
  ```text
  ml service host log-search SERVICE_ID [--pod POD_NAME --cluster-name CLUSTER_NAME] [--type TYPE] [--file FILE_NAME] [-k TEXT] [-n N] [--list] [--no-input] [--search-order ORDER] [--grep-scope SCOPE] [--grep-line N]
  ```
- 由原 `ml service logs` 迁入，保持全部参数、主机类型适配与交互/非交互行为不变；原 `ml service logs` 在 Go CLI 中直接移除。

### 4.4 `ml service host list` 表格列调整

- 表格视图移除首列 `部署 ID`（以 `集群` 为首列展示）；`-o json` 输出保持原始记录结构，继续保留 `deployId` 字段。

---

## 5. 实现落点与验证范围

- **核心实现**：
  - `cli-go/internal/command/service.go`：重构 `service` / `service host` 命令树并注册子命令；
  - `cli-go/internal/command/service_logs.go`：将命令重命名为 `log-search`；
  - `cli-go/internal/command/service_host_diag.go`：实现 `pod-event`、`log-stdout` 及双模式寻址、动态容器校验与渲染逻辑；
  - `cli-go/internal/command/python_help.go`、`python_help_test.go`、`testdata/python-cli.tsv`：切分 Go CLI 原生帮助与命令契约。
- **验证覆盖**：
  - `wiserec` 与 `mlops` 双管理台下的 `pod-event`、`log-stdout`、`ml tree` 与 `--help`；
  - `businessid` 请求头、`lastTimestamp` 北京时间转换、空事件数组、双模式寻址与参数校验；
  - `log-stdout` 动态容器探测、全部容器状态逐行打印、多行日志真实换行、缺失容器报错拦截、`-o json`；
  - 原 `ml service logs` 移除后的错误退出验证。
