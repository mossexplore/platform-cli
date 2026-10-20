# WiseRec Platform skill

本目录是供 Windows 上的 OpenCode 使用的 Agent Skill，指导 Agent 通过 WiseRec `ml` CLI 操作平台。本文件面向安装和分发人员，不随 skill 安装；Agent 使用的内容在 `SKILL.md` 和 `references/` 中。

## 安装

官方 Windows 安装包分两个阶段执行：先安装并验证 CLI，再写入并核对权限规则，通过后才安装 `wiserec-platform` skill 和 `/ml` command。权限步骤失败时不会安装新的 skill 和 `/ml` command，已经存在的旧版本保持原样。替换前会先备份旧的 skill 和 `/ml` command；复制失败时恢复这份备份，并把这次的权限改动从备份恢复。已有的 `wiserec-managed.json` 按安装前的字节写回，只有这次新建的清单才删除。回滚失败时会说明可能留下的规则和备份路径。安装程序显示失败原因和下一步。CLI 仍可正常使用；按提示处理后再运行安装程序即可重试。直接通过 pip 安装 Wheel 不会安装 skill。

- 默认目标为当前用户的 `~/.config/opencode`，设置 `OPENCODE_CONFIG_DIR` 时使用该目录。
- 每次成功安装都会在备份之后替换旧的 `skills/wiserec-platform` 目录和 `commands/ml.md`，再完整写入随包资源。这两处由安装程序管理，请勿直接修改；其他 skill 和 command 不受影响。
- 同一目录下的 `opencode.json` 会被合并写入权限规则。若目录里只有 `opencode.jsonc` 且内容是严格 JSON，则改写该文件，因为 OpenCode 会在 `opencode.json` 之后加载它。两个文件同时存在时安装停止，原文件保持不变。配置含注释、不是严格 JSON，或 OpenCode 版本无法识别时，安装以错误结束，不改原文件，也不替换已经存在的 skill 和 `/ml` command。权限规则核对通过后才复制这两处；复制前先备份旧文件，复制失败时恢复这份备份，并把这次写入的配置从备份恢复。同目录已有的 `wiserec-managed.json` 按安装前的字节写回，只有这次新建的清单才删除。回滚失败时会说明可能留下的规则和备份路径。与要写入的键同名时，安装程序的值直接生效：`"*": "ask"` 仍放在第一项，其他被覆盖的键移入末尾的受管理规则。每个被覆盖的键都会醒目打印原值和新值，原值留在同目录的 `wiserec-managed.json` 和备份中。首次写入前把原文件备份为 `opencode.json.bak` 或 `opencode.jsonc.bak`；该备份已存在时不再覆盖，另写带时间戳的备份。备份可能含有 API 密钥。备份从创建起就只允许当前用户读写。其他系统权限为 `0600`。Windows 上用 `whoami` 得到的 `DOMAIN\user` 调用 `icacls`；`icacls` 或 `whoami` 失败时会警告。
- 配置文件里不写 `wiserec` 或其他非 schema 键。受管理的键、原值和安装程序版本记在同目录的 `wiserec-managed.json`，并保存写入内容的 SHA-256。模型、插件、不冲突的用户权限规则、`permission.bash` 和 `permission.shell` 都保留。不是同一条键的 `ml*` 放行会保留并列出警告，不删除。OpenCode 2 里 `permission.bash` 的 `"*": "allow"` 会保留，但受管理的 shell `"*": "ask"` 写在后面，没有被更后规则命中的命令按确认处理。v2 数组顺序是用户的非 shell 规则、`shell` `"*": "ask"`、用户的 shell 规则，然后才是受管理规则。重复安装不会追加重复的受管理规则，也不再打印已经接管的键。安装输出会列出本次写入和从旧标记迁出的规则。`python -m wiserec_cli.opencode_install --uninstall` 删掉新增的键，并按清单恢复被覆盖的原值。`wiserec-managed.json` 缺失或损坏时会明确警告，并只删除与 WiseRec 规则完全一致的条目，逐条说明无法恢复的原值；效果不同的用户规则保留。安装时若清单缺失且配置里已有这些规则，或清单损坏，也会警告。
- 项目目录或兼容目录中的同名副本需自行移除，以免 OpenCode 加载旧副本。
- 安装后完全退出并重新打开 OpenCode，使其获得新的 PATH，然后输入 `/ml 查询当前业务下的模型`；只输入 `/ml` 会检查使用上下文并显示用法。

手工分发时，把 `SKILL.md` 和 `references/` 复制到 `skills/wiserec-platform`，并把仓库中的 `skill/commands/ml.md` 复制到 OpenCode 的 `commands/ml.md`，再把下面的权限规则合并进 `opencode.json`。

## 权限配置

规则面向 Windows 上的 OpenCode。OpenCode 在这里默认使用 PowerShell 执行 shell 工具。规则按最后一条命中生效，匹配不区分大小写，并把反斜杠当作 `/`。

安装程序只执行 `opencode --version`。主版本号大于等于 2 时写入 `{action, resource, effect}` 的 `permissions` 数组，受管理规则放在最后。能加载该数组的最低版本是 `@opencode/cli` 2.1.0。OpenCode 1.x 全部拒绝顶层 `permissions`：v1.18.35 与当前 GitHub Release v1.19.3 在 `packages/opencode/src/config/v2-compat.ts` 第 94–113 行报 “V2 permissions are not supported by OpenCode V1. Use V1 permission rules or run opencode2.”，更早的 1.x 报 Unrecognized key。1.1.1 至 1.x 把规则写入 `permission.bash` 对象。这个下限来自 v1.1.1 `packages/opencode/src/config/config.ts`：`permission.bash` 已是 `PermissionRule`（第 388–405 行），顶层配置 `.strict()`（第 947 行）会拒绝未知顶层键；`permission` 的 `.catchall(PermissionRule)` 接受 `skill`。v1.16.0 至 v1.18.15 的 `packages/opencode/src/config/parse.ts` 用 `topLevelExtraKeys` 抛出 `Unrecognized key`，v1.18.16 起改为 `onExcessProperty: "ignore"`。所以 `opencode.json` 里不能保留 `wiserec` 键。受管理的键和原值记在同目录的 `wiserec-managed.json`。v1.19.3 `packages/opencode/src/permission/index.ts` 第 28–38 行按键插入顺序取最后一条命中（`findLast`，`fromConfig` 按 `Object.entries` 展开），任一子命令被拒绝则整条命令被拒绝。内置默认是 `"*": "allow"`，所以还没有 `"*"` 时必须把 `"*": "ask"` 插在第一项。与受管理规则同名的键直接改成安装程序的值，并醒目打印原值和新值。`"*": "ask"` 仍放在第一项，其他被覆盖的键进入末尾的受管理规则，并保持这些规则之间的相对顺序。相等或更严的同名键同样覆盖。不冲突的用户键保持原样。精确 allow、随后的 ask、`--help` allow 和 deny 按这个相对顺序追加在最后。低于 1.1.1，或无法从 `opencode --version` 读出版本时，安装停止，不改任何配置。两种模式都不搬移、不删除用户已有的 `permission.bash` 和 `permission.shell`。写入后用 `opencode debug config` 加载该目录（v1.19.3 `packages/opencode/src/cli/cmd/debug/config.ts`；设置 `OPENCODE_CONFIG_DIR`，并设置 `OPENCODE_DISABLE_PROJECT_CONFIG=1`），并核对每条受管理规则和 v1 的键顺序。退出码非 0、找不到该命令、输出不是配置 JSON，或少了受管理规则时，从备份恢复原文件。失败信息只包含退出码和第一行错误，并隐去 key、token、secret、password、cookie、set-cookie、csrftoken、sessionid，以及 Authorization 和 Proxy-Authorization 从冒号到行尾的 Bearer 和 Basic。只有项目或 Agent 配置里确实有可能盖过这些规则的条目时才警告。全局配置里 `agent.<name>.permission.bash` 的宽泛 allow，以及 Agent markdown 里的 `bash: allow`，也会警告。

`shell` 的 `"*": "ask"` 作用于所有 shell 命令，不只是 `ml`。只有完整、无额外参数的已知只读 `ml` 命令被精确 `allow`。放行规则不含 `*`。`--help` 只放行下表中的几条完整命令。带 ID、`-o json` 或其他额外参数的命令，以及以后新增的命令，都回到审批。

OpenCode 2 先评估 `permission.bash`，再评估 `permissions` 数组，所以数组里的 shell `"*": "ask"` 会盖过 bash 里保留的 `"*": "allow"`，除非后面还有更具体的规则命中。项目配置和 Agent 规则加载在全局文件之后，只有其中确有可能盖过受管理规则的条目时，安装程序才警告。`@opencode/cli` 2.1.0 的 `packages/core/src/permission.ts` 在 `evaluateInput` 里先检查已配置规则：结果为 deny 就拒绝，已保存的“始终允许”只追加在后面，所以它可以覆盖 ask，不能覆盖 deny。不要对 `ml` 命令点“始终允许”。OpenCode 1 的 `reply` 会把这次放行写进内存中的 `approved`，模式是 `ml *`，`ask` 在配置规则之后再匹配它，所以连 deny 也会被盖过，直到重新打开 OpenCode。命令中出现 TAB 时，整条命令都会跳过权限检查，包括只有一条命令的情况；这是上游已知问题，记录在 #9。

放在精确放行之后、仍然要求审批的模式：

- `ml jupyter exec*`
- `ml * --yes*` 与 `ml * -y*`
- `ml env use product*`
- `ml model deploy*`
- `ml train start*`
- `* > *` 与 `* >> *`

被拒绝的模式：`ml login --show-secrets*`、`ml jupyter terminal open*`、`ml jupyter terminal attach*`，以及 shell 中用 `cat`、`type`、`gc`、`Get-Content`、`sls`、`findstr`、`Copy-Item` 等方式读取 `credentials.json`。文件名规则是 `*credentials.json*`。

`[IO.File]::ReadAllText` 和 `${路径}` 不是 OpenCode 能拆出来的命令。扫描结果为空时，OpenCode 不做权限检查，所以上述规则拦不住这两种读法。不要用它们读取凭据。凭据改为 Windows DPAPI 加密存储由单独事项处理，本安装程序不实现 DPAPI。

下面是 OpenCode 2 全新安装时写入的 `opencode.json`。规则只含 schema 字段，不带 `wiserec`。`"*": "ask"` 作用于所有 shell 命令。OpenCode 1.1.1 至 1.x 改为写入 `permission.bash`：没有 `"*"` 时第一项是 `"*": "ask"`，ask 与 deny 在用户键之后。

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
