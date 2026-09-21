# v1.0.3 — CLI 版本管理与 Jupyter 能力

相较 v1.0.0，新增 CLI 版本上报与准入管理、Jupyter Notebook 执行、远程 Terminal 和 Web Studio 动态登录。沿用 v1.0.0 的正式出包方式，Windows 安装包、Wheel、Docker 镜像来自同一 main 提交，源提交、镜像摘要和附件校验见 manifest.json、SHA256SUMS。

## 新增能力

### CLI 版本管理

- CLI 自动上报运行版本；未上报版本的旧客户端按 **1.0.0** 判断。
- 管理台按环境、业务配置最低版本、推荐版本、禁用版本，支持仅观察、升级提醒、强制拒绝及有期限的账号例外。
- 版本使用统计、调用日志中的版本与判断详情，便于定位不兼容客户端。
- 调用日志采用自适应布局，完整命令在详情中查看、复制；筛选、字段名称及操作列对齐统一。
- 管理台版本策略需要实际权限检查链路才能生效；若要防止绕过 CLI，需在网关接入并关闭旁路，版本声明本身不构成可信身份。

### Jupyter 与 Web Studio

- `ml jupyter doctor`：检查服务连接、认证及 Kernel/Terminal HTTP 接口。
- `ml jupyter notebook run`：执行本地 Notebook，将结果保存为 executed.ipynb 和 summary.json，支持 Kernel、工作目录、超时和 JSON 输出。
- `ml jupyter terminal open/list/attach/close`：创建、查询、重连及关闭远程终端。
- `ml webstudio list/login/show`：查询并选择 Web Studio，动态取得 Jupyter 访问凭据；支持 `--studio-id` 为单次 Jupyter 操作指定目标。
- HTTP 与 WebSocket 使用当前环境选择的 businessId。Jupyter 服务需另行部署并具备相应权限，不包含在权限系统 Docker 镜像中。

Notebook 为前台执行，不自动重试代码。doctor 的 HTTP 检查通过不代表 WebSocket、真实业务网关及远程执行已通过验收。详细参数与限制见 CLI-reference.md。

## 下载哪个文件

| 附件 | 用途 |
| --- | --- |
| wiserec-cli-1.0.3-windows-py3-online.zip | Windows 联网安装，依赖由 Python 包源获取 |
| wiserec-cli-1.0.3-windows-x64-py312-offline.zip | Windows x64、Python 3.12 离线安装，包含 CLI 的 Python 依赖 |
| wiserec_cli-1.0.3-py3-none-any.whl | pip 安装 CLI，依赖另行准备 |
| cli-access-1.0.3-linux-amd64.tar.gz | Linux x86_64 权限系统 Docker 离线镜像 |
| Docker-runbook.md、Docker-upgrade-1.0.3.md | 首次部署、1.0.0 → 1.0.3 数据库迁移及回滚指导 |
| CLI-install.md、CLI-reference.md | CLI 安装和完整命令说明 |
| README.md、service.env.example | 镜像信息及配置示例 |
| SHA256SUMS、manifest.json | 附件校验、平台、源码提交和镜像身份 |

Windows 安装前需准备 Python；平台浏览器登录需 Microsoft Edge，ZIP 不包含这两个软件。通用 CLI 要求 Python 3.9+；本次 Windows 验证环境为 Python 3.12 x64。Docker 仅为 linux/amd64，连接已有 MySQL 8.x，不包含数据库和 Jupyter Server。

## 升级必须注意

**权限系统数据库结构由 7 升级到 8，不能直接换镜像后启动。** 先在独立库演练备份恢复和迁移；维护窗口停止全部写入、完成最终备份，再挂载原配置，用 cli-access:1.0.3 执行 `python -m app.manage migrate`。迁移成功后才替换应用容器。

- 原管理员、人员、环境、授权、申请、审计和日志保留；新增版本策略/例外表以及日志版本字段，不重新创建管理员。
- 历史日志的版本为 1.0.0、来源 historical_default，表示默认推定，不是历史实际版本。
- 先完成升级并验证原授权，再单独上线强制版本策略，避免立即阻断旧客户端。
- 旧镜像要求结构 7，迁移后回滚必须恢复匹配的数据库备份；不能仅切换镜像或手改结构版本。恢复备份会缺失备份后的写入。
- 保留原 service.env，不用示例覆盖。升级指导中的命令需匹配实际网络、挂载及端口；发布不会自动升级生产服务器。
- CLI 安装器会刷新默认 config.json，升级前备份自定义配置，升级后核对环境、权限服务与 Jupyter 配置。默认安装未自动启用权限服务。

## 验证范围

正式工作流验证 CLI/服务测试、浏览器时区、MySQL 容器授权及重启、配置目录挂载、Docker save/load、Windows 联网与离线安装，以及从 CLI 1.0.0 升级到 1.0.3。数据库迁移有结构 7 → 8 的数据保留及重复执行回归测试；生产数据库规模、真实平台网关和远程 Jupyter 执行仍需部署方验收。

镜像可通过离线附件导入，也可使用 ghcr.io/mossexplore/cli-access:1.0.3；生产建议固定 manifest.json 中记录的镜像摘要。正式附件不覆盖，后续修复使用新版本发布。
