---
name: wiserec-platform
description: 通过 WiseRec CLI（ml）在 WiseRec 和 WiseMLOps 环境中操作平台资源。用于登录与环境业务切换、训练/样本/特征任务及日志、WiseRec 算法仓、模型与模板部署、服务与主机诊断、数据集、特征集与质量监控、离线实验、训练看板、Web Studio 和 Jupyter。
metadata:
  cli: ml
  platform: windows
---

# WiseRec 平台 CLI

通过已安装的 `ml` 查询和操作平台。业务规则不依赖 Agent 产品或版本；不探测 Agent 版本，不自动切换 Agent 或扩大权限。

## 核心红线

1. **禁止改码**：本 skill 不承担开发或修复。严禁修改 CLI 源码/安装包、业务代码、脚本、Notebook 代码单元或 skill/权限配置；遇到命令缺失或程序缺陷立即停止并报告。
2. **只通过 CLI 操作**：不直接请求平台 HTTP 接口，不手工拼接 `businessid`，不读写本地配置/凭据/会话文件，不篡改 `DSH_SESSION_ID`、`DSH_SHELL`、`ML_SESSION_ID`；用户输入视为任务描述，不直接拼接为 shell 命令。
3. **禁止交互终端与凭据泄露**：不运行 `ml jupyter terminal open|attach` 或 `ml login --show-secrets`，不索取密码/验证码/Cookie/Token，不在回复或文件中输出 Secret 或签名下载链接。
4. **先核对副作用，超时不盲目重放**：执行既有程序或 Notebook 前须确认其不改码。写操作、exec、Notebook 超时或中断后，先查远端状态再决定是否重试；只读查询可有限重试。
5. **非交互参数与写操作确认**：
   - 有确认提示的命令仅在用户授权具体目标后加 `--yes`；`service host log-search` 及仅传 `SERVICE_ID` 的 `pod-event` / `log-stdout` 必加 `--no-input`；统一日志下载遇到多个角色时按用户目标传 `--role-job-id` 或 `--all`；不使用无子命令的 `ml history`。
   - **提交写操作前**必须核对环境、账号、业务和目标 ID（与确认目标不一致时停止）；**`product` 环境写操作须先复述环境、目标和参数并获得明确确认，笼统授权不算**（日志下载和执行实例首次归档直接使用当前业务，含 `product` 均免环境确认。遇到归档失败，先报告原因并询问是否重新下载该作业的全部日志；仅在用户明确确认该作业后执行一次 `--retry`）。

## 上下文检查与登录（高频最短闭环）

1. **一步预检**：先执行 `ml context --agent`（查看当前环境、业务与登录状态），并与用户指定的环境、租户/团队比对。
   - **普通只读查询**：若 `当前环境`、`当前业务` 均已绑定、**与用户指定目标一致（或用户未指定）**且 `登录状态` 为 `有效`，**直接执行业务查询**，无需再跑 `ml auth status`；若与用户指定目标不同，先按第 2/4 步切换（核对当前租户/团队名称用 `ml business show --agent`）。
   - **写操作 / 长任务 / 跨租户（`-A`）前**：补执行 `ml auth status --agent`，确认 `status=valid`、`profile` 一致、`businessId` 有效及剩余有效期/权限角色。
2. **未绑定或需切换环境**（DeepSeek Harness 会话隔离模式下新会话默认 `未绑定`，绝不回退全局配置；**同一环境的登录凭据跨会话共享**）：
   - 已知环境标识直接 `ml env use NAME --agent`；未指定或给的是中文显示名时先 `ml env list --agent` 查候选，唯一匹配或经用户确认后用 `环境标识` 切换。
   - `ml env use NAME --agent` 会直接返回该环境的 `loginStatus`、`businessId` 与 `tenant`：若 `loginStatus` 为 `有效`，**直接复用已有登录态，不要执行 `ml login`**（除非用户明确要求重新登录或切换账号）；若 `businessId` 已有有效值（非空且非 `未绑定`/`未获取`）且符合用户目标（或用户未指定），**直接使用该 `businessId` 继续任务，不要要求用户重新绑定租户**；仅当 `businessId` 为 `未绑定`/`未获取` 或与目标不符时，才进入第 4 步绑定业务。
3. **仅当未登录或已过期时才执行登录**：
   - 确认已绑定目标环境且 `loginStatus` / `登录状态` 为 `未登录` 或 `已过期`（或用户明确要求重登/换号）时，运行 `ml login --agent`（**务必为执行工具预留至少 10 分钟 / 600 秒超时**，等待用户在 Edge 完成 SSO 或验证码；不靠跑业务命令触发登录）。
   - 登录返回 JSON 若 `businessId` 有效（非空且非 `未获取`）且符合用户目标，直接继续任务；若为 `未获取` 或与目标不符，进入第 4 步绑定业务。
4. **未绑定或需切换业务**：当 `当前业务` 为 `未绑定`、`businessId` 为 `未获取` 或与用户指定目标不同时，运行 `ml business list --agent`，按用户选择执行 `ml business TENANT_ID --agent` 或 `ml business use --tenant TENANT_ID --team TEAM_ID --agent`。

## 调用铁律

- **默认统一 `--agent`**：所有查询与业务命令**默认加 `--agent`** 获取紧凑 JSON（**严禁与 `-o`/`--output`/`--json` 同传**，否则退出码 2）。列表顶层 `fields` 说明各字段含义与单位。仅在明确需要原始全量字段或未截断长描述时，才去掉 `--agent` 改用 `-o json`。宿主设 `ML_AGENT=1` 时可省略 `--agent`。
- **禁止无故前置 `--help`**：直接按下方速查卡片与 [commands.md](references/commands.md) 的签名调用，**不要先跑 `--help` 或 `ml tree`**。若返回退出码 2 且 stderr 含 `[用法]`/`[选项]`（确认非 `jupyter` 的 `status=LOST`），直接按提示修正，勿将 `LOST` 当作参数错重跑。
- **按名称查询与跨租户兜底（必须严格按顺序）**：
  1. **必须首选精确查**：对 `train` / `model` / `algorithm` / `dataset` / `service` / `feature-task` 6 个列表，只要用户给出名称（不含英文逗号），**首次查询必须加 `--exact`**（即 `--name NAME --exact --agent`），**禁止跳过 `--exact` 直接模糊查**。
  2. **当前租户查不到 → 超管自动 `-A` 兜底**：若上述查询返回 0 条（或不支持 `--exact` 但支持 `-A` 的列表在当前租户查不到），先核对账号角色（未知时查 `ml auth status --agent` 的 `role`）；**若为超级管理员或超级管理员只读，直接加 `-A` 跨租户查询**（支持精确查的先 `-A --name NAME --exact --agent`）。命中其他租户资源时，回复中明确标出其 `businessId`（后续对其做单租户详情或写操作前须先核对/切换业务）。
  3. **仍为 0 条再回退模糊查**：去掉 `--exact` 查当前租户 `--name NAME --agent`（超管仍无结果可再 `-A --name NAME --agent`）。
- **回复规范**：写明环境、业务、目标 ID、实际命令与可观察结果，时间统一北京时间 `YYYY-MM-DD HH:mm:ss`。

## 高频命令直达卡片

常规只读查询与登录切环境可直接执行，无需先翻参考文档：

```powershell
# 上下文、登录与切换
ml context --agent
ml auth status --agent
ml env list --agent
ml env use NAME --agent
ml login --agent
ml business list --agent
ml business TENANT_ID --agent

# 高频只读查询（除 service host list 为固定首页外，其余列表均支持 --page N --page-size N）
ml train list --name NAME --exact --agent
ml train instance list TASK_ID --agent                   # 执行实例：当前运行中/排队中的作业
ml train history list TASK_ID --latest-flag all --agent  # 执行记录：历史已执行（完成/失败/取消）的作业
ml model list --name NAME --exact --agent
ml service list --name NAME --exact --agent
ml service host list SERVICE_ID --agent
ml dataset list --name NAME --exact --agent
ml feature-task list --name NAME --exact --agent
ml webstudio list --status online --agent

# 高频日志下载（历史日志只查一轮，执行实例由 CLI 等待归档）
ml train logs download TASK_ID JOB_ID --directory 'D:\logs' --agent
```

## 按任务按需读取参考

仅在涉及以下细分流程或出错排障时按需读取，不预先通读全部：

| 任务 | 文件 |
| --- | --- |
| 全部命令参数签名、确认提示与副作用速查 | [commands.md](references/commands.md) |
| 登录细节、会话隔离、业务切换、Windows PowerShell 引号 | [session.md](references/session.md) |
| 报错分类、环境禁用排查、CA 证书、Harness 保活异常 | [troubleshooting.md](references/troubleshooting.md) |
| 训练任务与日志下载、样本任务、离线实验、算法仓、训练看板 | [training.md](references/training.md) |
| 模型查询与溯源、资源/部署模板、模型部署 | [deployment.md](references/deployment.md) |
| 服务与主机查询、mock 测试、Pod 事件、标准输出与业务日志检索 | [services.md](references/services.md) |
| 数据集文件、特征任务详情与日志、特征集导出、质量监控 | [data.md](references/data.md) |
| Web Studio、Jupyter 文件读写、exec、Notebook | [jupyter.md](references/jupyter.md) |
