# Jupyter 非交互执行约束

使用本 skill 操作 Jupyter 时，禁止交互式 TTY/PTY。不得调用 `ml jupyter terminal open`、`ml jupyter terminal attach`，不得设置 `tty: true`、模拟按键或维护交互 Shell 会话。不得通过启用 PTY 扩展、重定向包装或其他工具绕过此约束。

## 替代方式

- 目录查询、文件读写与传输：使用 `ml jupyter files`。
- 运行程序、脚本、测试或 Shell 命令：使用 `ml jupyter exec --cwd PATH --output json -- PROGRAM [ARGS...]`。
- 多步命令：准备脚本上传后用 exec 执行，或显式使用 `sh -c`；不要依赖先前调用的 cd/export 状态。
- 完整 Notebook：使用非交互的 `ml jupyter notebook run`，核对执行摘要和结果文件。
- 需要密码提示或其他交互输入的程序：改用该程序支持的非交互参数或配置；不能改写时报告限制，不退回交互终端，也不将凭据写入命令行或共享文件。

连接前提、参数、路径及退出状态见 [Jupyter 文件与非交互执行](jupyter.md)。使用普通进程工具捕获输出。若宿主返回非交互进程句柄，可用来等待和读取结果，不能将其转为交互会话。超时或断线时先检查远端状态，不自动重发有副作用的命令。

`terminal list` 和 `terminal close` 仅用于用户明确要求的既有终端检查或关闭；不是执行程序的入口。不要为执行命令启动、连接或停止其他用户的终端。
