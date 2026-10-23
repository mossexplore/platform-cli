# WiseRec Platform skill

本目录是供 Windows 上的 OpenCode 使用的 Agent Skill，指导 Agent 通过 WiseRec `ml` CLI 操作平台。本文件面向安装和分发人员，不随 skill 安装；Agent 使用的内容在 `SKILL.md` 和 `references/` 中。

## 安装

官方 Windows 安装包分两个阶段执行：先安装并验证 CLI，再安装 `wiserec-platform` skill 和 `/ml` command。第二阶段失败会显示原因，CLI 仍可正常使用；排除文件占用或目录权限问题后重新运行安装程序即可重试。直接通过 pip 安装 Wheel 不会安装 skill。

- skill 同时安装到当前用户的 `~/.config/opencode/skills/wiserec-platform` 和 `~/.cac/skills/wiserec-platform`。设置 `OPENCODE_CONFIG_DIR` 时仅替换 OpenCode 根目录，CAC 路径仍位于当前用户目录。`/ml` command 同时安装到 `~/.config/opencode/commands/ml.md` 和 `~/.cac/commands/ml.md`。
- 每次安装都会完整替换两个目标目录中的 `skills/wiserec-platform`，以及两个目录中的 `commands/ml.md`。这些资源由安装程序管理，请勿直接修改；其他 skill、command 和 OpenCode 配置不受影响。
- 项目目录或兼容目录中的同名副本需自行移除，以免 OpenCode 加载旧副本。
- 安装后完全退出并重新打开 OpenCode，使其获得新的 PATH，然后输入 `/ml 查询当前业务下的模型`；只输入 `/ml` 会检查使用上下文并显示用法。

手工分发时，把 `SKILL.md` 和 `references/` 复制到 `skills/wiserec-platform`，并把仓库中的 `skill/commands/ml.md` 复制到 OpenCode 的 `commands/ml.md`。

## 建议的权限配置

安装程序不修改 OpenCode 权限。建议在 `opencode.json` 中加入以下规则：`ml` 命令默认逐次审批，只放行只读命令，禁止交互终端和输出凭据。OpenCode 按最后匹配的规则生效，具体规则须放在通配规则之后。

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permission": {
    "skill": { "wiserec-platform": "allow" },
    "read": { "*credentials.json": "deny" },
    "bash": {
      "ml *": "ask",
      "ml --version*": "allow",
      "ml * --help*": "allow",
      "ml tree*": "allow",
      "ml context*": "allow",
      "ml env list*": "allow",
      "ml env show*": "allow",
      "ml auth status*": "allow",
      "ml auth ping status*": "allow",
      "ml access status*": "allow",
      "ml business list*": "allow",
      "ml business show*": "allow",
      "ml user info*": "allow",
      "ml mep config get*": "allow",
      "ml history list*": "allow",
      "ml mtp swanboard project list*": "allow",
      "ml mtp swanboard project namespace list*": "allow",
      "ml mtp swanboard project experiment list*": "allow",
      "ml mtp swanboard experiment feature list*": "allow",
      "ml mtp swanboard experiment environment get*": "allow",
      "ml mtp swanboard experiment metrics*": "allow",
      "ml mtp swanboard experiment config list*": "allow",
      "ml mtp swanboard experiment inspect*": "allow",
      "ml offline experiment list*": "allow",
      "ml offline experiment trial list*": "allow",
      "ml offline experiment clone * --dry-run*": "allow",
      "ml sample-task list*": "allow",
      "ml sample-task period list*": "allow",
      "ml sample-task execution list*": "allow",
      "ml feature-task list*": "allow",
      "ml feature-task execution list*": "allow",
      "ml feature-task execution logs search*": "allow",
      "ml train list*": "allow",
      "ml train instance list*": "allow",
      "ml train history list*": "allow",
      "ml algorithm list*": "allow",
      "ml model list*": "allow",
      "ml model detail*": "allow",
      "ml model source*": "allow",
      "ml model deploy * --dry-run*": "allow",
      "ml resource template list*": "allow",
      "ml resource template detail*": "allow",
      "ml deployment template list*": "allow",
      "ml deployment template detail*": "allow",
      "ml service list*": "allow",
      "ml service logs*": "allow",
      "ml service host list*": "allow",
      "ml service deployment list*": "allow",
      "ml dataset list*": "allow",
      "ml dataset detail*": "allow",
      "ml dataset files list*": "allow",
      "ml featureset wide list*": "allow",
      "ml featureset wide config*": "allow",
      "ml featureset model list*": "allow",
      "ml featureset model config*": "allow",
      "ml webstudio list*": "allow",
      "ml webstudio show*": "allow",
      "ml jupyter doctor*": "allow",
      "ml jupyter files list*": "allow",
      "ml jupyter files stat*": "allow",
      "ml jupyter files read*": "allow",
      "ml jupyter terminal list*": "allow",
      "ml * --yes*": "ask",
      "ml * -y*": "ask",
      "ml jupyter terminal open*": "deny",
      "ml jupyter terminal attach*": "deny",
      "ml * --show-secrets*": "deny"
    }
  }
}
```

- 未列出的 `ml` 命令都需要审批，包括写操作、本地下载、登录和业务切换；新增命令默认也需要审批。新增只读命令时，按完整命令路径补充 `allow` 规则，不要使用 `ml * list*` 这类宽泛模式。
- `--yes`、`-y` 规则放在放行规则之后，确保同时带 `--dry-run` 和 `--yes` 的命令仍需审批。
- 放在子命令前的全局参数（如 `ml --config PATH model list`）匹配不到放行规则，会改为审批，不会被误放行。
- 以上只列出 `ml` 相关规则，其他命令按团队要求另行配置。OpenCode 对 PowerShell 命令的解析方式（例如命令前加了编码设置时）可能影响匹配结果，正式分发前请在 OpenCode 中实测：只读命令直接执行，写操作弹出审批，被禁止的命令被拒绝。

## 本机核对

```powershell
Get-Command ml
ml --version
ml tree
ml env show
ml auth status
ml business show
```

`ml login` 需要 Edge 和图形界面，不能在无人值守的环境中完成登录。命令和参数以实际安装的 CLI 帮助为准；命令缺失时更新 CLI，不能只更新 skill。

## 分发边界

skill 只是调用说明，不包含 CLI、凭据、平台配置或 Jupyter Server。不要把本机的 `config.json`、`business.json`、Cookie 或 Token 放入 skill 包。
