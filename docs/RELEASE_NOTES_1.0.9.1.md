# CLI 1.0.9.1 源码更新说明

增加环境字段 `platform_type`，取值 `wiserec` 或 `mlops`，旧配置默认使用 WiseRec。MLOps 首批支持 `ml train list`，复用现有参数与输出；每页默认 10 条，最多 200 条，业务请求头和请求体使用当前环境选定的业务 ID。

`ml tree` 展示当前环境支持的命令，`ml tree --all` 展示全部命令及支持情况。不支持的业务命令在登录和接口请求前拒绝。MLOps 按配置支持自动保活，训练记录查询、执行记录日志下载和执行实例查询复用 WiseRec 接口；其他训练操作尚未开放。

训练列表小文件按 B、K 展示，继续保留 M、G 展示及北京时间转换。JSON 保留原始数值和额外字段。安装配置同步保留 MLOps 环境。

本次为源码更新，不代表正式 Release 已发布。沿用现有 Python 和平台要求，下载仍以 README 正式发布入口为准。真实 MLOps 登录、业务选择、权限服务及接口联调需在可访问环境验收，不能将模拟响应测试视为真实联调通过。

MLOps 开放全部现有 Web Studio、Jupyter 和 service 公开命令，按已确认的相同接口复用 WiseRec 实现，保留当前环境业务上下文与权限检查。训练列表成功且 count 为零时直接返回空列表，兼容 taskInfos 缺失或为 null。

执行记录日志下载增加 `--type plog`，默认普通日志行为保持兼容。Plog 接口按 code=0 判断成功，从 plogUrl 获取地址，并复用现有文件下载与重名保护。请求不传 target。

MLOps 新增支持现有 auth ping、user、mep、model、resource、deployment、dataset 分组全部公开命令，复用 WiseRec 实现。完整命令树仅在不支持的叶命令描述末尾追加红色 [不支持]，支持命令不添加标记。

CLI 安装仅分发正式 wiserec-platform skill 与 /ml 入口；不再打包或安装 skill-lab 详细版。安装成功时自动清理标准安装位置中历史详细版与 /ml-lab，仓库设计资料保留。

环境 profile 新增 command_policy.deny，可精确禁止 jupyter files upload/download。执行前离线拦截，默认命令树隐藏禁用命令，完整命令树显示红色 [当前环境禁用]。重装保留配置，不扩展为终端、Notebook 或其他文件传输限制。

配合权限服务的环境禁止命令策略，CLI 增加 COMMAND_DISABLED/COMMAND_REQUIRED 拒绝提示与服务端策略展示缓存；删除本地配置不能解除正常在线鉴权收到的禁令，缓存不用于执行放行。

根目录配置样例更名为 config.example.json；构建转换为包内 config.json，安装后的正式用户配置仍为 config.json，真实根目录配置已加入忽略清单。权限系统源码目标同步为 1.0.9.1，数据库结构为 13，需显式迁移。
