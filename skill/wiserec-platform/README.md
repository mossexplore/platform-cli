# WiseRec Platform skill

此目录是可独立分发的 Agent Skill。复制整个 `wiserec-platform` 目录，保留 `SKILL.md` 与 `references/` 的相对位置。它覆盖当前项目的环境、业务、看板、离线实验、模型详情与溯源、关联训练任务、训练任务、算法仓、服务日志、数据集、特征集、Web Studio 和 Jupyter 命令。需要安装可用的 WiseRec `ml` CLI；具体命令以安装版本的 `--help` 为准。Jupyter 操作禁止使用交互式 TTY/PTY，文件操作用 files，程序执行用非交互式 exec；不得调用 terminal open/attach。普通进程工具即可捕获结果。文件读写和程序执行指南见 [Jupyter 文件与非交互执行](references/jupyter.md)。

## Windows OpenCode 安装

在**包含本仓库 `skill` 目录**的位置打开 Windows PowerShell 5.1 或 PowerShell 7。项目级安装：

```powershell
$target = '.opencode\skills\wiserec-platform'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path '.\skill\wiserec-platform\*' -Destination $target -Recurse -Force
```

全局安装：

```powershell
$target = Join-Path $HOME '.config\opencode\skills\wiserec-platform'
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path '.\skill\wiserec-platform\*' -Destination $target -Recurse -Force
```

OpenCode 也识别 `.agents\skills\wiserec-platform` 和 `.claude\skills\wiserec-platform` 等兼容位置。其他 agent 按其自身的 Agent Skills 发现路径安装；本 skill 不依赖另一个 skill、bash 或额外脚本。安装后确认目标位置存在 `SKILL.md` 和全部参考文件，重新启动或刷新 agent 会话，询问其可用 skill 列表并核对 `wiserec-platform`。若已有同名 skill，先检查加载优先级，避免读到旧副本。

## 本机核对

```powershell
Get-Command ml
ml --version
ml tree
ml env show
ml auth status
ml business show
ml service logs --help
ml model source --help
ml jupyter files --help
ml jupyter exec --help
```

安装 `ml` 后若当前终端仍找不到命令，重新打开终端再检查。真正使用业务命令前按 `SKILL.md` 核对业务选择。若 `ml service logs --help` 不存在，说明安装的 CLI 版本尚未包含该命令；其他命令同样以安装版本的帮助为准。若 files/exec 帮助不存在，先更新实际调用的 CLI；只复制 skill 不会安装或更新 CLI。`ml login` 需要 Edge 和图形界面，不能在无人值守的无头环境完成交互登录。

## 模型与服务日志入口

```powershell
ml model list -o json
ml model detail MODEL_ID -o json
ml model source MODEL_ID -o json
ml model source MODEL_ID --train-task -o json
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --list --no-input
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME -k error -n 200 --no-input
```

占位符替换为真实目标。模型 source 默认返回溯源，`--train-task` 仅返回训练任务信息；两个 JSON 不混合。服务日志不支持 `-o json`，`--list` 显示文件表格，读取正文可重定向 stdout。用户在交互终端可直接运行 `ml service logs SERVICE_ID` 按编号选择；agent 普通进程使用 `--no-input`，遇到多个候选项需补充参数或询问用户。日志类别和类型约定见 [命令索引](references/commands.md)。

## Jupyter 使用入口

完成环境、登录、业务检查后，Web Studio 用户选择运行中的实例，再查询远端根目录。下面的 ENV_ID 用实际实例 ID 替换：

```powershell
ml webstudio list --status online -o json
ml webstudio login ENV_ID
ml jupyter files list --output json
```

按根目录返回的 path 使用 files 命令；路径不是本机工作目录。一次性远端执行使用 `ml jupyter exec --cwd PATH --output json -- python main.py`，PATH 和脚本必须真实存在。远端需 POSIX 系统及 Python Kernel，本地可使用 Windows。完整命令、输出与失败处理见 [专项指南](references/jupyter.md)；所有 Jupyter 操作均不得切换到交互式终端。

## 分发边界

skill 是调用说明，不随附 CLI、凭据、平台配置或 Jupyter Server。团队分发时复制整个目录即可；不要把本机 `config.json`、`business.json`、Cookie 或 Token 放入 skill 包。
