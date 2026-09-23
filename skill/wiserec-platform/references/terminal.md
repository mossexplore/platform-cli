# Jupyter 远程交互终端

## 前提和目标

先完成 `SKILL.md` 的会话检查。使用 Web Studio 时，先通过 `ml webstudio list` 确认实例 ID 和 online 状态；默认实例可通过 `ml webstudio show` 查看，需要选择时用 `ml webstudio login ENV_ID`。也可以在 Jupyter 命令上带 `--studio-id ENV_ID`，该选项只影响本次命令。终端名称只在所属实例内有效。

`ml jupyter doctor [--studio-id ENV_ID]` 只检查 HTTP 认证、Kernel 与 Terminal 接口；它**不能证明** WebSocket 交互通道可用，实际 `open/attach` 才能验证。

## agent 的执行方式

1. 先确认宿主 agent 提供能持续写入和读取的 PTY/TTY 进程工具。用它启动 `ml jupyter terminal open`，或者 `ml jupyter terminal attach NAME`；例如具有 `tty: true` 且返回可复用会话句柄的进程工具。在 Windows 上应开启真正的交互式控制台。stdin 和 stdout 都必须是 TTY。OpenCode 的普通 `shell` 工具若只返回一次性输出或后台任务，不能当作已具备此能力；此时应启用宿主的 PTY 扩展/工具，缺少时明确告知不能由 agent 自动操作交互终端。不要用 `Start-Process` 隐藏窗口、输出重定向或 `ml ... | Out-String` 假装 TTY。
2. 保留进程会话句柄；等待出现 CLI 打印的终端名称和远端提示符。将实例 ID 与终端名称对应记录在当前任务上下文。若连接失败，先用 `ml jupyter terminal list` 检查服务端是否已创建终端，再决定 `attach`，不要反复 `open` 制造新终端。
3. 通过会话句柄写入远端命令及回车，读取新输出，按输出判断是否成功。`cd` 等状态命令必须在**同一条终端连接**中继续执行，不能每条命令新开一个本地进程。执行耗时命令时持续读取输出；输出暂时为空不代表完成。
4. 远端允许执行服务器上可用的全部命令。示例：`pwd`、`ls`、`cd project`、`cat README.md`、`python --version`、`pip list`。命令由用户目标、远端 Shell 和权限决定；这些示例不是限制。含特殊字符、路径或换行的命令应按远端 Shell 语法转义，不能把本地 PowerShell 语法直接当成远端 Shell 语法。
5. `Ctrl+C` 发送给远端进程，`Ctrl+D` 发送 EOF，`Ctrl+]`（控制字符 0x1D）只断开本地连接。要继续使用现有终端，运行 `ml jupyter terminal attach NAME`。`ml jupyter terminal close NAME` 会删除远端终端并可能中止其中的进程；只有目标确实是关闭它时才执行。

`attach` 不保证补取全部历史输出。断线、工具超时或结果不明时先通过现有终端和相关平台查询核对实际状态，不直接重发可能有副作用的远端命令。

Web Studio 访问 URL 可能带临时 Token，CLI 可能在 stderr 打印它。只将其用于建立连接，不复制到回答、工单或可共享日志。处理终端输出时也注意远端命令可能打印秘密。
