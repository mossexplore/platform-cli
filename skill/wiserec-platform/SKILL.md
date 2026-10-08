---
name: wiserec-platform
description: 通过 WiseRec 命令行客户端 ml 管理模型及溯源、关联训练任务、训练任务、算法仓、服务及主机日志、数据集、特征集、离线实验、MEP/MTP 看板、Web Studio、Jupyter 文件读写、非交互执行、Notebook；切换环境或核对登录、业务上下文时也使用。
metadata:
  cli: wiserec-cli
---

# WiseRec 平台 CLI

用 `ml` 执行平台交互。按用户目标选择最短且可核验的命令链；不直接请求平台 HTTP 接口，不手工拼接 `businessid` 或复用其他环境的业务 ID。可用 `ml tree` 查看完整命令树（说明结尾不带标点）；需要确认参数时读本 skill 的 [命令索引](references/commands.md)，以已安装客户端的 `ml <子命令> --help` 为最终依据。仅加载当前任务涉及的参考文件。

## 会话入口

1. 确定目标环境。口头描述与 CLI 标识：开发 `dev`、镜像 `mirror`、探索 `explore`、生产 `product`。用户说“登录镜像环境”时先执行 `ml env use mirror`，说“切换到生产环境”时执行 `ml env use product`。仅有查询请求而未指定环境时，用 `ml env show` 确认当前环境，不猜测或擅自切换。
2. 检查 `ml --version`、`ml auth status`；访问业务资源前再检查 `ml business show`。首次进入会话、切换环境、身份可能过期或执行长任务前检查一次；连续命令不重复做全套检查。`auth status` 的退出码 0 不代表有效，必须看 `status=valid` 和剩余有效时间。认证缓存内的 `business_id` 不替代 `business show` 中当前环境的选择。
3. 未安装、未登录、认证过期、未选择业务或权限拒绝时按 [会话与故障处理](references/session.md) 处理，不用可能自动启动 Edge 的业务命令试探。登录可在有图形界面的用户终端交互完成；不要索取密码、验证码、Cookie 或 Token。

## 查询与操作

- 用户给出准确 ID 时直接用该 ID 查询；否则先用最窄的名称、状态或分页筛选定位对象，再继续。任务、算法仓、服务、部署、Pod、作业等 ID 与名称不互换。默认先取小页，只有需要时翻页；不能把第一页当作完整结果。
- 支持 `--output json` / `-o json` 的命令优先用 JSON 读取 ID、状态和数量；部分命令固定表格、文本或 JSON，先查命令索引。检查进程退出码和 stderr。CLI 可能在 stdout 加入认证提示；此时不要把 stdout 整体当作 JSON，也不要猜测解析结果，先完成认证再重新查询。避免把大量返回内容直接送入 agent 上下文。
- 写操作先核对环境、业务、目标 ID 与用户意图。已有授权覆盖具体操作时直接执行；缺少目标、参数或授权时再询问。执行后用只读命令核验。失败或超时后先查远端状态；对训练启动、克隆实验、Notebook 运行等操作不盲目重放。
- 训练任务和算法仓下载会写入本地文件，先确认保存目录与目标文件；算法仓下载链接可能含临时签名。服务日志优先用 `ml service logs SERVICE_ID`；agent 自动化时加 `--no-input` 并按需指定 `--pod`、`--type`、`--file`，不为选择候选项擅自分配 PTY。日志类别没有默认值，同一类别用于文件列表和正文；Python 主机类型是 `infer-python`，CLI 自动映射为日志请求的 `rtc_python`。候选不唯一时向用户确认，不选第一项。正文为原始文本，不支持 `-o json`；详情见 [命令索引](references/commands.md)。
- 模型查询使用 `ml model list/detail/source`；查询关联训练任务用 `ml model source MODEL_ID --train-task`。两种 source 模式的 JSON 分别保留对应接口完整响应，不合并；`MODEL_ID`、来源标识、`jobId`、`taskId` 不互换。
- `ml` 自动处理业务请求头，所选业务来自当前环境 `business.json` 的选择。不要读取或编辑凭据、业务文件来替代 CLI；平台地址也由当前配置中的 `api_endpoint` 决定。

## Jupyter 与 Web Studio

**使用 Jupyter 时禁止交互式 TTY/PTY，禁止调用 `ml jupyter terminal open` 或 `attach`，禁止分配 `tty: true`、模拟按键或通过持久交互 Shell 执行任务。** 文件读写和传输使用 `ml jupyter files`，运行程序、脚本或测试使用非交互式 `ml jupyter exec`；进程工具使用普通输入输出管道。先读 [Jupyter 文件与非交互执行](references/jupyter.md)，按其中说明确认连接、根目录相对路径、JSON 结果和失败状态。不要用本地文件工具操作同名路径来冒充远端修改。

Web Studio 用 `ml webstudio login ENV_ID` 选择默认实例，`--studio-id ENV_ID` 只覆盖本次调用。先核对目标与 online 状态；`files list` 无路径可发现根目录，不能假设存在 `projects`。exec 要求远端 POSIX 系统与 Python Kernel，每次独立执行，明确传入 `--cwd`，不继承前一次 Shell 状态。结果未知时先核对远端，不重放命令。

完整 Notebook 使用现有 `ml jupyter notebook run`，检查本地结果和摘要；没有 Cell 子命令。需要多步命令时准备脚本再通过 exec 执行。程序必须提供非交互参数或配置；无法非交互完成时报告限制，不退回 TTY/PTY，见 [非交互执行约束](references/terminal.md)。

## Windows 与效率

直接调用 `ml`，不要求额外 Python、bash 或 PowerShell 脚本。Windows PowerShell 5.1 和 7 的命令示例见 [安装与使用](README.md)；Windows 上 `ml` 可能是 `.cmd` 入口，不能假定 `CreateProcess` 可直接执行该文件。自动化调用时使用宿主支持本地 Shell 的进程工具处理入口；Jupyter 命令必须使用非交互方式捕获输出，不申请或启用 PTY/TTY。

减少启动次数与网络往返：复用本轮已确认的环境和会话、先精确筛选、只读当前任务相关的参考、根据可用字段核验。不要为省时跳过认证、业务、目标或结果校验。

## 输出与凭据

回答中说明环境、业务范围、目标 ID、实际命令及可观察结果；区分“请求已接受”和“远端已完成”。时间展示若需转换为北京时间，按 UTC+8 正确换算后用 `YYYY-MM-DD HH:mm:ss`；不靠替换 `T` 或删除时区后缀。响应示例不是完整 schema，不以某例缺字段推断接口不存在该字段。

不运行 `ml login --show-secrets`，不将 Cookie、Token、含 Token 的 Web Studio 访问 URL 或其他凭据写入回复、持久日志与共享文件。files/exec 已屏蔽连接地址诊断；其他 Web Studio/Jupyter 命令仍可能将含 Token 地址输出到 stderr，应视作敏感信息。远端文件与程序输出同样可能包含秘密。
