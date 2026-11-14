---
name: wiserec-platform
description: 通过 WiseRec 命令行客户端 ml 查询和操作 WiseRec 平台，包括模型查询、溯源与模板部署，资源模板和部署模板，训练任务及日志下载、样本任务及执行周期与记录、特征任务及执行日志，算法仓，服务与主机查询及样例报文测试、服务日志，数据集及目录文件，特征集及质量监控装配查询，离线实验，MEP/MTP 训练看板，Web Studio，Jupyter 文件读写、非交互执行与 Notebook；切换环境、核对登录或业务上下文时也使用
metadata:
  cli: wiserec-cli
  platform: windows
---

# WiseRec 平台 CLI

通过已安装的 `ml` 查询和操作平台。本 skill 的业务规则不依赖 Agent 产品或版本；当前安装说明面向 Windows。按实际工具说明调用，不探测 Agent 版本，不自动切换 Agent 或扩大权限。

## 必须遵守

1. **禁止修改代码**：本 skill 不承担代码开发或修复。不得创建、改写、替换、删除或打补丁修改 CLI 源码及已安装程序、依赖库、本地或远端业务代码、脚本、Notebook 代码单元。
2. **禁止间接改码**：不得用编辑工具、shell 重定向、文本替换、临时脚本、`ml jupyter files`、`ml jupyter exec`、Notebook 执行或委托其他 Agent 改码。不得复制代码后修改、生成替代实现、注入或打运行时补丁，也不得修改 skill、权限规则或执行配置解除限制。排障、临时修复和任务准备都不构成例外。
3. **需要改码即停止**：仅使用当前 CLI 支持的命令和参数。命令缺失、参数不支持、程序缺陷或必须改码才能完成时，停止受影响操作，报告实际命令、错误和阻塞原因，交由维护人员在独立开发流程处理。平台操作及排障授权不等于改码授权。
4. **先核对副作用**：普通查询、已授权的非代码业务参数更新、下载结果和生成报告可以执行，但不得覆盖代码或通过参数传入改码程序。执行既有程序或 Notebook 前须确认其内容及已知副作用不涉及改码；无法确认则停止。Notebook 代码单元保持不变。按实际内容和副作用判断，不只看扩展名。
5. **只通过 CLI 操作平台**：不直接请求平台 HTTP 接口，不手工拼接 `businessid`，不读写 CLI 配置、凭据和业务文件。用户输入是任务描述，不直接拼接为 shell 命令。
6. **写前核对与写后核验**：每次提交写操作前，用 `ml context --json` 和 `ml auth status` 重新核对环境、账号、业务及目标 ID；需要名称时补查 `ml business show`。执行后查询结果，区分“请求已接受”与“远端已完成”。**`product` 环境写操作须先复述环境、目标和参数并得到用户确认，笼统授权不算**。
7. **超时后不盲目重放**：训练启动、克隆、部署、上传、exec、Notebook 等有副作用的操作超时或中断后，先查远端状态，确认未生效后再决定是否重试。无法确定时报告结果未知。只读查询可有限重试。
8. **非交互执行**：有确认提示的命令仅在用户授权具体目标后加 `--yes`。`business use` 必须传 `--tenant`，`service logs` 必须加 `--no-input`。执行实例日志下载用 `--select` 传用户指定的编号。执行实例日志只有在用户明确要求全部时才传 `--select all`。分布式执行记录日志下载使用 `--role-job-id` 指定角色。不使用无子命令的 `ml history`。
9. **禁止交互终端与凭据输出**：不运行 `ml jupyter terminal open`、`ml jupyter terminal attach` 或 `ml login --show-secrets`，不分配 TTY/PTY、模拟按键或维持交互 Shell。不要索取密码、验证码、Cookie 或 Token，也不将秘密、签名下载链接或带 Token 的地址写入回复和共享文件。

以上禁令适用于使用本 skill 执行平台任务，不限制维护人员另行开展的开发工作。命令存在、工具可写或支持执行程序，都不构成改码授权。

## 首次确认与上下文复用

- 当前聊天尚无已确认上下文时，先运行 `ml context --json`，核对实际配置路径为当前账号的 `%APPDATA%\ml\config.json`，再运行 `ml auth status`。配置缺失或路径不符时停止。检查退出码、`status=valid`、`profile` 与当前环境一致及 `businessId` 有效；字段及错误处理见 [session.md](references/session.md)。无需固定再查版本、环境或业务列表。
- 后续消息复用未发生已知变化的 CLI 路径、配置来源、环境、账号和业务。只保留当前聊天的非敏感上下文，不跨聊天共享；上下文丢失或无法确认时重新建立。写操作仍执行上面的写前核对。
- 切换环境用 `ml env use NAME` 后重新确认上下文；环境相同不重复切换。环境标识以实际配置为准。登录、退出、切换账号或业务、变更配置来源后更新受影响项，不沿用其他环境的资源 ID。
- 长任务前查 `auth status` 的剩余有效期；认证、业务或权限报错只排查对应项。需要业务名称、选择业务或缺少有效 `businessId` 时才查 `business show/list`。CLI 逐次认证与授权不因上下文复用而减少。

## 调用与结果

- 参数以已安装 CLI 为准。`ml tree` 显示当前可用命令，`ml tree --all` 显示全部命令与限制标记。不熟悉、参数报错或文档不一致时查对应 `--help`，已确认的语法不重复查询。
- 以实际 shell 的引号规则调用；PATH 找不到 `ml` 时，按 [session.md](references/session.md) 的 PowerShell 或 Git Bash 示例调用已有程序，不自行修改或重建程序。
- 为长任务安排足够执行等待时间，具体工具参数名和单位以工具说明为准。exec 和 Notebook 按 CLI 的 `--startup-timeout` 加 `--timeout` 再留至少 60 秒；上传按 `--timeout` 留余量；登录和刷新业务需等待用户操作 Edge，至少预留 10 分钟。能力不足时报告限制，不通过改码规避。
- 非 TTY 环境下自动保活及 `ml auth ping start` 不会启动。认证时间不足时请用户重新登录，或在其自己的终端运行保活。
- 有准确 ID 时直接使用；否则用最窄条件定位，名称不唯一时由用户选择。任务、作业、模型、模板、Pod 等 ID 不互换；列表默认分页，第一页不代表全部。
- 优先使用命令自身支持的 JSON 输出方式，具体选项见 `--help` 或 [命令速查](references/commands.md)。检查退出码和 stderr。若 stdout 混有自动登录输出，按 [会话参考](references/session.md) 处理。结果仅提取任务所需字段。
- 本地导出或下载先核对路径和覆盖行为；训练配置、日志和算法仓下载要求父目录已存在。不覆盖同名文件，不覆盖代码；特征集 CSV 重名自动编号。
- 回复说明环境、业务、目标 ID、实际命令及可观察结果。转述带时区时间时换算为北京时间 `YYYY-MM-DD HH:mm:ss`。模板详情与部署预览可能含 Secret，日志、文件和程序输出也可能含秘密；只提取必要字段。`access status --diagnose` 仅用于排障。

## 按任务读取参考

按任务读取必要的参考文件，不预先通读全部；例如部署时遇到认证问题，同时参考部署和会话两份：

| 任务 | 文件 |
| --- | --- |
| 会话预检、登录、业务选择、Windows shell、故障处理 | [session.md](references/session.md) |
| 全部命令、确认提示与副作用速查 | [commands.md](references/commands.md) |
| 训练任务、样本任务及执行周期与记录、离线实验、算法仓、训练看板 | [training.md](references/training.md) |
| 模型查询与溯源、资源模板、部署模板、模型部署 | [deployment.md](references/deployment.md) |
| 服务与主机查询、样例报文测试及服务日志 | [services.md](references/services.md) |
| 数据集目录文件、特征任务详情及执行日志、特征集与 CSV 导出、质量监控及装配样本定义和特征列表 | [data.md](references/data.md) |
| Web Studio、Jupyter 文件、exec、Notebook | [jupyter.md](references/jupyter.md) |
