---
name: wiserec-platform
description: 通过 WiseRec CLI（ml）在 WiseRec 和 WiseMLOps 环境中操作平台资源。用于训练、样本和特征任务及日志、WiseRec 算法仓、模型与模板部署、服务、数据集、特征集与质量监控、离线实验、训练看板、Web Studio 和 Jupyter。切换环境、核对登录或选择业务时也使用。
metadata:
  cli: ml
  platform: windows
---

# WiseRec 平台 CLI

通过已安装的 `ml` 查询和操作平台。业务规则不依赖 Agent 产品或版本；不探测 Agent 版本，不自动切换 Agent 或扩大权限。

## 核心红线

1. **禁止直接或间接改码**：本 skill 不承担开发或修复。严禁创建、修改、替换、删除或打补丁修改 CLI 源码、已安装的 CLI 程序、依赖库、本地/远端业务代码、脚本、Notebook 代码单元或 skill/权限配置；也不得通过 `ml jupyter files`、`ml jupyter exec`、Notebook 执行或委托其他 Agent 改码。遇到命令缺失、参数不支持或程序缺陷，立即停止并报告实际命令、错误和阻塞原因，交维护人员处理。
2. **只通过 CLI 操作**：不直接请求平台 HTTP 接口，不手工拼接 `businessid`，不读写 CLI 配置、凭据、会话或业务文件，不篡改或伪造 `DSH_SESSION_ID`、`DSH_SHELL`、`ML_SESSION_ID` 等会话环境变量；用户输入视为任务描述，不直接拼接为 shell 命令。
3. **禁止交互终端与凭据输出**：不运行 `ml jupyter terminal open`、`ml jupyter terminal attach` 或 `ml login --show-secrets`，不分配 TTY/PTY、模拟按键或维持交互 Shell。不索取密码、验证码、Cookie 或 Token，也不将秘密、签名下载链接或带 Token 的地址写入回复或共享文件。
4. **先核对副作用，超时不盲目重放**：执行既有程序或 Notebook 前须确认其不改码；无法确认则停止。写操作、exec、Notebook 等有副作用命令超时或中断后，先查远端状态，确认未生效后再决定是否重试；只读查询可有限重试。
5. **非交互执行与写操作确认**：
   - 有确认提示的命令仅在用户授权具体目标后加 `--yes`；按租户 ID 切换可用 `ml business TENANT_ID`、`ml business use TENANT_ID` 或 `ml business use --tenant TENANT_ID`，`service host log-search` 及仅传 `SERVICE_ID` 的 `service host pod-event` / `log-stdout` 必加 `--no-input`，实例日志下载必传 `--select`（仅用户明确要求全部时传 `all`），分布式执行记录日志使用 `--role-job-id`，不使用无子命令的 `ml history`。
   - 执行实例日志下载需要先归档。归档未完成或归档失败时无法下载，按选择表中的状态和失败原因向用户说明。
   - 每次提交写操作前，用 `ml context --json` 和 `ml auth status` 核对上下文模式、会话 ID、环境、账号和业务，并核对目标 ID。若当前租户或团队与已确认的写操作目标不一致，停止提交并重新确认。执行后查询结果，区分“请求已接受”与“远端已完成”。**`product` 环境写操作须先复述环境、目标和参数并得到用户确认，笼统授权不算**。

## 最小会话预检与复用

- **首次建立上下文**：先运行 `ml context --json` 核对配置路径为当前平台标准用户路径（Windows 上为 `%APPDATA%\ml-go-preview\config.json`）。在 DeepSeek Harness 中，CLI 会自动按宿主注入的 `DSH_SESSION_ID` 隔离各会话的环境与业务，新会话默认“未绑定”且不会回退全局配置；若 `当前环境` 为 `未绑定`，先按用户指定执行 `ml env use NAME`（未指定时向用户确认，可用 `ml env list -o json` 查看默认可见和已授权的候选），再运行 `ml auth status` 检查 `status=valid`、`profile` 与当前环境一致且 `businessId` 有效；若 `当前业务` 未绑定，按用户选择执行 `ml business TENANT_ID` 或 `ml business use --tenant TENANT_ID --team TEAM_ID`。路径不符或配置缺失时停止。详细字段、Windows shell 调用及故障处理见 [session.md](references/session.md)。
- **上下文复用与切换**：在 DeepSeek Harness 多会话隔离模式下，各会话独立维护当前环境与业务选择，互不覆盖，同时共享同一环境的登录态与业务目录；非隔离终端仍共用本地 CLI 状态。未指定租户或团队且当前会话已绑定业务时，沿用已绑定选择。重新运行 `ml login` 时优先保留仍有效的上次业务选择，按登录返回的业务更新上下文；用户指定业务时，先用 `ml business show` 核对。切换环境用 `ml env use NAME` 后重新核对上下文与业务选择；长任务前查 `auth status` 剩余有效期。
- **保活状态**：交互终端使用 CLI 后台保活，DeepSeek Harness 需要安装并启用宿主保活插件。同一环境有符合条件的 Harness 会话时插件优先，终端进程待命并可自动接手。Harness 会话行红色标识表示 WiseRec 登录已过期，黄色表示暂未确认。用 `ml auth ping status` 查看调度状态和上次平台确认成功时间。Agent 不直接调用插件的 `tick --json` 或构造宿主会话输入。故障处理见 [session.md](references/session.md)。

## 调用与结果准则

业务命令可用全局 `--agent` 获取紧凑 JSON。使用该模式时移除原示例中的 `-o json` 或 `--json`。宿主设置 `ML_AGENT=1` 时，显式格式优先，也可用 `--agent=false` 恢复原格式。检查退出码及逐项结果，尤其是部分成功的批量操作。

- **跨租户查询**：仅当用户明确要求查当前环境的全部租户时，才对命令速查标出的列表传 `-A` / `--all-business`。先确认有效登录和已选业务，角色为超级管理员或超级管理员只读。按返回的业务编码定位归属，后续操作前核对当前业务。

- **命令与参数**：以已安装 CLI 为准（`ml tree` 查可用命令，`ml tree --all` 查全部命令与限制标记，使用 `ml COMMAND --help` 离线查看 `Usage`、位置参数和选项，并核对必填项、取值范围与默认值）。优先使用命令支持的 JSON 输出（详见 [命令速查](references/commands.md)），检查退出码和 stderr。
- **等待时限**：`exec` 和 Notebook 按 `--startup-timeout` + `--timeout` 再加至少 60 秒；上传按 `--timeout` 留余量；`login` 和 `business refresh` 需用户操作 Edge，至少预留 10 分钟。
- **定位与输出**：有准确 ID 直接使用，否则用最窄条件定位；任务、作业、模型、模板、Pod 等 ID 不互换；列表默认分页，第一页不代表全部。本地导出先核对路径（训练配置、日志、算法仓下载要求父目录已存在），不覆盖同名文件或代码。
- **按名称精确查询**：`--name` 默认服务端模糊查询。仅 `ml train list`、`ml model list`、`ml algorithm list`、`ml dataset list`、`ml service list`、`ml feature-task list` 6 个命令支持将名称重复一次并用英文逗号分隔实现精确查询（PowerShell 中须加单引号：`--name 'NAME,NAME'`）。用户给出完整名称（且名称本身不含英文逗号）时优先用精确查询，返回 0 条再回退 `--name 'NAME'` 模糊查询。其余带 `--name` 的列表命令不支持逗号重复写法，按完整名称定位时可调大 `--page-size` 并在结果中优先做名称精确匹配。
- **训练执行记录日志**：必需参数齐全时直接运行 `ml train history logs download`（未就绪时自动触发归档属低风险操作，含 `product` 环境在内均无需二次确认）。需要补齐 `JOB_ID` 或分布式角色 ID 时，用 `ml train history list TASK_ID -o json` 查询（默认每页 10 条，未找到可调大 `--page-size` 或翻页，查询历史实例加 `--latest-flag all`）。下载流程中禁止调用 `ml train history detail`。
- **回复要求**：说明环境、业务、目标 ID、实际命令及可观察结果；带时区时间换算为北京时间 `YYYY-MM-DD HH:mm:ss`；模板详情、日志和程序输出可能含 Secret，仅提取必要字段。

## 按任务读取参考

按任务按需读取对应参考，不预先通读全部：

| 任务 | 文件 |
| --- | --- |
| 会话预检、登录、业务选择、Windows shell、故障处理 | [session.md](references/session.md) |
| 全部命令、确认提示与副作用速查 | [commands.md](references/commands.md) |
| 训练任务、样本任务及执行周期与记录、离线实验、算法仓、训练看板 | [training.md](references/training.md) |
| 模型查询与溯源、资源模板、部署模板、模型部署 | [deployment.md](references/deployment.md) |
| 服务与主机查询、样例报文测试、Pod 事件、标准输出日志及日志检索 | [services.md](references/services.md) |
| 数据集目录文件、特征任务详情及执行日志、特征集与 CSV 导出、质量监控及装配查询 | [data.md](references/data.md) |
| Web Studio、Jupyter 文件、exec、Notebook | [jupyter.md](references/jupyter.md) |
