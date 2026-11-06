# 1.0.9.1 发布说明

增加环境字段 `platform_type`，取值 `wiserec` 或 `mlops`，旧配置默认使用 WiseRec。MLOps 首批支持 `ml train list`，复用现有参数与输出；每页默认 10 条，最多 200 条，业务请求头和请求体使用当前环境选定的业务 ID。

`ml tree` 展示当前环境支持的命令，`ml tree --all` 展示全部命令及支持情况。不支持的业务命令在登录和接口请求前拒绝。MLOps 按配置支持自动保活，训练记录查询、执行记录日志下载和执行实例查询复用 WiseRec 接口；其他训练操作尚未开放。

训练列表小文件按 B、K 展示，继续保留 M、G 展示及北京时间转换。JSON 保留原始数值和额外字段。安装配置同步保留 MLOps 环境。

本次相较上一正式版本 1.0.7.10，四个产品统一为 1.0.9.1。沿用现有 Python 和平台要求。真实 MLOps 登录、业务选择、权限服务及接口联调需在可访问环境验收，不能将模拟响应测试视为真实联调通过。

MLOps 开放全部现有 Web Studio、Jupyter 和 service 公开命令，按已确认的相同接口复用 WiseRec 实现，保留当前环境业务上下文与权限检查。训练列表成功且 count 为零时直接返回空列表，兼容 taskInfos 缺失或为 null。

执行记录日志下载增加 `--type plog`，默认普通日志行为保持兼容。Plog 接口按 code=0 判断成功，从 plogUrl 获取地址，并复用现有文件下载与重名保护。请求不传 target。

MLOps 新增支持现有 auth ping、user、mep、model、resource、deployment、dataset 分组全部公开命令，复用 WiseRec 实现。完整命令树仅在不支持的叶命令描述末尾追加红色 [不支持]，支持命令不添加标记。

CLI 安装仅分发正式 wiserec-platform skill 与 /ml 入口；不再打包或安装 skill-lab 详细版。安装成功时自动清理标准安装位置中历史详细版与 /ml-lab，仓库设计资料保留。

环境 profile 新增 command_policy.deny，可精确禁止 jupyter files upload/download。执行前离线拦截，默认命令树隐藏禁用命令，完整命令树显示红色 [当前环境禁用]。重装保留配置，不扩展为终端、Notebook 或其他文件传输限制。

配合权限服务的环境禁止命令策略，CLI 增加 COMMAND_DISABLED/COMMAND_REQUIRED 拒绝提示与服务端策略展示缓存；删除本地配置不能解除正常在线鉴权收到的禁令，缓存不用于执行放行。

根目录配置样例更名为 config.example.json；构建转换为包内 config.json，安装后的正式用户配置仍为 config.json，真实根目录配置已加入忽略清单。权限系统源码目标同步为 1.0.9.1，数据库结构为 13，需显式迁移。


## 下载与使用前提

在本 Release 下载 Windows CLI 联网 ZIP、Python 3.12 x64 离线 ZIP、独立 Wheel、Linux amd64 权限系统镜像和独立 Windows 权限通知助手源码安装包。Agent 使用 GitHub 自动提供的完整仓库源码 ZIP/TAR，按 agent-service/README.md 安装；需要 Python 3.12、MySQL、Edge 和支持工具调用的模型服务。Agent 补齐特征装配、标签装配的样本定义及特征查询映射，保持原命令权限与业务上下文；通知助手此次同步版本。

CLI 安装仅包含正式 skill；离线包不含 Python 和 Edge。权限系统镜像不包含 MySQL 或 Jupyter Server。安装步骤见 CLI-install.md、Notifier-install.md、Docker-runbook.md；所有独立附件均在 SHA256SUMS 内，manifest.json 记录构建提交与已测试镜像身份。

## 升级、迁移与回滚

权限系统必须使用结构 13。从当前结构 12 升级，按 Docker-upgrade-1.0.9.1.md 先独立库恢复演练，再停写和最终备份，使用目标镜像单进程显式迁移，核对原人员、授权及空策略后切换并验收。保留原 service.env、外部数据库和管理员，不重新初始化。结构变化后不支持直接回滚旧镜像，无降级迁移；按指南恢复最终备份，恢复将丢失备份后新增数据。禁止修改 schema_versions 冒充迁移。生产部署不随 GitHub 发布自动更新。

## 验证范围

正式发布门禁包括 CLI 和服务测试、浏览器时区与策略输入测试、Windows 全新/重复/离线安装及从 1.0.7.10 升级、最终分发镜像的 MySQL 结构 12→13 迁移和重复迁移、授权允许与禁止命令拒绝、数值图表 JSON、日志、重启和目录配置、Docker 导入导出、通知助手与 Agent 自动化测试以及下载附件独立校验。最终通过情况以对应正式工作流为准。Agent 使用注入 HTTP 与 SQLite 自动化测试，尚未完成真实模型、Edge、MySQL 和平台组合验收；真实 MLOps 和 Jupyter 操作仍需用户环境验收。
