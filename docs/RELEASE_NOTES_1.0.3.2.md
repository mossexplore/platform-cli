# v1.0.3.2 — CLI 与权限管理系统

CLI 与权限管理系统均为 **1.0.3.2**。本版相较上一正式版 v1.0.3.1 重新构建 Windows 安装包、Wheel 和 linux/amd64 权限系统镜像。附件来源、已测试镜像摘要和文件校验以 `manifest.json`、`SHA256SUMS` 为准。

## 本版变化

- 新增 `ml webstudio start ENV_ID` 和 `ml webstudio stop ENV_ID`。启动请求最长等待至少 60 秒，不自动重试；两个命令使用当前环境已选业务，启动操作者取当前登录账号。
- `ml env list` 新增逐环境的 `access_status`，使用该环境已有登录信息和业务选择查询权限服务；缺少登录、业务选择、服务地址或网络故障会分别提示，不能当作已授权。
- CLI 权限检查默认开启。未配置 `access_control.url` 时，业务命令报配置错误并停止；确需关闭须显式设置 `"enable": false`。旧的 `enabled` 布尔字段仍兼容，但不能与 `enable` 同时使用。升级安装会覆盖默认 `config.json`，请先备份自定义配置并在安装后填写实际权限服务地址。
- `ml login` 成功输出的 `businessId` 与 `ml business show` 一致；租户级选择对应租户 ID，团队级选择对应团队业务 ID。
- Windows 安装器每次卸载旧 CLI 并安装本次包内 Wheel，同版本也会替换 CLI 文件；`-Force` 仍用于重建整个虚拟环境。
- Web Studio/Jupyter 连接和环境列表的业务上下文校验更严格。权限管理台数据看板将 MySQL 聚合计数统一转为整数，修复有数据时图表 JSON 序列化错误；调用日志表格适配桌面窗口高度。

## 下载附件与要求

| 附件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.3.2-windows-py3-online.zip` | Windows 联网安装；Python 3.9+，依赖从配置的 Python 包源获取 |
| `wiserec-cli-1.0.3.2-windows-x64-py312-offline.zip` | Windows x64、Python 3.12 离线安装；依赖在 ZIP 中 |
| `wiserec_cli-1.0.3.2-py3-none-any.whl` | CLI Wheel；通过 pip 安装时需另行提供依赖 |
| `cli-access-1.0.3.2-linux-amd64.tar.gz` | 权限系统离线 Docker 镜像，连接外部 MySQL 8.x |
| `CLI-install.md`、`CLI-reference.md` | 安装和命令使用说明 |
| `Docker-runbook.md`、`Docker-upgrade-1.0.3.2.md` | 部署及从 1.0.3.1 升级、验收、回滚步骤 |
| `README.md`、`service.env.example`、`manifest.json`、`SHA256SUMS` | 镜像说明、无真实凭据的配置示例、来源和校验 |

Windows ZIP 不包含 Python 或 Microsoft Edge；浏览器登录需自行安装 Edge。权限镜像不包含 MySQL 或 Jupyter Server。在线镜像标签为 `ghcr.io/mossexplore/cli-access:1.0.3.2`；生产部署建议使用 manifest 记录的已测试摘要。

## 升级与回滚

已对比 v1.0.3.1 与本版的迁移代码：两版数据库结构版本均为 **10**，`access-service/app/migrations.py` 无变化。已有结构版本 10 且管理员、数据正常的库**无需迁移**，也不得重建管理员；新数据库仍须按部署指南初始化。由更早的结构版本升级时，先按实际结构和对应历史升级指南制定连续迁移方案。

升级前在独立环境演练备份恢复；维护窗口停止全部旧应用和写入后做最终数据库及配置备份，再替换镜像并核对健康、管理员登录、授权允许/拒绝、日志及数据看板。保留原 `service.env` 和外部 MySQL。结构保持 10 时可切回 v1.0.3.1 镜像并用原配置验收；本版没有降级迁移。若选择恢复升级前备份，备份后新产生的日志、审计及配置变更会丢失，须先评估和保存。完整步骤见 `Docker-upgrade-1.0.3.2.md`。

## 验证范围与限制

正式工作流验证 CLI、权限服务和浏览器时区测试；Windows 联网、禁止访问包源的离线安装、同版本重复安装及从上一正式 CLI 升级；MySQL 8 容器中的健康、登录、授权、日志、重启和挂载配置；同一已测试镜像摘要的来源证明、Docker save/load 和离线导出。真实业务平台、远程 Jupyter 和生产数据库升级不在自动联调范围内，部署方仍需按指南验收。发布 Release 不会自动部署或迁移生产系统。
