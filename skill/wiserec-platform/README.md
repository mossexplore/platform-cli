# WiseRec Platform skill

此目录是可独立分发的 Agent Skill。复制整个 `wiserec-platform` 目录，保留 `SKILL.md` 与 `references/` 的相对位置。需要安装可用的 WiseRec `ml` CLI；Jupyter Terminal 的自动操作还要求 agent 提供可持续读写的真实交互式 PTY/TTY 工具。只有普通一次性 shell 工具的宿主仍可使用其余 CLI 功能。

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
ml env show
ml auth status
```

安装 `ml` 后若当前终端仍找不到命令，重新打开终端再检查。真正使用业务命令前按 `SKILL.md` 核对业务选择。`ml login` 需要 Edge 和图形界面，不能在无人值守的无头环境完成交互登录。

## 分发边界

skill 是调用说明，不随附 CLI、凭据、平台配置或 Jupyter Server。团队分发时复制整个目录即可；不要把本机 `config.json`、`business.json`、Cookie 或 Token 放入 skill 包。
