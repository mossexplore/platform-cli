# CLI 1.0.7.11 — 详细 skill 与 /ml-lab

本次为 CLI 源码和安装资源更新，尚未执行正式发布。相较 CLI 1.0.7.10，Windows 安装流程增加详细测试 skill 和 `/ml-lab` 入口；现有 `/ml` 继续加载简洁版 skill。权限管理系统、通知助手及数据库结构不在本次变更范围。

## 能力与使用前提

- `/ml-lab` 加载 `wiserec-platform-detailed`，按需读取 96 个 CLI 命令的参数、边界、响应和错误说明。
- 两套 skill 与两个 command 同时安装到 OpenCode 和 codeagent 配置目录，保留详细资料的多级引用。
- lab 表示说明仍在测试，不是业务沙箱；操作仍使用已有 ml 命令和用户的当前环境、认证及业务权限。
- 需要允许 Agent 加载 skill、调用终端工具。直接 pip 安装 Wheel 不自动执行 Agent 资源安装阶段。

## 安装与兼容性

CLI Wheel 包元数据与运行版本均应为 1.0.7.11。Windows 联网包沿用 Python 3；离线包目标沿用 Windows x64 / Python 3.12。CLI 离线包不包含 Python 或 Edge 本体。本次没有发布新的下载附件，README 的正式下载入口保持不变。

安装器完整替换两个受管理 skill 目录及 commands/ml.md、commands/ml-lab.md，同版本重装也会清理废弃参考。其他个人 skill、command 和 Agent 配置不受影响。已有同名详细 skill 的自定义修改应提前另存。

损坏的资源包在替换前报错；资源安装失败不影响 CLI 主程序使用，可解决问题后重跑官方安装器。降级到旧安装器可能留下实验入口和详细 skill，需要按安装说明单独清理。

skill-lab/validation 仅用于仓库维护，不进入 Wheel、源码包或 Windows 安装资源。

## 验证范围

Python 3.12 本地验证：CLI 1168 项通过、12 项跳过；权限服务 259 项通过、1 项跳过；Node 时间预设 3 项通过。Wheel、源码包及从源码包重建的 Wheel 均含完整 110 个 Agent 资源，validation 未进入包；隔离安装后的 ml --version 与包元数据均为 1.0.7.11。两个隔离 Agent 目录的资源与源码逐字节一致。用户手册 32 章四类小节结构、无版本信息和实际 CLI 命令树检查通过。未执行真实平台/Jupyter 联调、Agent 双入口端到端会话测试或 Windows 联网/离线安装实测；本地构建和自动化测试不代表正式发布工作流完成。
