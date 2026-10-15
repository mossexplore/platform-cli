# WiseRec Platform skill

此目录是可独立分发的 Agent Skill。复制整个 `wiserec-platform` 目录，保留 `SKILL.md` 与 `references/` 的相对位置。它覆盖当前项目的环境、业务、看板、离线实验、模型详情与溯源、模板部署、资源模板与部署模板、关联训练任务、训练任务、算法仓、服务日志、数据集及目录文件、特征集、Web Studio 和 Jupyter 命令。需要安装可用的 WiseRec `ml` CLI；具体命令以安装版本的 `--help` 为准。Jupyter 操作禁止使用交互式 TTY/PTY，文件操作用 files，程序执行用非交互式 exec；普通进程工具即可捕获结果。文件读写和程序执行指南见 [Jupyter 文件与非交互执行](references/jupyter.md)。

## OpenCode 安装与使用

OpenCode 集成分两个可见阶段执行：先安装并验证 CLI，再安装 `wiserec-platform` skill 和唯一的 `/ml` command。第二阶段失败会显示原因，CLI 仍可正常使用；排除文件占用或目录权限问题后，重新运行安装程序即可重试。

默认目标为当前用户的 `~/.config/opencode`，设置 `OPENCODE_CONFIG_DIR` 时使用该目录。每次安装都会删除旧 `skills/wiserec-platform` 目录和 `commands/ml.md`，完整写入随包的新资源，同版本重装也会更新。WiseRec skill 与 `/ml` command 由安装程序管理，请勿直接修改这些文件。其他 skill、command 和 OpenCode 配置不受影响。项目目录或兼容目录中的同名副本需自行移除，以免加载旧副本。

完成后重新打开 OpenCode 会话，输入 `/ml 查询当前业务下的模型`；输入 `/ml` 可检查使用上下文并查看用法。需要允许 OpenCode 加载 skill 和调用终端工具，安装程序不会修改权限。直接通过 pip 安装 Wheel 不自动执行这一阶段，自动安装入口为官方 Windows 安装包。

手工分发时需同时复制整个 skill 目录至 `skills/wiserec-platform`，并将仓库 `skill/commands/ml.md` 复制至 OpenCode 的 `commands/ml.md`。

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
ml model deploy --help
ml resource template list --help
ml deployment template list --help
ml dataset files --help
ml history list --help
ml jupyter files --help
ml jupyter exec --help
```

安装 `ml` 后若当前终端仍找不到命令，重新打开终端再检查。真正使用业务命令前按 `SKILL.md` 核对业务选择。命令及参数以实际安装的 CLI 帮助为准；入口缺失时更新实际调用的 CLI，不能只复制 skill。`ml login` 需要 Edge 和图形界面，不能在无人值守的无头环境完成交互登录。

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

## 模板与模型部署入口

```powershell
ml model list --name MODEL_NAME -o json
ml deployment template list --name TEMPLATE_NAME -o json
ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --dry-run -o json
```

先核对查询结果中的实际 ID，名称匹配不唯一时继续筛选或请用户选择。模板缺少调用超时或最大并发数时，分别补充 `--service-timeout MILLISECONDS`、`--execute-limit COUNT`。已有具体部署授权时，使用 `ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID --yes -o json` 提交，之后按返回服务 ID 核验。部署详情、参数和异常处理见 [模板与模型部署](references/deployment.md)；框架配置不脱敏，不分享完整预览。

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
