---
name: wiserec-platform
description: 通过 WiseRec 命令行客户端 ml 查询和操作 WiseRec 平台，包括模型查询、溯源与模板部署，资源模板和部署模板，训练任务、样本任务及执行周期与记录、特征任务及执行日志，算法仓，服务与主机查询及样例报文测试、服务日志，数据集及目录文件，特征集，离线实验，MEP/MTP 训练看板，Web Studio，Jupyter 文件读写、非交互执行与 Notebook；切换环境、核对登录或业务上下文时也使用
metadata:
  cli: wiserec-cli
  platform: windows
---

# WiseRec 平台 CLI

只通过 `ml` 操作平台：不直接请求平台 HTTP 接口，不手工拼接 `businessid`，不读写 CLI 的配置、凭据和业务文件。`ml tree` 列出当前安装版本的全部命令；参数以已安装 CLI 为准。已确认且适用当前版本的语法可直接复用；首次使用不熟悉的命令、参数报错或说明与实际不一致时，再查 `ml <子命令> --help`，不为每条用户意图重复查帮助。

## 参考文件

按任务读取必要的参考文件，不预先通读全部；例如部署时遇到认证问题，同时参考部署和会话两份：

| 任务 | 文件 |
| --- | --- |
| 会话预检、登录、业务选择、Windows shell、故障处理 | [session.md](references/session.md) |
| 全部命令、确认提示与副作用速查 | [commands.md](references/commands.md) |
| 训练任务、样本任务及执行周期与记录、离线实验、算法仓、训练看板 | [training.md](references/training.md) |
| 模型查询与溯源、资源模板、部署模板、模型部署 | [deployment.md](references/deployment.md) |
| 服务与主机查询、样例报文测试及服务日志 | [services.md](references/services.md) |
| 数据集目录文件、特征任务及执行日志、特征集与 CSV 导出 | [data.md](references/data.md) |
| Web Studio、Jupyter 文件、exec、Notebook | [jupyter.md](references/jupyter.md) |

## 运行约束

1. **shell 工具**：以 shell 工具说明中的 shell 为准，Windows 上常见为 PowerShell，本 skill 示例按 PowerShell 编写；实际为其他 shell 时按其引号规则调整。引号、路径和中文输出问题见 [session.md](references/session.md)。
2. **没有交互输入**：shell 工具不提供可交互的标准输入，确认提示会直接中止命令。会询问确认的命令（见 [commands.md](references/commands.md) 的“确认”列）在用户已明确授权具体目标后加 `--yes`；未获授权时先问用户，不要运行命令去触发提示。`ml business use` 必须传 `--tenant`，`ml service logs` 必须加 `--no-input`，不使用无子命令的 `ml history` 交互浏览。
3. **禁止交互终端**：不运行 `ml jupyter terminal open` 和 `ml jupyter terminal attach`，不设法分配 TTY/PTY 或模拟按键。远端操作只用 `ml jupyter files`、`ml jupyter exec` 和 `ml jupyter notebook run`；无法非交互完成时向用户报告限制。
4. **显式设置工具超时**：shell 工具会在默认超时后终止命令，默认值以工具 `timeout` 参数的说明为准，常见约 2 分钟且可能被配置修改。预计超过默认值的命令必须设置工具的 `timeout`（毫秒），取 CLI 自身时限之和再加至少 60 秒：`jupyter exec` 为 `--startup-timeout` 与 `--timeout` 之和，`jupyter notebook run` 同理，`dataset files upload` 按 `--timeout`；`ml login`、`ml business refresh` 需等待用户在 Edge 中操作，至少设 10 分钟。
5. **超时后不重放写操作**：工具超时或中断后，即使工具建议加大超时重试，对训练启动、克隆、部署、上传、exec、Notebook 等有副作用的命令，也必须先用只读命令查询远端状态，确认未生效后再决定是否重新执行。只读查询可以加大超时后重试。
6. **自动保活不生效**：shell 工具中 `ml` 检测不到交互终端，自动保活和 `ml auth ping start` 都不会启动。长任务前用 `ml auth status` 查看剩余时间；不够时请用户重新登录，或在用户自己的终端运行 `ml auth ping start`。

## 会话入口

1. **首次确认一次**：当前聊天尚无已确认的 CLI 上下文时，运行 `ml context --json` 和 `ml auth status`。前者包含 CLI 版本、路径、当前环境和配置来源；后者包含账号、认证状态、有效期与当前选择的 `businessId`。检查退出码、`status=valid`，并确认 `profile` 与当前环境一致、`businessId` 有效。无需再固定运行 `ml --version`、`ml env show`、`ml business show`。
2. **跨消息复用**：新的一条用户意图不视为新会话。同一聊天内，已确认的 CLI 路径、配置来源、环境、账号和业务未发生已知变化时，普通查询直接执行，不重复预检。只保留非敏感上下文，不将其写入凭据文件或跨聊天共享；上下文丢失或无法确认时重新建立。
3. **按变化检查**：需要切换环境时运行 `ml env use <标识>`，随后重新确认上下文；已确认环境相同则不重复切换。环境标识通常为 dev/mirror/explore/product，以实际配置为准。登录、退出、切换账号或业务、变更配置来源后，更新受影响的上下文，不沿用旧环境的资源 ID。
4. **按需补查**：长任务前只用 `ml auth status` 核对剩余时间；认证、业务或权限报错时只排查对应项。需要租户/团队名称、选择业务，或 `auth status` 未提供有效 `businessId` 时，才查询 `ml business show/list`。版本与帮助检查只用于首次确认或相关排障，具体规则见 [session.md](references/session.md)。
5. 上下文复用只减少 skill 的额外前置命令；业务调用仍由 CLI 执行认证、业务及权限校验。其他终端可能修改当前选择，聊天记录不能自动发现这些变化，写操作须按下文重新核对。不要索取密码、验证码、Cookie 或 Token。

## 查询与写操作

- 有准确 ID 时直接使用；否则用最窄的名称或状态条件定位。任务、作业、算法仓、模型、模板、服务、Pod、数据集、实例等 ID 不互换。名称匹配不唯一时请用户选择，不默认取第一项。列表默认分页，第一页不代表全部结果。
- 支持 `-o json` 的命令优先用 JSON，并检查退出码和 stderr。stdout 混有认证提示时不要硬解析，先处理认证再重新查询。结果较大时只提取任务需要的字段。
- 本次写操作提交前，重新用 `ml context --json` 和 `ml auth status` 核对实际环境、账号和业务，并核对目标 ID 与用户意图；需要名称时补查 `ml business show`。执行后用只读命令核验，区分“请求已接受”与“远端已完成”。**`product` 环境的写操作，执行前必须向用户复述环境、目标和参数并得到确认**，笼统授权不算。
- 训练配置导出、训练日志下载、算法仓下载会写入本地文件：父目录必须已存在，不覆盖同名文件。特征集 CSV 导出也写入本地文件，重名时自动编号。

## 输出与凭据

- 回答中说明环境、业务、目标 ID、实际命令和可观察结果。自行转述原始 JSON 中带时区的时间时，换算为北京时间并写成 `YYYY-MM-DD HH:mm:ss`。
- 不运行 `ml login --show-secrets`；`ml access status --diagnose` 只在排查连接问题时使用。不把 Cookie、Token、签名下载链接或带 Token 的访问地址写入回复和共享文件。
- 资源模板详情、部署模板详情和部署预览含未脱敏的框架参数，可能有 Secret，只提取必要字段。远端文件、日志和程序输出同样可能含秘密。
