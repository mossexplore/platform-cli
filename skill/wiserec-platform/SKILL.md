---
name: wiserec-platform
description: 通过 WiseRec CLI（ml）在 WiseRec 和 WiseMLOps 环境中操作平台资源。用于训练、样本和特征任务及日志、WiseRec 算法仓、模型与模板部署、服务、数据集、特征集与质量监控、离线实验、MEP 配置、训练看板、Web Studio 和 Jupyter。切换环境、核对登录或选择业务时也使用。
metadata:
  cli: ml
  platform: windows
---

# WiseRec 平台 CLI

通过已安装的 `ml` 查询和操作平台。业务规则不依赖 Agent 产品或版本；不探测 Agent 版本，不自动切换 Agent 或扩大权限。

## 核心红线

1. **禁止直接或间接改码**：本 skill 不承担开发或修复。严禁创建、修改、替换、删除或打补丁修改 CLI 源码、已安装的 CLI 程序、依赖库、本地/远端业务代码、脚本、Notebook 代码单元或 skill/权限配置；也不得通过 `ml jupyter files`、`ml jupyter exec`、Notebook 执行或委托其他 Agent 改码。遇到命令缺失、参数不支持或程序缺陷，立即停止并报告实际命令、错误和阻塞原因，交维护人员处理。
2. **只通过 CLI 操作**：不直接请求平台 HTTP 接口，不手工拼接 `businessid`，不读写 CLI 配置、凭据或业务文件；用户输入视为任务描述，不直接拼接为 shell 命令。
3. **禁止交互终端与凭据输出**：不运行 `ml jupyter terminal open`、`ml jupyter terminal attach` 或 `ml login --show-secrets`，不分配 TTY/PTY、模拟按键或维持交互 Shell。不索取密码、验证码、Cookie 或 Token，也不将秘密、签名下载链接或带 Token 的地址写入回复或共享文件。
4. **先核对副作用，超时不盲目重放**：执行既有程序或 Notebook 前须确认其不改码；无法确认则停止。写操作、exec、Notebook 等有副作用命令超时或中断后，先查远端状态，确认未生效后再决定是否重试；只读查询可有限重试。
5. **非交互执行与写操作确认**：
   - 有确认提示的命令仅在用户授权具体目标后加 `--yes`；`business use` 必传 `--tenant`，`service logs` 必加 `--no-input`，实例日志下载必传 `--select`（仅用户明确要求全部时传 `all`），分布式执行记录日志使用 `--role-job-id`，不使用无子命令的 `ml history`。
   - 每次提交写操作前，用 `ml context --json` 和 `ml auth status` 核对环境、账号和业务，并核对目标 ID。若当前租户或团队与已确认的写操作目标不一致，停止提交并重新确认。执行后查询结果，区分“请求已接受”与“远端已完成”。**`product` 环境写操作须先复述环境、目标和参数并得到用户确认，笼统授权不算**。

## 最小会话预检与复用

- **首次建立上下文**：先运行 `ml context --json` 核对配置路径为当前平台标准用户路径（Windows 上 Python 客户端为 `%APPDATA%\ml\config.json`，Go 客户端为仅保存当前环境的 `%APPDATA%\ml-go-preview\config.json`），再运行 `ml auth status` 检查 `status=valid`、`profile` 与当前环境一致且 `businessId` 有效。路径不符或配置缺失时停止。详细字段、Windows shell 调用及故障处理见 [session.md](references/session.md)。
- **上下文复用与切换**：共用同一套本地 CLI 状态的聊天共享当前环境和已选业务。未指定租户或团队时，使用 CLI 执行时的当前选择；用户指定业务时，先用 `ml business show` 核对。切换环境用 `ml env use NAME` 后重新运行上述两条命令确认；长任务前查 `auth status` 剩余有效期。

## 调用与结果准则

- **命令与参数**：以已安装 CLI 为准（`ml tree` 查可用命令，`ml tree --all` 查全部命令与限制标记，不确定时查 `--help`）。优先使用命令支持的 JSON 输出（详见 [命令速查](references/commands.md)），检查退出码和 stderr。
- **等待时限**：`exec` 和 Notebook 按 `--startup-timeout` + `--timeout` 再加至少 60 秒；上传按 `--timeout` 留余量；`login` 和 `business refresh` 需用户操作 Edge，至少预留 10 分钟。
- **定位与输出**：有准确 ID 直接使用，否则用最窄条件定位；任务、作业、模型、模板、Pod 等 ID 不互换；列表默认分页，第一页不代表全部。本地导出先核对路径（训练配置、日志、算法仓下载要求父目录已存在），不覆盖同名文件或代码。
- **回复要求**：说明环境、业务、目标 ID、实际命令及可观察结果；带时区时间换算为北京时间 `YYYY-MM-DD HH:mm:ss`；模板详情、日志和程序输出可能含 Secret，仅提取必要字段。

## 按任务读取参考

按任务按需读取对应参考，不预先通读全部：

| 任务 | 文件 |
| --- | --- |
| 会话预检、登录、业务选择、Windows shell、故障处理 | [session.md](references/session.md) |
| 全部命令、确认提示与副作用速查 | [commands.md](references/commands.md) |
| 训练任务、样本任务及执行周期与记录、离线实验、算法仓、训练看板 | [training.md](references/training.md) |
| 模型查询与溯源、资源模板、部署模板、模型部署 | [deployment.md](references/deployment.md) |
| 服务与主机查询、样例报文测试及服务日志 | [services.md](references/services.md) |
| 数据集目录文件、特征任务详情及执行日志、特征集与 CSV 导出、质量监控及装配查询 | [data.md](references/data.md) |
| Web Studio、Jupyter 文件、exec、Notebook | [jupyter.md](references/jupyter.md) |
