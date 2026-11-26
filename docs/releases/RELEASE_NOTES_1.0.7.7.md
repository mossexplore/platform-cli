# v1.0.7.7 — CLI、权限管理系统与独立本地助手

三个组件统一使用 **1.0.7.7**，分别安装。助手源码、网页、依赖和个人配置不进入 CLI Wheel 或 Windows 安装包。

## 相较上一正式版 v1.0.7.1

- CLI 增加 `ml context`，查看环境与业务上下文；新增 `ml feature-task list`、特征任务执行记录与日志查询、新旧样本任务列表、样本任务执行周期与执行记录查询。成功启动自动保活时不再重复提示。完整命令与使用前提见 `CLI-reference.md`。
- 权限管理系统增加个人通知页面、独立助手 Token 的生成/重置/撤销、通知任务领取与结果回传。申请与通知任务在同一事务提交；通知默认关闭，仅指定管理员使用，不改变审批权限。
- 独立 Python 本地助手通过浏览器配置，支持 Windows 托盘、当前用户登录启动、暂停和退出。配置及恢复状态保存在个人目录下的 JSON 文本文件，无本地数据库。
- 消息地址、auth、sender 和多个接收 UID 可配置；逐对象请求，成功对象不重发，失败对象可单独重试，不确定结果需人工核对。保存配置后自动应用，新对象列表只影响新任务。

## 下载与安装

| 附件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.7.7-windows-py3-online.zip` | CLI Windows 联网安装 |
| `wiserec-cli-1.0.7.7-windows-x64-py312-offline.zip` | CLI Windows x64 / Python 3.12 离线安装 |
| `wiserec_cli-1.0.7.7-py3-none-any.whl` | CLI Wheel |
| `cli-access-1.0.7.7-linux-amd64.tar.gz` | 权限系统 Linux x86_64 Docker 镜像 |
| `permission-notifier-1.0.7.7-windows-source.zip` | 独立助手源码安装 ZIP，含 PowerShell 安装入口 |
| `Notifier-install.md` | 助手安装、Token 绑定、消息配置和退出说明 |
| `CLI-install.md`、`CLI-reference.md` | CLI 安装及命令说明 |
| `Docker-runbook.md`、`Docker-upgrade-1.0.7.7.md` | 权限系统部署与 1.0.7.1 → 1.0.7.7 升级指南 |
| `README.md`、`service.env.example`、`manifest.json`、`SHA256SUMS` | 镜像信息、配置示例、构建来源及附件校验 |

CLI 包不包含 Python 或 Microsoft Edge。助手需要 Windows、Python 3.12 和可获取 Python 依赖的网络，不是免安装 EXE，也不是离线依赖整包。权限镜像不包含 MySQL 或 Jupyter Server，连接已有 MySQL 8.x。

助手解压后运行 `powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1`，使用桌面“权限通知助手”快捷方式启动，在 `http://127.0.0.1:18765` 配置。关闭浏览器不会停止助手，使用页面或托盘“退出”。Token/auth 存在本机个人 JSON 文件中，不随安装包分发。

## 升级与启用

**权限数据库结构从 11 升至 12，必须先迁移再启动。** 新增通知客户端、通知任务表，原有数据保留。先在独立库恢复演练；维护窗口停写并做最终数据库及配置备份，再用目标镜像单进程执行 `python -m app.manage migrate`、核对数据、启动验收。保留原 service.env 和管理员，不重新初始化账号。

没有 12 → 11 降级迁移，不能只切回旧镜像；回滚需要恢复匹配旧版的最终备份并处理备份后新增数据。完整命令见 `Docker-upgrade-1.0.7.7.md`。发布不会自动升级生产或修改版本准入策略。

设置 `NOTIFICATION_OWNER_ADMIN_ID` 后由该管理员登录“个人通知”，开启通知并生成 Token，30 分钟内在助手绑定。历史申请不会自动补发。权限服务远程连接需 HTTPS；消息接口可配置 HTTP/HTTPS，保持 TLS 校验。首次使用必须确认实际接口的成功判据；默认未确认时不发送，主动测试后再恢复通知。

## 验证与限制

发布门禁包括 CLI、服务与助手单元测试、跨组件模拟通知、真实 MySQL 结构 11 → 12 迁移及重复执行、Windows CLI 联网/离线安装与从正式版 1.0.7.1 升级、助手安装及本机 HTTP 启停、镜像同摘要验证和 Docker save/load。独立验证任务在新的运行环境中从草稿重新下载全部附件，核对版本、源提交、哈希、CLI 包隔离及 Docker 导入后的镜像 ID；门禁通过后才正式发布。

真实业务平台、远程 Jupyter 和实际消息接口未联调；托盘交互及用户登录自动启动仍需在实际 Windows 用户桌面验收。跨组件测试使用模拟消息，不代表真实通知已送达。已接受发送只表示接口按配置规则接受，不保证最终用户阅读。
