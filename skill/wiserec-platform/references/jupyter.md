# Jupyter 文件与非交互执行

## 选择操作入口

| 用户任务 | 首选命令 |
| --- | --- |
| 查目录、读写或传输文件 | `ml jupyter files` |
| 执行脚本、测试或一次性远端命令 | `ml jupyter exec` |
| 执行整个本地 Notebook 并保存结果 | `ml jupyter notebook run` |
| 持续交互、需要输入或保留 Shell 状态 | `ml jupyter terminal open/attach`，见 [交互终端](terminal.md) |

files 与 exec 不需要 TTY，可使用普通进程工具捕获输出。不要为读写文件先打开终端，也不要因为没有 PTY 就认定不能运行远端命令。当前 CLI 没有 `cell`、后台 `jobs` 或独立 Kernel 管理命令，不要构造这些命令。

## 连接与路径

先按 [会话检查](session.md) 核对环境、认证与当前业务。Web Studio 模式下：

```text
ml webstudio list --status online -o json
ml webstudio login ENV_ID
ml jupyter files list --output json
```

ENV_ID 必须来自用户目标或查询结果；已有默认实例时先用 `ml webstudio show` 核对，无需重复登录。也可在每条命令上用 `--studio-id ENV_ID` 临时指定实例。实例未启动时，按用户授权启动后查询 online 状态。直连模式使用现有 Jupyter 配置，不执行 Web Studio 登录。不要自行改写认证文件。

远端路径相对 Jupyter 文件浏览器的根目录。`files list` 省略路径查看根目录；使用返回条目的 `path` 继续操作，不假设存在 `projects`。路径不能以 `/` 开头或含 `..`，不能使用本地 Windows 路径。交互终端中的 `cd` 不影响 files 或 exec，exec 每次显式传 `--cwd`。LOCAL 是本机文件，REMOTE 是远端文件，两者不可互换。

`doctor` 会同时检查 Kernel 和 Terminal 管理接口；其失败不一定代表 Contents API 不可用。文件任务直接用只读的 `files list` 验证所需能力。

## 文件命令

各命令均支持 `--studio-id ENV_ID` 和 `--output text|json`（`-o`），默认 text；Agent 优先 JSON。

| 命令（接在 `ml jupyter` 后） | 参数与行为 |
| --- | --- |
| `files list [PATH]` | 仅列一层目录，不是递归搜索 |
| `files stat PATH` | 元数据，无文件正文 |
| `files read PATH` | UTF-8 文本；可用 `--start-line N --end-line N`，从 1 开始且包含首尾 |
| `files write PATH --from-file LOCAL` | 从本地 UTF-8 文件写入；也可用 `--stdin`，二选一 |
| `files mkdir PATH` | 创建一个目录，父目录必须存在，不支持 `-p` |
| `files upload LOCAL REMOTE` | 单文件上传，含二进制；REMOTE 包含目标文件名 |
| `files download REMOTE LOCAL` | 单文件下载；LOCAL 含文件名，本地父目录须存在 |
| `files move SOURCE TARGET` | 移动或重命名，不覆盖目标 |
| `files copy SOURCE TARGET_DIR` | 单文件复制到已有目录，新文件名由服务端决定，读取返回 path |
| `files delete PATH` | 立即删除文件或空目录，无交互确认、不递归 |

write、upload、download 默认不覆盖已有文件，覆盖必须传 `--overwrite` 并符合用户意图。move 没有覆盖选项。上传、下载、复制不递归处理目录；文件命令不是 Shell，没有通配符展开。行范围在下载完整文本后切片，文件传输会占用内存，不适合超大文件。

Agent 编辑文件时，先读取目标，再在本地准备内容，用 write 写回并读取核验。避免与浏览器同时编辑：存在性检查不提供原子并发保护。`--stdin` 仅在宿主能可靠传入 UTF-8 标准输入并关闭输入时使用；Windows 上优先 `--from-file`，避免本地 Shell 的编码与转义差异。Notebook 整体文件可 upload/download；不要把普通文本替换当作 Cell API。

下面假设已查询并确认远端 `workspace` 目录存在，本地 `main.py` 是准备好的 UTF-8 文件：

```text
ml jupyter files list workspace -o json
ml jupyter files write workspace/main.py --from-file ./main.py -o json
ml jupyter files read workspace/main.py -o json
ml jupyter files upload ./data.csv workspace/data.csv -o json
ml jupyter files download workspace/data.csv ./downloaded.csv -o json
```

成功 JSON 是 `{server_url, studio_id, business_id, result}`。目录子项在 `result.content`，read 正文也在 `result.content`，不要混用数组和字符串。stat/write 等返回模型可能有其他字段。时间按北京时间显示。操作失败退出 1 并返回 `{status: "FAILED", error: ...}`；参数解析错误退出 2，可能只有用法文本，不保证 JSON。

## 非交互执行

```text
ml jupyter exec [OPTIONS] -- PROGRAM [ARGS...]
ml jupyter exec --cwd workspace --output json -- python main.py
ml jupyter exec --cwd workspace --timeout 120 --output json -- python -m pytest -q
ml jupyter exec --cwd workspace --output json -- sh -c 'pwd && ls -la'
```

远端须是 Linux/macOS 等 POSIX 系统且有 Python/IPython Kernel；本地 Windows 可连接此类远端。每次用独立 Kernel 启动程序，不继承已有 Notebook 变量、先前 exec 的 cd/export 或交互 Shell 状态。程序通过远端 PATH 查找，必要时使用远端程序绝对路径。不要将“Python Kernel 可用”推断为某个命令或虚拟环境必然可用。

| 选项 | 默认值与用途 |
| --- | --- |
| `--cwd PATH` | 默认 Jupyter 根目录，必须为已有目录 |
| `--timeout SECONDS` | 60，最小 0.1；远端程序执行时限 |
| `--startup-timeout SECONDS` | 60，最小 0.1；Kernel 就绪等待 |
| `--kernel NAME` | 当前环境配置；必须选择 Python Kernel |
| `--max-output BYTES` | stdout/stderr 各自最多保留 1048576 字节，可设 1–10485760 |
| `--output text|json` / `-o` | text 为缩进 JSON，json 为单行结果 |
| `--studio-id ENV_ID` | 单次覆盖默认实例 |

PROGRAM 与 ARGS 置于 `--` 后；CLI 不隐式使用 Shell。需要管道、重定向时显式 `sh -c`，同时正确处理本地 Shell 与远端 Shell 两层引用，不拼接未经转义的输入。标准输入关闭，不能用于密码提示或交互程序。

进程工具等待时间应覆盖 Kernel 启动、程序超时和清理余量；支持会话句柄时持续等待同一调用，不重复启动。stdout/stderr 在完成后返回，不是实时流。超过上限会截断并标记 `truncated`，不提供完整日志文件或任务查询接口；`output_incomplete=true` 表示管道输出未完全收齐。

成功调用的 JSON 外层与 files 相同，执行结果在 `result`：

| result.status | CLI 退出码 | Agent 处理 |
| --- | --- | --- |
| `SUCCEEDED` | 0 | 核对 stdout/stderr 和用户预期产物 |
| `FAILED` | 原始退出码 1–123，其余为 1 | 查看 error、stderr 和原始 exit_code；修正原因后再执行 |
| `TIMED_OUT` | 124 | 远端已确认超时并终止进程组，仍需核对副作用 |
| `LOST` | 2 | 提交后结果未知；不能视为参数错误或自动重跑 |
| `INTERRUPTED` | 130 | 本地中断，不能断言远端已停止 |

`exit_code` 可能为空；用 status 与 remote_state 判断，不把 CLI 退出码当作原始子进程退出码。`cleanup_errors` 非空时按 kernel_id 检查遗留资源，不声称已释放。断线时释放 Kernel 的尝试不保证子进程停止。

exec 完成或超时会清理同一进程组，不适合启动后台常驻服务；主动脱离进程组的子进程不保证清理。没有后台 jobs/status/cancel 命令，超时不是自动重试授权。

## 输出与凭据

新 files/exec 命令已屏蔽连接发现阶段的带 Token 地址诊断，但登录、doctor、Notebook、Terminal 等路径仍可能输出敏感地址。远端文件或程序输出也可能包含秘密；仅报告任务所需内容，不传播凭据。认证失败先完成会话处理，不在混合输出中猜 JSON。
