# Go CLI 训练日志统一下载与自动等待设计方案

## 1. 背景与当前痛点

当前 Go CLI 将训练日志下载拆为 `ml train instance logs download`（运行中实例）与 `ml train history logs download`（历史执行记录）两条割裂链路，存在 4 个核心问题：

1. **后端接口分叉直接暴露给用户与 Agent**：调用方必须先判断作业是在运行中还是已结束，再决定调哪条命令。
2. **等待步骤分散**：执行实例持续归档时，Agent 在命令外自行等待并重跑会重复提交作业级请求。
3. **状态难以判读**：历史日志暂不可用时，旧命令可能同时返回顶层 `failed` 和条目 `not_ready`。执行实例则需要单独表达服务端正在归档。
4. **角色选择方式割裂**：`history` 按 `--role-job-id` 指定机器 ID，`instance` 却按 `--select '1,3'` 指定人类表格行号，对 Agent 极不友好。

**设计目标**：在不改动平台后端接口、完全保留旧命令向后兼容的前提下，新增面向用户意图的统一入口 `ml train logs download`，内置安全的自动等待轮询与统一状态机，并将 Skill 中的训练日志指引大幅精简。

---

## 2. 命令契约与向后兼容

### 2.1 命令格式

```text
ml train logs download TASK_ID [JOB_ID] [OPTIONS]
```

| 参数 / 选项 | 默认值 | 说明 |
| --- | --- | --- |
| `TASK_ID` | 必填 | 训练任务 ID |
| `JOB_ID` | 可选 | 作业 ID；省略时按第 3.1 节规则选取最新作业并锁定该 ID |
| `--type` | `log` | 日志类型：`log` 或 `plog`（`plog` 仅历史作业支持；运行中作业传 `--type plog` 返回退出码 2） |
| `--role-job-id` | 无 | 分布式角色 ID，可重复指定（支持多个角色） |
| `--all` | `false` | 分布式或多节点作业中跟踪并下载全部目标角色（与 `--role-job-id` 互斥） |
| `--retry` | 关闭 | 用户确认后为整个执行实例作业重新下载普通日志，须显式提供原 `JOB_ID`。覆盖作业内所有角色，无需提供归档或角色 ID，与 `--role-job-id` 互斥 |
| `--directory` | 当前目录 | 本地保存目录（保存目录须已存在，同名自动编号不覆盖） |
| `--wait` / `--no-wait` | `--wait` 开启 | 执行实例默认只读复查仍在归档的角色；`--no-wait` 只检查一轮并下载可用项。执行实例按第 3.2 节处理 |
| `--poll-interval` | `30` | 轮询间隔秒数（正整数） |
| `--wait-timeout` | `120` | 执行实例的归档等待秒数，从首轮处理完毕起算，所有目标共用截止时间。`0` 等价于 `--no-wait`，负数为用法错误 |
| `--output` / `-o` | `table` | `table` 或 `json`；支持全局 `--agent`（与 `-o` 互斥） |

### 2.2 向后兼容

- 保留既有 `ml train instance logs download` 与 `ml train history logs download` 及其全部原有参数与测试，不破坏现有脚本。
- `ml tree` 中在 `train` 下新增 `logs` → `download`（说明结尾无标点，符合命令树规范）。

---

## 3. 自动路由、归档安全边界与角色选择

### 3.1 作业定位与“最新作业”选取规则

- **指定 `JOB_ID`**：先查当前任务运行中实例，命中走 `running` 通道；未命中再查历史记录（`latestFlag=all`），命中走 `history` 通道；均未命中报错退出 `1`。
- **省略 `JOB_ID`**：现有平台接口（`TrainInstances` / `TrainHistory`）默认使用 `ascend` 升序，绝不直接取首页第一条。须跨页扫描确定最新作业并**立即锁定该 `JOB_ID`**（等待或切换通道期间绝不漂移到新启动的作业）：
  - 优先在运行中实例中按 `createTime` 最大值选取（时间相同按 `jobId` 字典序较大者决胜）；
  - 若无运行中实例，在历史记录（`latestFlag=all`）中按 `createTime`（缺失时回退 `statusTime`）最大值选取（时间相同按 `jobId` 字典序较大者决胜）。

### 3.2 历史日志查询下载与执行实例归档下载

- **`history` 通道（只读查询历史日志并下载）**
  1. 校验任务、作业及所选角色。普通日志通过 `queryJobLogIsExist` 检查可用性，通过 `downloadLogUrl` 获取地址。取得有效地址后下载文件。
  2. 普通日志返回 `ErrLogNotReady` 时记录 `not_ready` 并结束该项。历史作业始终只查一轮。权限、网络、无效响应等错误按实际阶段报告。文件传输沿用下载层超时。
  3. 对 `plog` 按所选记录检查 `HasPlog`，可用时直接通过 `downloadPlog` 取址，不可用时报告原因并结束该项。
- **`running` 通道（严禁盲目轮询）**：
  - 现有 `runningLog` 的 `archive` 参数仅在客户端切换 `a.Mutation` / `a.JSON`，并非后端只读开关，不能通过传 `false` 冒充只读查询（且会绕过 `Mutation` 写前锁校验）。
  - **`running` 通道仅允许发送 1 次 `getRunJobLogArchiveList`（走 `a.Mutation`）**：
    1. 每次执行 running 下载（重新下载须先取得第 3.3 节的作业级确认）先调用 `POST /ai/backend/mtp/train/getRunJobLogArchiveList`。`result.code == 0` 表示服务端已收到归档请求。请求失败或响应无效时报告归档阶段错误并停止；空列表按 `archiving` 返回。
    2. 普通下载按记录状态处理：归档中（`0`）标记待就绪；归档成功（`1`）正常取址；归档失败（`2`）报告失败原因及目标标识，结束该项。用户确认重新下载后，按当前业务、任务和作业 ID 发送一次作业级请求，由服务端决定是否实际重新归档。`code=0` 只表示请求已受理。遍历本次返回的全部日志记录，归档中的记录进入同一次命令的等待队列，成功或失败状态的记录均可取址。采用本次返回的记录标识，允许服务端返回新的归档 ID。可取址项使用其 `roleJobId`、`archiveId`、`createUser` 及任务、作业和业务信息调用 `POST /ai/backend/mtp/train/getRunningJobLogUrl`。
    3. 根据取址接口的本次响应判断能否下载。业务成功且返回有效 `downloadUrl` 时执行下载，以文件落盘作为成功条件。若仍在归档，只对待处理记录按原归档 ID 定时调用取址接口。默认间隔 30 秒、上限 120 秒，含首次最多 5 轮，到期执行最后一次检查。明确返回归档失败时记录原因，到期仍在归档记为等待超时；业务拒绝、缺失或无效地址以及传输失败均记录实际失败阶段。沿用现有地址校验、签名链接隔离和同名文件自动编号规则。
    4. 首次失败和显式重试的结果均按第 4.1 节汇总。取址失败、传输失败和重试再次失败均报告实际原因，本轮到此结束。
  - 普通下载中，同一 `roleJobId` 匹配多条归档记录（多个 `archiveId`）时，按归档记录的 `createTime` 比较实际时刻，取最大值。若任一候选时间缺失、无法解析，或多个不同 `archiveId` 并列最新，该角色记为选择失败并列出候选 ID，不依赖返回顺序。
  - **运行中转历史兜底**：初次定位并锁定作业后，在发送归档请求前复核完整实例列表。仅当列表查询成功且原 `JOB_ID` 已消失时，普通下载才按原任务、业务和作业 ID 切入 history；显式重试直接报告原目标已消失。平台层须将“完整列表无此实例”与“任务或业务不匹配”区分为可判别的结果；归属异常、分页不完整、网络或鉴权失败均直接报错。running 归档请求一经发出，本次调用不再切换通道或重发。

### 3.3 普通下载的角色选择与作业级重新下载确认

以下角色选择规则适用于普通下载。作业级重新下载直接处理全部角色。

- **单机作业**：直接下载；误传 `--role-job-id` 或 `--all` 返回退出码 `2`。
- **分布式 / 多节点作业**：
  - 传 `--role-job-id`：仅跟踪并下载指定角色（不存在直接报错）；
  - 传 `--all`：跟踪全部目标角色/节点，每个已就绪目标只下载一次。仅 running 的 `--wait` 模式继续轮询归档中条目；history 和 `--no-wait` 均在本轮处理后汇总；
  - 均未传且仅 1 个角色/节点：自动下载；
  - 均未传且有多个角色/节点：非交互 / `--agent` 下返回退出码 `2`，在 `stderr` 列出可选 `roleJobId`、`roleType` 与状态（自愈提示，1 轮选定）。
- 常规下载及 running 首次归档均免环境确认，适用于包括 `product` 在内的所有环境。权限、归属校验及写保护照常执行。
- 普通下载发现一项或多项归档失败时，汇总失败原因，针对整个作业提示一次“是否重新下载该作业的全部日志”。失败记录用于解释提示原因。用户可执行 `ml train logs download TASK_ID JOB_ID --retry` 确认一次作业级操作。Agent 代为执行前须取得对该作业的明确同意。拒绝或未答复即停止；普通命令重跑、角色选择、`--all` 和等待选项均不构成确认。重新下载仍有失败时，报告本次结果并结束。

> 等待期间的进度提示统一写入 `stderr`，在 JSON 或 Agent 模式下将结果作为单个 JSON 写入 `stdout`；收到 `Ctrl+C`（`ctx.Done()`）立即中止并返回退出码 `130`。

---

## 4. 统一状态机、输出结构与退出码

### 4.1 终态定义

| `status` | 退出码 | 含义 |
| --- | --- | --- |
| `succeeded` | `0` | 全部目标日志均已下载完成 |
| `archiving` | `0` | 仅 running：归档请求已受理，列表为空或单轮检查后全部目标均在归档中 |
| `not_ready` | `0` | 仅 history：单轮检查后全部目标普通日志暂不可用，不提交归档 |
| `wait_timeout` | `1` | 仅 running：最后一轮检查后所有目标仍在归档 |
| `partial` | `1` | 至少一个目标下载成功，且至少一个失败、待就绪或等待超时；覆盖两个通道及两种等待模式 |
| `failed` | `1` | 作业级错误，或零个目标下载成功且至少一个明确失败；其余目标仍待就绪时也保留各自状态 |

### 4.2 `--agent` 输出结构示例

```json
{"status":"succeeded","source":"history","taskId":"TASK_ID","jobId":"JOB_ID","type":"log","waitedSeconds":0,"items":[{"roleJobId":"ROLE_ID","roleType":"worker","status":"succeeded","file":"D:\\logs\\job-worker.zip","bytes":102400}]}
```

- `source` 明确标识实际命中通道（`running` 或 `history`）。
- 失败或超时条目在 `items[]` 中给出 `stage` 与 `error`（或 `message`），不泄露签名下载链接。

---

## 5. 代码模块规划与同步清单

严格遵守 `AGENTS.md` 单模块 `< 500 LoC` 规范，零后端接口改动：

| 文件 | 变更内容 |
| --- | --- |
| `cli-go/internal/command/train_logs_unified.go`（新增，~300 行） | 实现 `ml train logs download` 统一入口、跨页最新作业选取与锁定、`history` 单轮只读检查与执行实例 `--wait` 轮询器、`running` 单次触发与转历史兜底、统一状态机渲染 |
| `cli-go/internal/platform/train_logs.go` | 复用受写保护的归档请求和取址请求构造。区分普通下载与经确认的作业级重新下载；归档请求按作业发送一次，取址按本次返回的记录分别执行，旧入口沿用原有就绪校验。区分归档前实例消失与归属校验失败 |
| `cli-go/internal/command/train.go` | 将 `newTrainUnifiedLogs` 挂载为 `ml train logs` 子命令组 |
| `cli-go/internal/command/train_logs_unified_test.go`（新增） | 覆盖全部路由、跨页最新选取、轮询、超时、中断与异常场景（注入假时钟） |
| `cli-go/internal/command/testdata/python-cli.tsv` | 登记 `train logs download` 及其选项 |
| `versions.toml`、`cli-go/cmd/ml/version.go`、版本测试、`README.md`、发布说明 | 按 `AGENTS.md` 将 `components.cli_go` 补丁号 `+1`，运行 `scripts/sync_versions.py` 与 `--check`，并同步 README、发布说明及版本测试 |
| `docs/guides/WiseRec CLI 使用手册.md` | 同步命令树与训练任务章节，给出用户确认后按原任务及作业 ID 重新下载的示例（不写版本信息） |
| `skill/wiserec-platform/`、`scripts/skill_index/commands.md.in` | 切换日志下载主入口为 `ml train logs download`，说明 history 查询已有日志，running 出现归档失败时按作业汇总提示。常规下载免环境确认，Agent 重新下载前必须取得用户对整个作业的确认，移除 `history` 手工 `Start-Sleep` 重试段落，工具超时按配置的等待时长另加查询和文件传输时间，运行 `scripts/sync_skill_index.py` 与 `--check` |

---

## 6. 验收测试矩阵

1. **自动路由与跨页最新选取**：传运行中 `JOB_ID` 命中 `running`；传历史 `JOB_ID` 命中 `history`；省略 `JOB_ID` 时跨页（模拟升序多页数据）准确选中 `createTime` 最新作业并锁定该 `JOB_ID`。
2. **history 单轮只读下载**：验证普通日志先检查可用性再取址，成功落盘返回 `succeeded(0)`，全部暂不可用立即返回 `not_ready(0)`。验证 plog 可用时直接取址、不可用时结束该项。对所有 history 路径断言 `manualArchiveLog` 与 `getRunJobLogArchiveList` 调用次数均为零。
3. **running 单次归档与转历史**：已锁定的运行中作业只发送一次受写保护的归档请求。检查实际 HTTP 调用顺序与次数：归档请求被拒绝或列表为空时取址次数为零；关闭等待且单目标归档中时返回 `archiving(0)` 且不取址；归档成功时正常取址，归档失败时返回失败项，断言该项取址和下载次数均为零（含 `--all`、`--wait` 和普通重跑）。覆盖取址失败、空地址和传输失败时的阶段、退出码及零个完整文件。验证 Agent 在用户拒绝或未回复时执行零次重试；用户确认后，即便上一轮存在多个失败角色，也只发一次作业级归档请求，校验请求数据为 `businessId`、`taskId`、`jobId`。分别模拟服务端沿用已有记录、返回新归档 ID 和返回归档中记录，验证按本轮全部记录处理，状态为 1 或 2 的逐条取址，状态为 0 的在启用等待时定时复查取址。作业消失或归属不符时停止，重试失败后不自动再试。颠倒同角色多条记录的顺序，仍选中相同的最新归档；时间缺失或并列最新时验证候选 ID 及零次文件下载。归档前复核发现实例已消失时，断言 running 归档请求为零、history 仅读取原作业日志、结果的 `source=history` 及文件内容。归属不符、列表不完整、网络或鉴权错误时断言历史接口调用次数为零。
4. **多角色汇总**：对每例核对顶层状态、退出码、逐项结果和落盘文件数。running 等待时，A 已下载、B 超时返回 `partial(1)` 和一个文件；全部待就绪直到截止返回 `wait_timeout(1)` 和零个文件；A 明确失败、B 始终未就绪返回 `failed(1)` 和零个文件。全部成功时每份文件只落盘一次。running 和 history 的 `--no-wait` 在一项成功、一项待就绪时均返回 `partial(1)`，不再查询。多角色缺少选择时验证非交互退出码 `2` 和角色候选。
5. **时间、中断、请求头与免确认**：用假时钟验证默认第 30、60、90、120 秒复查，最后一轮就绪仍可下载，并覆盖最后一轮仍归档、明确失败和取消；等待时间设为零时仍可下载已就绪文件。轮询期间按 Ctrl+C 返回 `130`。WiseRec 与 MLOps 的平台业务请求头 `businessid` 取自 `business.json` 当前环境的 `selected.businessId`，签名文件下载请求不携带该头。在模拟的 `product` 环境中，以关闭的标准输入分别执行参数齐全的 running 和 history 下载，验证 history 只读取址并下载、running 提交一次首次归档请求并正常下载归档成功项，且没有环境或归档确认提示。
6. **回归与生成校验**：`cd cli-go && go test ./...`、版本测试、`scripts/sync_versions.py` + `--check`、`scripts/sync_skill_index.py` + `--check`、`pytest tests -k skill` 全部通过。
