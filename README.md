# WiseRec CLI (`platform-cli`)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/mossexplore/platform-cli)](https://github.com/mossexplore/platform-cli/releases/latest)

面向 **WiseRec 机器学习/深度学习平台**的命令行工具（`ml`）及配套企业级权限治理套件，用于在终端中完成算法管理、训练任务、分布式训练、数据集管理、在线推理服务部署、资源监控与 Jupyter 远程开发。

> [!IMPORTANT]
> **Python CLI 已废弃，后续维护集中在 Go CLI。** `cli-python/` 仅保留作历史参考。新用户请参阅 [Go 客户端构建与安装说明](cli-go/README.md)。

> [!NOTE]
> **平台依赖与运行前提**
> - 本项目为 **WiseRec 平台**配套客户端与治理套件，使用业务命令前需具备可访问的 WiseRec 平台环境与账号。
> - `ml login` 默认通过浏览器完成登录；Windows 交互式登录依赖 **Microsoft Edge**（或按环境配置使用服务端登录方式）。
> - 若暂未接入真实平台，可使用仓库内 `devtools/mock-platform` 搭配 `access-service` 体验合成业务数据，详见 [CLI 演示环境使用指南](docs/guides/CLI演示环境使用指南.md)。

---

## 核心特性

- **全流程平台 CLI（`ml`）**：覆盖环境与租户切换、算法创建/克隆、单机与分布式训练、执行实例与角色日志归档下载、数据集管理、模型评估、推理服务部署、容器监控及交互式 Jupyter 会话管理。
- **集中式权限治理（`access-service`，可选）**：提供基于 FastAPI + MySQL 的独立权限管理服务，支持人员/环境授权、到期控制、多环境版本准入策略、环境禁用命令清单（如禁止特定子命令组）与调用审计看板。
- **AI Agent 技能集成（`agent-service`，可选）**：支持 OpenCode 等 AI Agent 调用 `ml` 命令完成平台操作，并提供 `mlops-agent` CLI 与统一管理流程。
- **权限通知助手（`permission-notifier`，可选）**：面向管理员的桌面通知服务与审批提醒客户端。
- **本地命令历史**：支持 `ml history` 查看近期命令、`ml history clear` 清理历史，可设置 `ML_HISTORY=0` 关闭自动记录。

---

## 架构概览

```mermaid
flowchart LR
    User["开发者 / 运维"] -->|"ml 命令"| CLI["wiserec-cli (ml)"]
    Agent["AI Agent / OpenCode"] -->|"Agent Skill"| AgentSvc["agent-service (mlops-agent)"]
    AgentSvc -->|"调用"| CLI

    CLI -->|"权限校验与调用上报 (可选)"| Access["access-service (FastAPI)"]
    Access -->|"读写授权与审计"| DB[("MySQL")]
    Access -->|"待办提醒"| Notifier["permission-notifier"]

    CLI -->|"HTTPS / API & 浏览器登录"| Platform["WiseRec 平台 API"]
```

---

## 快速开始

### 1. 安装 CLI

#### Go 客户端（Windows x64）

终端用户可用 MSI 注册 `ml` 和 Agent Skill，开发人员可解压便携 ZIP 直接运行 `ml.exe`。参阅 [Go 构建与安装说明](cli-go/README.md)。

#### Python 客户端（已废弃）

DeepSeek Harness 使用[独立 Windows Desktop 插件](dsh-plugin/wiserec-cli/README.md)。插件支持 CLI 保活，完整包还可连接[内网遥测网关](telemetry-gateway/README.md)上报会话指标。保活要求 CLI 构建支持 `dsh-keepalive-v1`。

Python Wheel 及 Windows 联网、离线安装包见 [历史发布](https://github.com/mossexplore/platform-cli/releases)。已有安装的说明见 [Python CLI 历史安装文档](cli-python/scripts/windows/INSTALL.md)。

### 2. 登录与环境初始化

```bash
# 查看或切换平台环境（例如 dev / prod 等已配置环境）
ml env list
ml env use <ENV_NAME>

# 登录平台账号
ml login

# 选择当前业务空间 / 租户
ml business list
ml business use --tenant <TENANT_ID>

# 查看当前上下文与权限状态
ml context
ml access status
```

更多命令参数与完整示例请参阅 [WiseRec CLI 使用手册](docs/guides/WiseRec%20CLI%20使用手册.md)。

---

## 仓库组件与版本管理

本仓库采用统一版本清单 [`versions.toml`](versions.toml) 管理以下五个独立组件（正式交付版本与附件清单以 [GitHub Releases](https://github.com/mossexplore/platform-cli/releases) 为准）：

| 组件 | 目录 | 当前源码版本 | 说明 | 文档入口 |
| --- | --- | --- | --- | --- |
| **WiseRec CLI（Go）** | `cli-go/` | `1.1.1` | 当前维护的命令行工具（`ml`），提供 Windows x64 便携 ZIP 和每用户 MSI | [构建与安装](cli-go/README.md) |
| **WiseRec CLI（Python，已废弃）** | `cli-python/` | `1.0.9.6` | 只读历史实现 | [历史安装文档](cli-python/scripts/windows/INSTALL.md) |
| **权限管理系统** | `access-service/` | `1.0.9.1` | 授权、版本准入与审计管理台 | [README](access-service/README.md) · [Docker 部署指南](docs/deployment/权限管理系统Docker安装部署与调试指南.md) |
| **Agent 服务** | `agent-service/` | `1.0.9.1` | AI Agent 集成与部署工具 | [README](agent-service/README.md) · [配置示例](agent-service/config.example.json) |
| **权限通知助手** | `permission-notifier/` | `1.0.9.1` | 权限申请桌面通知客户端 | [README](permission-notifier/README.md) |

> 维护者更新 `versions.toml` 后，需运行 `python scripts/sync_versions.py` 同步派生文件，并通过 `python scripts/sync_versions.py --check` 校验一致性，详见 [版本号管理说明](docs/maintenance/版本号管理说明.md)。

---

## 配置与安全说明

- **配置目录**：两个客户端分别保存状态。Windows 上 Python 使用 `%APPDATA%\ml`，Go 使用 `%APPDATA%\ml-go-preview`，其中 `config.json` 只保存当前环境，部署配置随 Go 程序分发。
- **环境与认证信息**：登录状态、Token 与当前选定的业务空间保存在本地配置目录中，请勿将真实配置文件、密钥或 `service.env` 提交到版本库。
- **权限与命令限制**：当接入 `access-service` 后，管理员可按环境配置版本准入规则与禁用命令列表，CLI 会在执行对应命令前自动校验并提示。

---

## 部署权限管理系统（可选）

`access-service` 提供离线容器镜像与标准化 Docker 部署方案，默认搭配外部 **MySQL** 运行。当前源码要求数据库结构版本为 **Schema 15**。

- **1.1.1 下载**：从 [v1.1.1 Release](https://github.com/mossexplore/platform-cli/releases/tag/v1.1.1) 获取 Go CLI 的 Windows x64 MSI 和 ZIP、权限系统和 DSH 遥测网关的 Linux amd64 镜像。历史附件可在对应 Release 下载。
- **首次部署**：下载权限系统镜像后，按 [权限管理系统 Docker 安装部署与调试指南](docs/deployment/权限管理系统Docker安装部署与调试指南.md) 完成建库、初始化与启动。
- **已有环境升级**：根据目标产物选择适用的迁移要求，先停写备份并显式迁移，再切换服务。详见 [权限服务源码及数据库结构说明](access-service/README.md)。
- **运维与发布**：参见 [Linux 部署与运维手册](docs/deployment/权限管理系统Linux部署与运维手册.md) 与 [Docker 部署与发布指南](docs/deployment/权限管理系统Docker部署与发布指南.md)。

---

## 文档索引

按用途浏览全部文档，见 [WiseRec 文档索引](docs/README.md)。

- **用户与开发文档**
  - [WiseRec CLI 使用手册](docs/guides/WiseRec%20CLI%20使用手册.md)
  - [CLI 使用与维护说明](docs/guides/CLI使用与维护说明.md)
  - [Jupyter 本地开发指南](docs/Jupyter本地开发指南.md)
  - [CLI 演示环境使用指南](docs/guides/CLI演示环境使用指南.md)
- **版本与发布说明**
  - [版本号管理说明](docs/maintenance/版本号管理说明.md)
  - 近期变更：[1.1.1](docs/releases/RELEASE_NOTES_1.1.1.md) · [1.0.9.6](docs/releases/RELEASE_NOTES_1.0.9.6.md) · [1.0.9.5](docs/releases/RELEASE_NOTES_1.0.9.5.md)

---

## 问题反馈与开源协议

- **问题反馈**：如遇使用问题或有功能建议，欢迎前往 [GitHub Issues](https://github.com/mossexplore/platform-cli/issues) 提交反馈。
- **开源协议**：本项目基于 [MIT License](LICENSE) 开源。
