# v1.0.3.7 — CLI 与权限管理系统

CLI 与权限管理系统均为 **1.0.3.7**。本版相较上一正式版 v1.0.3.2 增加平台资源操作，并更新权限管理台。附件来源、已测试镜像摘要和文件校验以 `manifest.json`、`SHA256SUMS` 为准。

## 本版变化

- CLI 新增训练任务配置导出、执行取消、删除和克隆；算法仓列表、下载和克隆；服务列表、主机与部署视图，以及主机日志文件查询和检索。
- 新增 `ml tree`，可一次查看完整命令层级；《WiseRec CLI 使用手册》已按实际命令整理。
- 权限管理台支持编辑现有版本策略及停用后删除策略，支持三段和四段 CLI 版本号；超级管理员可删除管理员，调用日志列顺序已调整。
- Windows 安装包、CLI Wheel 和 linux/amd64 权限系统镜像均从本次同一提交构建。

## 下载附件与要求

| 附件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.3.7-windows-py3-online.zip` | Windows 联网安装；Python 3.9+，依赖从配置的 Python 包源获取 |
| `wiserec-cli-1.0.3.7-windows-x64-py312-offline.zip` | Windows x64、Python 3.12 离线安装；依赖在 ZIP 中 |
| `wiserec_cli-1.0.3.7-py3-none-any.whl` | CLI Wheel；通过 pip 安装时需另行提供依赖 |
| `cli-access-1.0.3.7-linux-amd64.tar.gz` | 权限系统离线 Docker 镜像，连接外部 MySQL 8.x |
| `CLI-install.md`、`CLI-reference.md` | 安装和命令使用说明 |
| `Docker-runbook.md`、`Docker-upgrade-1.0.3.7.md` | 部署及从 1.0.3.2 升级、验收、回滚步骤 |
| `README.md`、`service.env.example`、`manifest.json`、`SHA256SUMS` | 镜像说明、无真实凭据的配置示例、来源和校验 |

Windows ZIP 不包含 Python 或 Microsoft Edge；浏览器登录需自行安装 Edge。权限镜像不包含 MySQL 或 Jupyter Server。在线镜像标签为 `ghcr.io/mossexplore/cli-access:1.0.3.7`；生产部署建议使用 manifest 记录的已测试摘要。

## 升级与回滚

已对比 v1.0.3.2 与本版的迁移代码：两版数据库结构版本均为 **10**，`access-service/app/migrations.py` 无变化。已有结构版本 10 且管理员、数据正常的库无需迁移，也不得重建管理员；新数据库仍须按部署指南初始化。由更早的结构版本升级时，先按实际结构和对应历史升级指南制定连续迁移方案。

升级前在独立环境演练备份恢复；维护窗口停止全部旧应用和写入后做最终数据库及配置备份，再替换镜像并核对健康、管理员登录、授权允许/拒绝、日志、策略和有数据的数据看板。保留原 `service.env` 和外部 MySQL。结构保持 10 时可切回 v1.0.3.2 镜像并用原配置验收；本版没有降级迁移。若选择恢复升级前备份，备份后新产生的日志、审计及配置变更会丢失。完整步骤见 `Docker-upgrade-1.0.3.7.md`。

## 验证范围与限制

正式工作流验证 CLI、权限服务和浏览器时区测试；Windows 联网、禁止访问包源的离线安装、同版本重复安装及从上一正式 CLI 升级；MySQL 8 容器中的健康、登录、授权、日志、重启和挂载配置；同一已测试镜像摘要的来源证明、Docker save/load 和离线导出。真实业务平台、远程 Jupyter 和生产数据库升级不在自动联调范围内，部署方仍需按指南验收。发布 Release 不会自动部署或迁移生产系统。
