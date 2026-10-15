# Web Studio 与 Jupyter

## 选择入口

| 用户任务 | 命令 |
| --- | --- |
| 查目录、读写或传输文件 | `ml jupyter files` |
| 执行脚本、测试或一次性远端命令 | `ml jupyter exec` |
| 执行整个本地 Notebook 并保存结果 | `ml jupyter notebook run` |
| 多步命令 | 写成脚本上传后用 exec 执行，或用 `sh -c` |
| 需要交互输入的程序 | 改用程序的非交互参数或配置；做不到时向用户报告限制 |

**禁止 `ml jupyter terminal open`、`ml jupyter terminal attach`，禁止分配 TTY/PTY、模拟按键或维持交互 Shell**，失败时也不能退回交互终端。`ml jupyter terminal list` 可以只读查看；`ml jupyter terminal close NAME` 会结束其中的进程且无确认，仅在用户明确要求时使用。CLI 没有 Cell、后台任务或 Kernel 管理命令，不要构造这些命令。

## 连接实例

先按 [session.md](session.md) 完成环境、认证和业务检查，然后：

```powershell
ml webstudio show
ml webstudio list --status online -o json
ml webstudio login ENV_ID
ml jupyter files list -o json
```

- `ml webstudio show` 显示当前环境、账号和业务绑定的默认实例及缓存状态，不代表实例实时状态；已有合适的默认实例时无需重复登录。
- ENV_ID 必须来自用户指定或查询结果。`login` 重新建立并验证连接，并保存为默认实例；`--refresh` 强制重新获取凭据和会话。单次命令可用 `--studio-id ENV_ID` 临时指定实例。
- 实例未运行时，经用户授权运行 `ml webstudio start ENV_ID`（接口可能约 15 秒才返回），再用 `ml webstudio list --env-id ENV_ID -o json` 确认状态。`stop` 可能中断运行中的 Notebook 或终端，先核对目标。start 和 stop 不改变默认实例。
- `ml jupyter doctor` 同时检查 Kernel 与终端管理接口，它失败不一定代表文件接口不可用；文件任务直接用 `files list` 验证。

## 远端路径

- 路径相对 Jupyter 文件浏览器的根目录。先省略路径运行 `files list` 查看根目录，再使用返回条目的 `path`，不要假设存在 `projects`。
- 远端路径不能以 `/` 开头或包含 `..`，不能使用 Windows 本地路径。LOCAL 是本机文件，REMOTE 是远端文件，两者不可互换。
- 不要用本地文件工具修改同名本地路径来冒充远端修改。

## 文件命令

均支持 `--studio-id ENV_ID` 和 `-o text|json`，Agent 使用 `-o json`。

| 命令（接在 `ml jupyter` 后） | 行为 |
| --- | --- |
| `files list [PATH]` | 只列一层，不递归 |
| `files stat PATH` | 类型、大小、时间和可写性，不含正文 |
| `files read PATH [--start-line N] [--end-line N]` | UTF-8 文本，行号从 1 开始且含首尾 |
| `files write PATH --from-file LOCAL` | 从本地 UTF-8 文件写入；也可 `--stdin`，二选一 |
| `files mkdir PATH` | 创建一层目录，父目录必须存在 |
| `files upload LOCAL REMOTE` | 上传单文件，含二进制；REMOTE 包含目标文件名 |
| `files download REMOTE LOCAL` | 下载单文件；LOCAL 含文件名，本地父目录须存在 |
| `files move SOURCE TARGET` | 移动或重命名，不覆盖 |
| `files copy SOURCE TARGET_DIR` | 复制单文件到已有目录，新文件名由服务端决定，从返回的 path 读取 |
| `files delete PATH` | 立即删除文件或空目录，无确认、不递归 |

- write、upload、download 默认不覆盖已有文件；覆盖须加 `--overwrite` 且符合用户意图。命令不递归处理目录，也不展开通配符。
- 编辑远端文件：先 read，在本地准备完整内容，用 `write --from-file --overwrite` 写回，再 read 核验。Windows 上优先 `--from-file`，避免 `--stdin` 的编码问题。避免与用户在浏览器中同时编辑同一文件。
- read 和传输会把整个文件读入内存，不适合超大文件。
- 成功 JSON 为 `{server_url, studio_id, business_id, result}`：目录子项在 `result.content`（数组），read 的正文也在 `result.content`（字符串）。失败退出 1 并返回 `{status: "FAILED", error: ...}`；参数错误退出 2，可能只有用法文本。

```powershell
ml jupyter files list workspace -o json
ml jupyter files write workspace/main.py --from-file '.\main.py' --overwrite -o json
ml jupyter files read workspace/main.py -o json
ml jupyter files download workspace/data.csv '.\data.csv' -o json
```

## 非交互执行

```powershell
ml jupyter exec --cwd workspace -o json -- python main.py
ml jupyter exec --cwd workspace --timeout 600 -o json -- python -m pytest -q
ml jupyter exec --cwd workspace -o json -- sh -c 'pwd && ls -la'
```

- 远端须是 POSIX 系统且有 Python Kernel，本地 Windows 可以连接。每次调用使用独立 Kernel，不继承 Notebook 变量或上一次 exec 的 `cd`、`export`，每次都显式传 `--cwd`。程序按远端 PATH 查找，Kernel 可用不代表某个命令或虚拟环境可用。
- PROGRAM 与 ARGS 放在 `--` 之后，CLI 不隐式使用 Shell；需要管道或重定向时显式用 `sh -c`。注意本地 PowerShell 和远端 sh 两层引号，复杂命令写成脚本上传后执行。
- 标准输入关闭，不能用于密码提示或交互程序。stdout、stderr 在结束后一次返回；各自默认最多保留 1 MiB（`--max-output`），超出截断并标记 `truncated`；`output_incomplete=true` 表示输出未收齐。
- 时限：`--startup-timeout`（Kernel 就绪，默认 60 秒）加 `--timeout`（程序执行，默认 60 秒）。shell 工具的 `timeout` 设为两者之和再加至少 60 秒。
- exec 结束或超时会清理同一进程组，不适合启动后台常驻服务。

执行结果在 JSON 的 `result` 中：

| `result.status` | CLI 退出码 | 处理 |
| --- | --- | --- |
| `SUCCEEDED` | 0 | 核对 stdout、stderr 和预期产物 |
| `FAILED` | 原始退出码 1–123，其余为 1 | 查看 error、stderr 和 `exit_code`，修正后再执行 |
| `TIMED_OUT` | 124 | 远端已终止进程组，仍需核对副作用 |
| `LOST` | 2 | 结果未知，不当作参数错误，不自动重跑 |
| `INTERRUPTED` | 130 | 本地中断，不能断言远端已停止 |

`exit_code` 可能为空，以 `status` 和 `remote_state` 为准。`cleanup_errors` 非空时说明 Kernel 可能遗留，按 `kernel_id` 报告，不要声称已释放。

## Notebook

```powershell
ml jupyter notebook run '.\analysis.ipynb' --download '.\results' -o json
```

- 上传本地 `.ipynb` 并按顺序执行全部单元格，失败也保存部分结果；结果写入 `--download` 目录下每次新建的子目录（默认相对当前目录的 `results`）。
- 时限为 `--startup-timeout`（默认 60 秒）加 `--timeout`（全部单元格，默认 600 秒），shell 工具的 `timeout` 相应设为两者之和再加至少 60 秒。
- 失败或超时检查摘要和远端状态，不自动重跑。

## 凭据

files 和 exec 不输出带 Token 的连接地址；Web Studio 列表会脱敏凭据字段。其他异常诊断、远端文件和程序输出仍可能含秘密，只报告任务需要的内容。认证失败时先处理会话，不在混合输出中猜测 JSON。
