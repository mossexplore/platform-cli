# Web Studio 与 Jupyter

所有写入和执行均受 [SKILL.md](../SKILL.md) 禁止改码约束：仅处理已授权非代码文件，或执行已确认不改码的既有程序/Notebook。默认使用 `--agent`（不与 `-o` 同传）。

**禁止 `ml jupyter terminal open|attach` 及分配 TTY/PTY**（失败也不能退回交互终端）。`ml jupyter terminal list --agent` 只读；`ml jupyter terminal close NAME --agent` 无确认且会杀进程，仅用户明确要求时执行。CLI 无 Cell/后台任务/Kernel 管理命令。

## 连接与选择实例

```powershell
ml webstudio show --agent                  # 查看默认实例缓存（不代表实时状态）
ml webstudio list --status online --agent  # 查在线实例，取 envId（支持 -A）
ml webstudio login ENV_ID --agent          # 建立连接并设为默认实例（强制刷新加 --refresh）
ml webstudio start ENV_ID --agent          # 启动实例（约 15 秒返回，需用户授权）
```

- 已有合适默认实例时无需重复 `login`；单次命令可用 `--studio-id ENV_ID` 临时指定。
- `start` / `stop` 不改默认实例（`stop` 会中断运行中的 Notebook/终端，先核对目标）；启动后用 `ml webstudio list --env-id ENV_ID --agent` 确认状态。
- `ml jupyter doctor --agent` 同时检查 Kernel 与终端接口，其失败不代表文件接口不可用，文件任务直接用 `files list` 验证。

## 远端文件操作（`ml jupyter files`）

均支持 `--studio-id ENV_ID` 与 `--agent`。路径相对 Jupyter 根目录（先省略路径 `files list --agent` 取实际 `path`，勿假设 `projects`），**禁止 `/` 开头、`..` 或 Windows 路径**；`LOCAL` 与 `REMOTE` 不可互换。

| 子命令 | 行为与关键选项 |
| --- | --- |
| `files list [PATH]` | 列一层目录（不递归）；返回 `path`、`fields`、`items` |
| `files stat PATH` | 类型、大小、时间、可写性（不含正文） |
| `files read PATH [--start-line N] [--end-line N]` | 读 UTF-8 文本（行号从 1 起含首尾），正文在顶层 `content` |
| `files write PATH --from-file LOCAL [--overwrite]` | 从本地 UTF-8 文件写入（Windows 优先 `--from-file`，避免 `--stdin` 编码问题） |
| `files mkdir PATH` | 建一层目录，父目录须存在 |
| `files upload LOCAL REMOTE [--overwrite]` | 上传单文件（含二进制），`REMOTE` 含目标文件名 |
| `files download REMOTE LOCAL [--overwrite]` | 下载单文件，`LOCAL` 含文件名且本地父目录须存在 |
| `files move SOURCE TARGET` | 移动/重命名，不覆盖 |
| `files copy SOURCE TARGET_DIR` | 复制单文件至已有目录，新路径以返回 `path` 为准 |
| `files delete PATH` | 立即删除文件或空目录，**无确认**、不递归 |

- 默认不覆盖（覆盖已授权非代码文件须加 `--overwrite`）；不递归、不展开通配符；大文件不适合 `read`/传输（整文件进内存）。
- 编辑非代码文件：先 `read` 确认非代码 → 本地准备 → `write --from-file --overwrite` → 再 `read` 核验。失败退出 `1` 返回 `{status:"FAILED",error:...}`。

## 非交互执行（`ml jupyter exec`）

```powershell
ml jupyter exec --cwd workspace --agent -- sh -c 'pwd && ls -la'
```

- **语法**：CLI 选项（含 `--agent`、`--cwd`）必须放在 `--` 之前，`PROGRAM [ARGS...]` 在 `--` 之后；需管道/重定向时显式 `sh -c`（注意 PowerShell 与远端 sh 两层引号）。
- **隔离与限制**：每次使用独立 Kernel（不继承上次 `cd`/`export` 或 Notebook 变量），标准输入关闭；stdout/stderr 各自默认上限 1 MiB（`--max-output`），超出标 `truncated`；结束/超时清理进程组，不用于常驻后台服务。
- **工具等待超时**：`--startup-timeout`（默认 60s）+ `--timeout`（默认 60s）+ 至少 60s 余量。
- **状态与退出码**（`--agent` 结果字段在顶层；`exit_code` 可能为空，以 `status`/`remote_state` 为准；`cleanup_errors` 非空时报告 `kernel_id`）：

| `status` | 退出码 | 处理 |
| --- | --- | --- |
| `SUCCEEDED` | `0` | 核对 stdout、stderr 与产物 |
| `FAILED` | `--agent` 透传 `1–255`（`-o json` 透传 `1–123`），其余 `1` | 看 `error`/`stderr`/`exit_code`；需改码则停止 |
| `TIMED_OUT` | `124` | 远端已终止进程组，仍需核对副作用 |
| `LOST` | `2` | 结果未知，不按参数错处理、不自动重跑 |
| `INTERRUPTED` | `130` | 本地中断，不能断言远端已停止 |

## Notebook 执行

```powershell
ml jupyter notebook run '.\analysis.ipynb' --download '.\results' --agent
```

- 仅执行既有且不改码的 `.ipynb`；按顺序跑全部单元格，失败亦保存部分结果至 `--download` 下新建子目录（默认 `results`）。
- **工具等待超时**：`--startup-timeout`（默认 60s）+ `--timeout`（默认 600s）+ 至少 60s 余量；失败或超时查摘要与远端状态，不自动重跑。
