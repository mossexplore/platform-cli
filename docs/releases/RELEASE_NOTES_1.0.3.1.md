# v1.0.3.1 — CLI 与权限管理系统更新

CLI 与权限管理系统均为 **1.0.3.1**。本版重新构建两个 Windows ZIP、Wheel 和权限系统镜像；源码、镜像摘要和附件校验见 `manifest.json`、`SHA256SUMS`。

## 相较 v1.0.3 的变化

- 新增“数据看板”：按时间、环境、用户、业务 ID、CLI 版本分析授权检查次数和命令分布；图表可跳转到调用日志。客户端预检查和网关检查分别记录，检查次数不等于业务执行成功次数。
- 调用日志显示人员授权档案中的当前姓名，列表密度调整为常见桌面窗口下 10 条及分页同屏；完整命令和拒绝详情保留在详情抽屉。
- 管理员账号新增独立的姓名字段，新增账号时必填；历史账号可由超级管理员补录。管理员管理与操作审计显示管理员当前姓名。
- 已停用的版本策略可由超级管理员删除；删除后从管理列表移除、不可重新启用，关联有效临时例外撤销。策略、例外和审计历史保留在数据库。
- CLI 的 Web Studio Jupyter 连接支持按实例 region 选择网关地址，并在请求前建立会话、携带网关设置的 Cookie 与 XSRF 标记；单一 `server_url` 配置仍可继续使用。
- CLI 为 `ml jupyter notebook run` 和 `ml webstudio list` 补齐 `-o` 输出格式短选项，并改进 Web Studio 连接诊断。诊断中显示的完整访问地址可能包含 token，须按凭据保护终端输出。

## 下载附件

| 附件 | 版本和用途 |
| --- | --- |
| `cli-access-1.0.3.1-linux-amd64.tar.gz` | 权限系统 1.0.3.1 离线 Docker 镜像，linux/amd64 |
| `Docker-runbook.md`、`Docker-upgrade-1.0.3.1.md` | 部署及从权限系统 1.0.3 升级的备份、迁移、验收和回滚步骤 |
| `wiserec-cli-1.0.3.1-windows-py3-online.zip` | Windows 联网 CLI 安装包 |
| `wiserec-cli-1.0.3.1-windows-x64-py312-offline.zip` | Windows x64 / Python 3.12 离线 CLI 安装包 |
| `wiserec_cli-1.0.3.1-py3-none-any.whl` | CLI Wheel |
| `CLI-install.md`、`CLI-reference.md` | CLI 1.0.3.1 安装和命令指导 |
| `README.md`、`service.env.example`、`manifest.json`、`SHA256SUMS` | 镜像信息、无真实凭据的配置示例、来源与校验 |

Windows 安装需要自行准备 Python，平台浏览器登录需要 Microsoft Edge；ZIP 不包含两者。权限镜像连接已有 MySQL 8.x，不含 MySQL 或 Jupyter Server。

## 升级影响

**权限系统数据库结构从 8 升至 10，不能直接替换镜像后启动。** 新增 `admins.display_name`，历史姓名为空；新增 `cli_version_policies.deleted_at`，历史策略保留。迁移不修改现有管理员密码、角色、人员、授权或日志，不自动创建策略或删除记录。

升级前在独立库完成备份恢复和迁移演练；维护窗口先停写，再做最终备份，之后由单个进程显式执行迁移、核对数据并启动新镜像。原配置和外部 MySQL 原样保留，不重新创建管理员。完整步骤见 `Docker-upgrade-1.0.3.1.md`。结构升级后不能仅换回 1.0.3 镜像；没有降级迁移，回滚需要恢复与旧镜像匹配的结构 8 备份，并处理备份后新增数据。

## 验证与限制

正式工作流验证 CLI 和权限服务测试、浏览器时区、Windows 联网/离线安装及 1.0.3 → 1.0.3.1 升级、MySQL 容器授权与日志、重启与挂载配置、同一权限镜像摘要的离线导出及 Docker save/load。结构 8 → 10 的数据保留和重复迁移有自动回归测试。真实生产库、业务平台网关及远程 Jupyter 未自动联调；部署方仍需按升级指南验收。发布不自动迁移或部署生产系统。

在线镜像标签为 `ghcr.io/mossexplore/cli-access:1.0.3.1`；生产建议固定 `manifest.json` 记录的已测试镜像摘要。已发布 v1.0.3 的 CLI 二进制及镜像均不覆盖。
