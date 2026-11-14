# WiseRec Platform skill

本目录提供各 Agent/harness 共用的 WiseRec CLI 操作说明，不绑定 Agent 产品或版本。当前安装流程面向 Windows，以下记录现有分发方式；未来接入不复制业务规则。本文件面向安装和分发人员，不随 skill 安装；Agent 使用的内容在 `SKILL.md` 和 `references/` 中。

## 安装

官方 Windows 安装包分两个阶段执行：先安装并验证 CLI，再安装 `wiserec-platform` skill 和 `/ml` command。第二阶段失败会显示原因，CLI 仍可正常使用；排除文件占用或目录权限问题后重新运行安装程序即可重试。直接通过 pip 安装 Wheel 不会安装 skill。正式安装提供 `/ml`。实验版已停止维护，仅在仓库 `skill-lab/` 保存历史资料，不再提供活跃的 `/ml-lab` 入口。

- 正式 skill 安装到 `~/.agents/skills/wiserec-platform` 和 `~/.cac/skills/wiserec-platform`。`/ml` 位于当前 OpenCode 配置目录的 `commands/ml.md` 和 `~/.cac/commands/ml.md`。OpenCode 配置目录默认 `~/.config/opencode`，`OPENCODE_CONFIG_DIR` 只改变该配置目录，不改变共享 skill 或 CAC 路径。
- 每次安装替换上述正式资源；成功后清理相应管理目录中的历史详细版、`ml-lab.md` 和当前 OpenCode 配置目录中的旧正式 skill。历史上使用过的其他配置目录不会被遍历。其他资源保留。
- 安装先校验资源，预校验失败保留旧文件；替换阶段失败会清理残留，不恢复已删除的旧资源。请修复问题后重跑安装程序，不把此行为视为自动回滚。
- 项目目录或兼容目录中的同名副本需自行移除，以免 OpenCode 加载旧副本。
- 安装后完全退出并重新打开 OpenCode，使其获得新的 PATH，然后输入 `/ml 查询当前业务下的模型`；只输入 `/ml` 会检查使用上下文并显示用法。

正式 Windows 安装方式见 [安装说明](../../scripts/windows/INSTALL.md)。通用正文为 `SKILL.md` 与 `references/`。`/ml` 是现有接入入口，下面的 OpenCode 权限示例供安装人员参考。

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
      "ml feature-task detail*": "allow",
      "ml feature-task execution list*": "allow",
      "ml feature-task execution logs search*": "allow",
      "ml train list*": "allow",
      "ml train detail*": "allow",
      "ml train instance list*": "allow",
      "ml train history list*": "allow",
      "ml train history detail*": "allow",
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
      "ml quality feature list*": "allow",
      "ml quality wide-featureset list*": "allow",
      "ml quality wide-featureset feature-assemble list*": "allow",
      "ml quality wide-featureset feature-assemble feature list*": "allow",
      "ml quality wide-featureset label-assemble list*": "allow",
      "ml quality wide-featureset label-assemble feature list*": "allow",
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
- 以上只列出 `ml` 相关规则，其他命令按团队要求另行配置。OpenCode 对 PowerShell 命令的解析方式（例如命令前加了编码设置时）可能影响匹配结果，正式分发前请在 OpenCode 中实测：只读命令直接执行，写操作弹出审批，被禁止的命令被拒绝。

## 操作规则与维护

会话预检、写前核对、禁止改码及异常处理统一见 [SKILL.md](SKILL.md)；字段、Windows shell 示例与排障见 [会话参考](references/session.md)。本文件不再维护另一套会话规则。

业务任务中不得修改 CLI、依赖、业务代码、脚本或 Notebook 代码单元；程序缺陷交由独立开发流程处理。该限制是 Agent 行为要求，不代表安装器已实现文件系统隔离。

命令索引由维护者运行 `python scripts/sync_skill_index.py` 生成，`--check` 检查漂移。人工语义保存在仓库 `scripts/skill_index/commands.md.in`，命令与选项存在性、叶子命令覆盖及确认列由当前 Click 命令树校验或生成。不自动推断 JSON 语义、敏感性或权限策略。

构建时在正式 `SKILL.md` 的 metadata 中写入 `source_cli_version` 和 `source_sha256`，不修改源文件中的版本。前者来自 `versions.toml`，后者标识构建前全部正式资源的内容。它们用于排查来源，不是 Agent 版本门槛；版本一致不代表加载路径或文件一定正确。

## 分发边界

skill 只是调用说明，不包含 CLI、凭据、平台配置或 Jupyter Server。不要把本机的 `config.json`、`business.json`、Cookie 或 Token 放入 skill 包。
