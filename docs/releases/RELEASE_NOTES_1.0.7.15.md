# CLI 1.0.7.15 — OpenCode skill 共享目录

本次为源码更新，尚未正式发布。相较 CLI 源码 1.0.7.14，仅调整 OpenCode 的 skill 安装位置；正式下载入口保持不变。仅递增 CLI，其他组件及 Agent 已验证 CLI 搭配版本不变。

## 安装变化

- 官方 Windows 安装器将 `wiserec-platform` 和 `wiserec-platform-detailed` 安装到当前用户的 `%USERPROFILE%\.agents\skills\`，供支持该共享目录的 Agent 发现。
- OpenCode 的 `/ml`、`/ml-lab` command 继续位于其配置目录的 `commands/` 下；`OPENCODE_CONFIG_DIR` 仅改变 command 配置根目录，不改变共享 skill 路径。
- codeagent 的两套 skill 和两个 command 继续位于 `%USERPROFILE%\.cac\` 下，安装行为不变。
- 新资源安装并校验成功后，仅清理当前 OpenCode 配置目录中的两套同名旧 skill，保留其他资源；共享安装失败时不清理旧 skill。以前使用过的其他配置目录中的旧副本需自行清理。
- 同版本重装继续完整替换受管理资源；个人修改应提前另存。直接 pip 安装 Wheel 仍不会自动安装 Agent 资源。支持共享目录的 Agent 需重新打开会话，并具备调用 CLI 的终端权限。

## 兼容性与交付范围

本次无新增 CLI 命令、接口或数据库结构变化。Windows 联网安装要求 Python 3.9+；离线目标仍为 Windows x64 / Python 3.12，CLI 离线包不包含 Python 或 Edge 本体。未执行正式发布或生产部署，未替换已有 Release 附件和镜像。

## 验证范围

Python 3.12 本地验证：CLI 1359 项通过、12 项跳过，另有 212 个子测试通过；权限服务 261 项通过、1 项跳过；Node 时间预设 3 项通过。安装专项 21 项通过，覆盖默认和自定义 OpenCode command 目录、共享 skill 路径、旧副本清理、同版本重装、个人资源保留、安装失败和符号链接保护，以及 codeagent 路径保持不变。

临时 Wheel 元数据、包内版本与独立安装后的 `ml --version` 均为 1.0.7.15。使用真实 Wheel 内的资源，在临时用户目录执行安装及 Windows 验证脚本内的 Python 校验逻辑通过；包隔离、版本同步、手册 36 章结构及无具体版本号检查、差异检查通过。

未在真实 Windows Agent 环境运行 PowerShell 安装器或联调；Windows 安装验证脚本已同步新路径。未构建正式 Windows 附件或执行正式发布。
