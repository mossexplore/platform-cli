---
name: wiserec-platform
description: 通过 WiseRec 命令行客户端 ml 管理训练任务、算法仓、服务及主机日志、数据集、特征集、离线实验、MEP/MTP 看板、Web Studio、Jupyter 文件读写、非交互执行、Notebook 与远程终端；切换环境或核对登录、业务上下文时也使用。
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
- 训练任务和算法仓下载会写入本地文件，先确认保存目录与目标文件；算法仓下载链接可能含临时签名。服务主机日志先用 `ml service host list SERVICE_ID` 找到 Pod 名称与集群，再分别使用 `ml service host logs list` 和 `search`；文件列表的日志类型与内容检索的日志类型分别传入，不自动复用。检索结果是原始多行文本，不按 JSON 解析。
- `ml` 自动处理业务请求头，所选业务来自当前环境 `business.json` 的选择。不要读取或编辑凭据、业务文件来替代 CLI；平台地址也由当前配置中的 `api_endpoint` 决定。

## Jupyter 与 Web Studio

文件读写和传输优先 `ml jupyter files`，运行脚本或测试优先 `ml jupyter exec`；两者不需要 TTY。先读 [Jupyter 文件与非交互执行](references/jupyter.md)，按其中说明确认连接、根目录相对路径、JSON 结果和失败状态。不要用本地文件工具操作同名路径来冒充远端修改。

Web Studio 用 `ml webstudio login ENV_ID` 选择默认实例，`--studio-id ENV_ID` 只覆盖本次调用。先核对目标与 online 状态；`files list` 无路径可发现根目录，不能假设存在 `projects`。exec 要求远端 POSIX 系统与 Python Kernel，每次独立执行，明确传入 `--cwd`，不继承前一次 Shell 状态。结果未知时先核对远端，不重放命令。

完整 Notebook 使用现有 `ml jupyter notebook run`，检查本地结果和摘要；没有 Cell 子命令。只有需要持续交互时使用 `terminal open/attach`，必须在真实 TTY/PTY 中运行并保留会话句柄，见 [交互终端](references/terminal.md)。

## Windows 与效率

直接调用 `ml`，不要求额外 Python、bash 或 PowerShell 脚本。Windows PowerShell 5.1 和 7 的命令示例见 [安装与使用](README.md)；Windows 上 `ml` 可能是 `.cmd` 入口，不能假定 `CreateProcess` 可直接执行该文件。自动化调用时使用宿主支持本地 Shell 的进程工具处理入口；files/exec 可捕获输出，不要求 PTY。只有 terminal open/attach 要求真实交互终端，不要将这一限制扩展到所有命令。

减少启动次数与网络往返：复用本轮已确认的环境和会话、先精确筛选、只读当前任务相关的参考、根据可用字段核验。不要为省时跳过认证、业务、目标或结果校验。

## 输出与凭据

回答中说明环境、业务范围、目标 ID、实际命令及可观察结果；区分“请求已接受”和“远端已完成”。时间展示若需转换为北京时间，按 UTC+8 正确换算后用 `YYYY-MM-DD HH:mm:ss`；不靠替换 `T` 或删除时区后缀。响应示例不是完整 schema，不以某例缺字段推断接口不存在该字段。

不运行 `ml login --show-secrets`，不将 Cookie、Token、含 Token 的 Web Studio 访问 URL 或其他凭据写入回复、持久日志与共享文件。files/exec 已屏蔽连接地址诊断；其他 Web Studio/Jupyter 命令仍可能将含 Token 地址输出到 stderr，应视作敏感信息。远端文件与程序输出同样可能包含秘密。
