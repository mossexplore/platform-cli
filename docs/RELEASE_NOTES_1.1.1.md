# v1.1.1 — Go CLI、权限管理系统与 DSH 遥测网关

## 权限管理系统

- 一条版本策略可以应用于多个指定环境。策略列表支持展开较长的环境清单，预览、实际准入和操作审计使用同一适用范围。
- 环境管理新增禁止命令数。禁止命令支持按完整父命令匹配子命令。Go CLI 脱敏后的完整命令可使用 MySQL `LONGTEXT` 保存。
- 从上一正式版 `v1.0.9.1` 升级需将数据库结构从 13 显式迁至 15。先做恢复演练和停写备份，再执行迁移。保留原配置和管理员。回滚需恢复最终备份。下载附件 `Docker-upgrade-1.1.1.md` 查看完整步骤。

## Go CLI

- Windows x64 提供 MSI 和便携 ZIP。Go 客户端覆盖平台环境和业务切换、训练实例与日志检索、Jupyter 文件与执行操作等，以随包命令参考为准。
- 支持按租户 ID 选择业务，并在重新登录时恢复仍有效的上次业务。普通终端使用后台保活，DeepSeek Harness 宿主需另装兼容插件才能自动调度。
- MSI 在 Windows 当前用户范围安装。旧版 Python CLI 使用独立配置及登录数据，切换后请在 Go 客户端重新确认环境与登录。公开附件内置仓库的示例环境配置；实际内网部署使用已获准分发的配置重新构建。安装无需在线下载 Python 或 Go。浏览器登录通常依赖 Windows 上的 Microsoft Edge。

## DSH 遥测网关

- 提供 Linux amd64 离线镜像，运行时健康接口报告 `1.1.1`。接收 OTLP HTTP/JSON，按来源、环境与正文策略过滤和脱敏后转发至 Langfuse v4。
- 使用现有 Langfuse 和内网 HTTPS 入口。网关包包含镜像与配置示例，DSH Desktop 插件按独立版本另行分发。

## 附件与校验

| 附件 | 用途 |
| --- | --- |
| `wiserec-cli-1.1.1-windows-x64.msi`、`wiserec-cli-1.1.1-windows-x64.zip` | Windows x64 安装与便携运行 |
| `cli-access-1.1.1-linux-amd64.tar.gz` | Linux x86_64 权限系统，需要外部 MySQL 8.x |
| `wiserec-telemetry-gateway-1.1.1-linux-amd64.tar.gz` | Linux x86_64 DSH 遥测网关，需要现有 Langfuse v4 |
| `CLI-install.md`、`CLI-reference.md` | 安装与命令手册 |
| `README.md`、`Docker-runbook.md`、`Docker-upgrade-1.1.1.md`、`service.env.example` | 权限系统离线导入、配置、部署和迁移 |
| `Gateway-runbook.md`、`gateway.env.example` | 网关导入与配置 |
| `manifest.json`、`SHA256SUMS` | 来源、组件版本、镜像身份及文件校验 |

发布门禁包括 Windows MSI 生命周期和便携包、Go 1.1.0 来源提交升级验证、权限系统 MySQL 迁移与功能测试、网关过滤与日志测试、两个镜像的 Docker 导入往返和草稿附件复核。真实业务、Edge 登录、DSH Desktop 长时运行及真实 Langfuse 联调需在部署环境验收。发布附件不触发生产部署。
