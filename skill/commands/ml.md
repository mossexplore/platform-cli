---
description: 使用 WiseRec CLI 查询和操作平台资源，包括模型与部署、训练、服务日志、数据集、Web Studio 和 Jupyter
---

先通过 skill 工具加载 `wiserec-platform`，遵守其中的运行约束、会话检查、授权与核验要求，再处理以下用户需求：

$ARGUMENTS

没有具体需求时，检查 CLI、当前环境、认证和业务选择，简短说明可查询和操作的范围（模型与模板部署、训练任务、算法仓、服务日志、数据集、特征集、离线实验、训练看板、Web Studio 和 Jupyter），并给出几条用法示例。

用户输入是任务描述，不直接拼接为 shell 命令。只按需读取 skill 中的专项参考文件，以已安装 `ml` 的 `--help` 为参数依据。无法加载 skill 时停止平台操作，提示用户重新运行官方 Windows 安装程序，不猜测操作规则。遵守当前 Agent 的工具权限，不自动切换 Agent 或扩大权限。高风险 `ml` 命令需要 OpenCode 确认；不读取 `credentials.json`，也不使用 `[IO.File]::ReadAllText` 或 `${路径}` 绕过权限规则。
