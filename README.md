# WiseRec CLI 与权限管理系统

面向 WiseRec 平台的命令行工具，以及配套的 Web 权限管理系统。

| 组件 | 谁使用 | 主要功能 |
| --- | --- | --- |
| **CLI（`ml`）** | 平台使用人员 | 登录和切换环境、选择业务、查询模型信息，以及查询与操作训练任务、算法仓、特征集等平台资源 |
| **权限管理系统** | 管理员 | 管理人员和环境、授予或撤销访问权限、设置有效期、查看调用记录和操作审计 |

启用权限校验后，CLI 在执行业务命令前向权限系统检查当前账号和环境的授权，通过后再调用平台接口。权限系统独立部署，数据保存在 MySQL；客户端校验不替代平台自身的权限控制。

四个产品的版本统一记录在根目录 [`versions.toml`](versions.toml)，CLI、权限管理系统、Agent 和权限通知助手本次发布目标均为 **1.0.9.1**，以后可以独立递增。运行 `python scripts/sync_versions.py` 同步，再运行 `python scripts/sync_versions.py --check` 检查。各产品读取自身包内版本，详见 [版本号管理说明](docs/版本号管理说明.md)。

本次发布增加 MLOps 管理台适配、Plog 下载与环境禁止命令管理，见 [发布说明](docs/RELEASE_NOTES_1.0.9.1.md)。权限管理系统数据库要求结构 **13**；现有结构 12 必须按 [升级指南](docs/权限管理系统结构12升级至1.0.9.1指南.md) 备份、迁移并验收。正式交付以对应 GitHub Release 的发布状态与校验清单为准。本地开发参见 [Jupyter 本地开发指南](docs/Jupyter本地开发指南.md)。

新增本地命令历史：`ml history` 查看最近记录，`ml history clear` 清理。历史以文本保存在配置目录，最多保留 1000 条；`ml --no-history COMMAND` 可跳过本次记录。

## 下载 1.0.9.1

前往 [GitHub Release](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.9.1)，按需要下载：

| 文件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.9.1-windows-py3-online.zip` | Windows 联网安装，支持企业 Python 包源 |
| `wiserec-cli-1.0.9.1-windows-x64-py312-offline.zip` | Windows x64、Python 3.12 离线安装 |
| `wiserec_cli-1.0.9.1-py3-none-any.whl` | 通过 pip 安装 CLI，依赖另行准备 |
| `cli-access-1.0.9.1-linux-amd64.tar.gz` | Linux x86_64 权限系统 Docker 镜像 |
| `permission-notifier-1.0.9.1-windows-source.zip` | 独立本地助手源码安装包，需要 Python 3.12 和依赖下载网络 |
| `Notifier-install.md` | 助手安装、Token 绑定、配置与退出说明 |

Agent 通过 Release 的完整仓库源码附件交付，按照 [Agent 安装说明](agent-service/README.md) 安装，需自行配置模型、MySQL 和 Edge。

Release 同时提供配置示例、安装指南和 `SHA256SUMS` 校验文件。

## CLI 快速使用

1. 预装 Python 和 Microsoft Edge。联网包要求 Python 3.9+；离线包要求 Python 3.12 x64。
2. 解压 Windows 安装包，运行 `install.cmd`。
3. 重新打开终端，选择已配置的环境并登录：

```bash
ml --version
ml env list
ml env use dev
ml login
ml business use
ml --help
```

将 `dev` 替换为实际环境名称。安装器使用独立虚拟环境，无需管理员权限；离线包包含 Python 依赖，不包含 Python 和 Edge 本体。

完整命令和参数见 [WiseRec CLI 使用手册](docs/WiseRec%20CLI%20使用手册.md)，企业包源与安装问题见 [Windows 安装说明](scripts/windows/INSTALL.md)。

## 部署权限管理系统

服务支持 Docker 部署，复用现有 MySQL 8.x。内网服务器无需拉取镜像，可下载 Release 中的离线镜像后导入：

```bash
docker load -i cli-access-1.0.9.1-linux-amd64.tar.gz
```

接着按 [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md) 完成配置和启动：

- 配置保存在宿主机 `/opt/cli-access-config/service.env`，只读挂载到容器 `/run/cli-access`。
- 使用镜像 `cli-access:1.0.9.1` 启动，默认端口 `8008`。
- 管理页面：`http://服务器IP:8008/cli-permission`。
- 管理员添加与平台登录账号一致的人员、配置对应环境并授予访问权限。
- 修改挂载配置后执行 `docker restart cli-access`；运行日志使用 `docker logs -f cli-access`。

新数据库需要初始化并创建管理员；从上一正式版本 1.0.7.7 升级结构仍为 12，无需迁移；先恢复演练、停写并完成最终备份，再切换镜像验收，不重新创建已有管理员。完整步骤与回滚限制见 [升级指南](docs/权限管理系统1.0.7.7升级至1.0.9.1指南.md)。

## CLI 接入权限系统

**CLI 默认开启权限校验。** 部署好服务后，在 CLI 使用的 `config.json` 中填写权限服务地址，保留其他配置：

```json
{
  "access_control": {
    "url": "http://服务器IP:8008/cli-permission",
    "timeout_seconds": 15
  }
}
```

替换为客户端实际可访问的地址。地址为空或未配置时，业务调用会报配置错误并停止。确需关闭时，在 `access_control` 中显式设置 `"enable": false`；默认配置无需写 `enable`。完成登录和业务选择后，执行 `ml access status` 验证授权。

当前源码的安装器在每次安装、同版本重装和升级时强制覆盖用户默认 `config.json`，仅保留新包中仍可用的本地 `current`，无法恢复时采用包内默认 `current`，其余字段全部采用安装包内容。此调整需通过后续安装包交付，已发布附件保持原样。配置位置、覆盖规则和授权排查见 [WiseRec CLI 使用手册](docs/WiseRec%20CLI%20使用手册.md)。

## 更多文档

- [CLI 使用与维护说明](docs/CLI使用与维护说明.md)：核心概念、命令速查、配置、架构与故障排查。
- [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md)：安装、启停、日志和常见报错。
- [Docker 与 GitHub 发布流程](docs/权限管理系统Docker部署与发布指南.md)：镜像构建、Compose 和 HTTPS。
- [非 Docker 部署手册](docs/权限管理系统Linux部署与运维手册.md)：Linux 离线包部署与数据库准备。
- [问题反馈](https://github.com/mossexplore/platform-cli/issues)：请附版本、运行环境及复现步骤，避免上传密码或登录凭据。

## OpenCode 使用

OpenCode/codeagent 集成分两个阶段：先安装并验证 CLI，再安装正式 skill `wiserec-platform` 和 `/ml` 快捷入口。不安装 `skill-lab` 详细版。第二阶段失败时 CLI 仍可使用，修复文件权限或占用问题后重新运行安装程序。

OpenCode 的正式 skill 安装到 `~/.agents/skills/wiserec-platform`，`/ml` 位于当前 OpenCode 配置目录的 `commands/ml.md`；codeagent 使用 `~/.cac/skills/wiserec-platform` 和 `~/.cac/commands/ml.md`。`OPENCODE_CONFIG_DIR` 可指定 OpenCode 配置目录。每次安装更新正式 skill，并清理共享目录、当前 OpenCode 目录和 codeagent 目录中的历史 `wiserec-platform-detailed` 与 `commands/ml-lab.md`，其他资源保留。

完成后重新打开 Agent 会话，输入 `/ml 查询当前业务下的模型` 使用正式 skill；不带需求时可查看上下文和用法。直接通过 pip 安装 Wheel 不自动安装 Agent 资源，自动安装入口为官方 Windows 安装包。

历史安装若使用过其他自定义 OpenCode 配置目录，需在该目录重新运行安装程序才能清理对应旧副本。


## Windows 本地代码打包并安装

在仓库根目录的 CMD 中运行：

```bat
scripts\build-install.cmd
```

脚本使用当前本地工作区源码，依次调用现有的联网打包和安装脚本，不自动拉取远程代码。先更新本地代码再执行即可安装所需源码；未提交的本地修改也会参与打包。需要 Windows PowerShell、Python、联网包源及现有安装脚本要求的 Microsoft Edge。默认沿用当前用户的 CLI 安装目录，支持同版本重新安装，安装后重新打开终端使用 `ml`。

每次产物保存在 `release\local-builds` 下的独立目录，打包失败不会继续安装，不会选择旧包。构建包属于本地验证产物，不是 GitHub 正式发行版。安装过程同时沿用原安装器的 OpenCode 资源安装流程，具体结果见终端输出。

可选参数：

```bat
scripts\build-install.cmd -IndexUrl https://PACKAGE_HOST/simple
scripts\build-install.cmd -InstallDirectory "D:\Tools\WiseRecCLI"
scripts\build-install.cmd -OutputDirectory "D:\Builds\WiseRecCLI"
```

`-Force` 会按原安装器规则重建安装虚拟环境，日常同版本覆盖无需指定；`-SkipEdgeCheck` 仅跳过安装时的 Edge 检查。打包和安装阶段共用 `-IndexUrl`；企业证书等 pip 环境配置继续沿用现有脚本行为。执行失败时返回非零退出码。

## 本地 Agent 工作台

新增独立的 [WiseRec Agent 本地工作台](agent-service/README.md)，通过环境登录与对话查询平台数据。配置模板位于 [agent-service/config.example.json](agent-service/config.example.json)。当前需完成真实平台、MySQL、模型及 Windows 联调后再验收放行；未纳入现有 CLI 正式发布附件。

仓库根目录 `config.example.json` 仅为样例；制作安装包前，必须在同一目录复制为 `config.json` 并填写实际环境。构建仅使用根目录正式 `config.json`，缺失时直接报错，不自动回退至样例。Wheel、源码分发包及 Windows 安装包均携带这份配置；安装时据此覆盖用户配置，并按上述规则保留或回退 `current`。真实根目录配置不提交到 Git。
