---
name: wiserec-platform
description: 通过 WiseRec 命令行客户端 ml 查询或操作训练任务、特征集、离线实验、MEP/MTP 看板、Web Studio、Jupyter Notebook 与远程终端；需要切换平台环境、核对登录和业务上下文时也使用。所有平台交互经 ml 完成。
metadata:
  cli: wiserec-cli
---

# WiseRec 平台 CLI

用 `ml` 执行平台交互。按用户目标选择最短且可核验的命令链；不直接请求平台 HTTP 接口，不手工拼接 `businessid` 或复用其他环境的业务 ID。需要确认参数时读本 skill 的 [命令索引](references/commands.md)，以已安装客户端的 `ml <子命令> --help` 为最终依据。仅加载当前任务涉及的参考文件。

## 会话入口

1. 确定目标环境。口头描述与 CLI 标识：开发 `dev`、镜像 `mirror`、探索 `explore`、生产 `product`。用户说“登录镜像环境”时先执行 `ml env use mirror`，说“切换到生产环境”时执行 `ml env use product`。仅有查询请求而未指定环境时，用 `ml env show` 确认当前环境，不猜测或擅自切换。
2. 检查 `ml --version`、`ml auth status`；访问业务资源前再检查 `ml business show`。首次进入会话、切换环境、身份可能过期或执行长任务前检查一次；连续命令不重复做全套检查。`auth status` 的退出码 0 不代表有效，必须看 `status=valid` 和剩余有效时间。认证缓存内的 `business_id` 不替代 `business show` 中当前环境的选择。
3. 未安装、未登录、认证过期、未选择业务或权限拒绝时按 [会话与故障处理](references/session.md) 处理，不用可能自动启动 Edge 的业务命令试探。登录可在有图形界面的用户终端交互完成；不要索取密码、验证码、Cookie 或 Token。

## 查询与操作

- 用户给出准确 ID 时直接用该 ID 查询；否则先用最窄的名称、状态或分页筛选定位对象，再继续。不同资源的 ID 不互换。默认先取小页，只有需要时翻页；不能把第一页当作完整结果。
- 支持 `--output json` / `-o json` 的命令优先用 JSON 读取 ID、状态和数量；部分命令固定表格、文本或 JSON，先查命令索引。检查进程退出码和 stderr。CLI 可能在 stdout 加入认证提示；此时不要把 stdout 整体当作 JSON，也不要猜测解析结果，先完成认证再重新查询。避免把大量返回内容直接送入 agent 上下文。
- 写操作先核对环境、业务、目标 ID 与用户意图。已有授权覆盖具体操作时直接执行；缺少目标、参数或授权时再询问。执行后用只读命令核验。失败或超时后先查远端状态；对训练启动、克隆实验、Notebook 运行等操作不盲目重放。
- `ml` 自动处理业务请求头，所选业务来自当前环境 `business.json` 的选择。不要读取或编辑凭据、业务文件来替代 CLI；平台地址也由当前配置中的 `api_endpoint` 决定。

## Jupyter 与 Web Studio

Web Studio 的默认实例由 `ml webstudio login ENV_ID` 选择；`--studio-id ENV_ID` 仅覆盖单次 Jupyter 命令。选择目标前核对实例状态和 ID。Notebook 在远端执行代码且前台运行，结果目录与摘要需核对；结果不明时先检查远端，不能直接重跑。

`ml jupyter terminal open` 和 `attach` **必须在 agent 的真实交互式 TTY/PTY 会话中运行**，保持会话句柄并通过它读写远端 Shell。不得将它们经管道、重定向、后台无 TTY 执行或用普通捕获输出的子进程包装。终端连接后，按用户任务发送任何远端服务器可用的命令，包括 `ls`、`cd`、`pwd`、`cat`、`python`、`pip list` 等；不要把示例当成白名单。完整操作见 [交互终端](references/terminal.md)。

## Windows 与效率

直接调用 `ml`，不要求额外 Python、bash 或 PowerShell 脚本。Windows PowerShell 5.1 和 7 的命令示例见 [安装与使用](README.md)；Windows 上 `ml` 可能是 `.cmd` 入口，不能假定 `CreateProcess` 可直接执行该文件。需要自动化调用时用 agent 的交互式终端工具运行 `ml`，不要自行编造命令包装器。

减少启动次数与网络往返：复用本轮已确认的环境和会话、先精确筛选、只读当前任务相关的参考、根据可用字段核验。不要为省时跳过认证、业务、目标或结果校验。

## 输出与凭据

回答中说明环境、业务范围、目标 ID、实际命令及可观察结果；区分“请求已接受”和“远端已完成”。时间展示若需转换为北京时间，按 UTC+8 正确换算后用 `YYYY-MM-DD HH:mm:ss`；不靠替换 `T` 或删除时区后缀。响应示例不是完整 schema，不以某例缺字段推断接口不存在该字段。

不运行 `ml login --show-secrets`，不将 Cookie、Token、含 Token 的 Web Studio 访问 URL 或其他凭据写入回复、持久日志与共享文件。Web Studio 模式下现有 CLI 可能将含 Token 的访问 URL 输出到 stderr，读取工具输出时必须视作敏感信息。
