# WiseRec Platform skill

本目录是供 Windows 上的 OpenCode 使用的 Agent Skill，指导 Agent 通过 WiseRec `ml` CLI 操作平台。本文件面向安装和分发人员，不随 skill 安装；Agent 使用的内容在 `SKILL.md` 和 `references/` 中。

## 安装

官方 Windows 安装包分两个阶段执行：先安装并验证 CLI，再安装 `wiserec-platform` skill 和 `/ml` command。第二阶段失败会显示原因，CLI 仍可正常使用；排除文件占用或目录权限问题后重新运行安装程序即可重试。直接通过 pip 安装 Wheel 不会安装 skill。

- 默认目标为当前用户的 `~/.config/opencode`，设置 `OPENCODE_CONFIG_DIR` 时使用该目录。
- 每次安装都会删除旧的 `skills/wiserec-platform` 目录和 `commands/ml.md`，再完整写入随包资源。这两处由安装程序管理，请勿直接修改；其他 skill 和 command 不受影响。
- 同一目录下的 `opencode.json` 会被合并写入权限规则。若目录里只有 `opencode.jsonc` 且内容是严格 JSON，则改写该文件，因为 OpenCode 会在 `opencode.json` 之后加载它。两个文件同时存在时安装停止，原文件保持不变。安装程序只新增或更新自己管理的规则，保留模型、插件和其他字段，以及用户自己的权限规则。写入前把原文件备份为同名加 `.wiserec-backup`，任何失败都会恢复原文件。重复安装不会追加重复规则。以往示例里的尾部通配放行（如 `ml tree*`、`ml * --help*`）会在合并时去掉。
- 项目目录或兼容目录中的同名副本需自行移除，以免 OpenCode 加载旧副本。
- 安装后完全退出并重新打开 OpenCode，使其获得新的 PATH，然后输入 `/ml 查询当前业务下的模型`；只输入 `/ml` 会检查使用上下文并显示用法。

手工分发时，把 `SKILL.md` 和 `references/` 复制到 `skills/wiserec-platform`，并把仓库中的 `skill/commands/ml.md` 复制到 OpenCode 的 `commands/ml.md`，再把下面的权限规则合并进 `opencode.json`。

## 权限配置

规则面向 Windows 上的 OpenCode。OpenCode 在这里默认使用 PowerShell 执行 shell 工具。规则按最后一条命中生效，匹配不区分大小写，并把反斜杠当作 `/`。

第一条 `shell` 规则是 `"*": "ask"`，作为兜底。只有完整、无额外参数的已知只读 `ml` 命令被精确 `allow`。放行规则不含 `*`。`--help` 只放行下表中的几条完整命令。带 ID、`-o json` 或其他额外参数的命令，以及以后新增的命令，都回到审批。

放在精确放行之后、仍然要求审批的模式：

- `ml jupyter exec*`
- `ml * --yes*` 与 `ml * -y*`
- `ml env use product*`
- `ml model deploy*`
- `ml train start*`
- `* > *` 与 `* >> *`

被拒绝的模式：`ml login --show-secrets*`、`ml jupyter terminal open*`、`ml jupyter terminal attach*`，以及 shell 中用 `cat`、`type`、`gc`、`Get-Content`、`sls`、`findstr`、`Copy-Item` 等方式读取 `credentials.json`。文件名规则是 `*credentials.json*`。

`[IO.File]::ReadAllText` 和 `${路径}` 不是 OpenCode 能拆出来的命令。扫描结果为空时，OpenCode 不做权限检查，所以上述规则拦不住这两种读法。不要用它们读取凭据。凭据改为 Windows DPAPI 加密存储由单独事项处理，本安装程序不实现 DPAPI。

下面是全新安装时写入的 `opencode.json`。已有文件会在保留其他字段的前提下得到同样的受管理规则。

```json
{
  "$schema": "https://opencode.ai/config.json",
  "permissions": [
    {
      "action": "shell",
      "resource": "*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml *",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml --version",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml tree",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml env list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml env show",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml auth status",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml auth ping status",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml access status",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml business list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml business show",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml user info",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml mep config get",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml history list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml mtp swanboard project list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml offline experiment list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml train list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml algorithm list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml model list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml resource template list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml deployment template list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml service list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml dataset list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml featureset wide list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml featureset model list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml webstudio list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml webstudio show",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter doctor",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter files list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter terminal list",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter exec*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml * --yes*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml * -y*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml env use product*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml model deploy*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml train start*",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "* > *",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "* >> *",
      "effect": "ask"
    },
    {
      "action": "shell",
      "resource": "ml tree --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml env list --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml service logs --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml train list --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml model list --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter exec --help",
      "effect": "allow"
    },
    {
      "action": "shell",
      "resource": "ml jupyter terminal open*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "ml jupyter terminal attach*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "ml login --show-secrets*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "ml * --show-secrets*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "cat *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "type *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "gc *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "get-content *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "more *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "less *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "head *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "tail *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "select-string *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "sls *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "findstr *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "copy *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "cp *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "copy-item *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "import-csv *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "get-item *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "gi *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "notepad *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "base64 *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "certutil *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "xxd *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "od *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "strings *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "sed *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "awk *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "grep *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "rg *credentials*",
      "effect": "deny"
    },
    {
      "action": "shell",
      "resource": "*credentials.json*",
      "effect": "deny"
    },
    {
      "action": "skill",
      "resource": "wiserec-platform",
      "effect": "allow"
    },
    {
      "action": "read",
      "resource": "*credentials.json*",
      "effect": "deny"
    }
  ]
}
```

- 全局参数放在子命令前（如 `ml --config PATH env show`）匹配不到精确放行，会改为审批。
- 重定向算在命令文本里，所以 `ml tree > 文件` 不会命中 `ml tree` 的放行规则。
- 正式分发前请在 Windows 上用发布版 OpenCode 复核 tree-sitter 拆分、实际选中的 shell，以及审批和拒绝是否与这些规则一致。

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
