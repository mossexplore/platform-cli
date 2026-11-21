# Skill 目录评审与优化建议

评审对象是 `skill/` 目录（正式 skill `wiserec-platform`、`/ml` 与 `/ml-lab` 入口），使用场景限定为 Windows 机器上的 OpenCode 等开源 Agent。评审依据是仓库当前代码，结论均对照了 `src/wiserec_cli`、`setup.py`、`MANIFEST.in` 和相关测试；未能在仓库内核实的部分集中列在第 6 节。

## 1. 结论

这份 skill 的安全意识和工程基础明显好于一般水平：渐进式加载、非交互约束、写操作先核验、超时不重放、安装校验都有。主要问题不在缺规则，而在以下四点：

1. **有 4 处事实错误或自相矛盾**，其中安装路径和日志选择两处会直接误导安装人员或 Agent。
2. **参考文件混入大量面向人的表格展示细节**，Agent 按 skill 要求使用 `-o json` 时用不到，却占用上下文并稀释关键规则。
3. **权限示例可以被 skill 自己教的调用方式绕过**，凭据输出只靠文字约束，CLI 侧没有兜底。
4. **准确性靠人工逐条同步**，现有测试只查结构，查不出参数、确认提示和权限清单的漂移；也没有任何行为评测。

建议的方向是：先修事实错误，再把“能从代码生成的内容”改为生成并加测试，把“Agent 必须遵守的规则”压缩成短而硬的条目，最后用演示环境建立行为评测。

## 2. 现状

### 2.1 文件与体量

| 文件 | 字符数 | 是否随安装包分发 | 何时进入 Agent 上下文 |
| --- | --- | --- | --- |
| `skill/commands/ml.md` | 726 | 是 | 每次输入 `/ml` |
| `skill/commands/ml-lab.md` | 769 | 否 | 不会 |
| `skill/wiserec-platform/SKILL.md` | 4174 | 是 | 每次加载 skill |
| `references/commands.md` | 7185 | 是 | 按需 |
| `references/session.md` | 5270 | 是 | 按需 |
| `references/training.md` | 5019 | 是 | 按需 |
| `references/jupyter.md` | 4341 | 是 | 按需 |
| `references/data.md` | 4064 | 是 | 按需 |
| `references/services.md` | 3123 | 是 | 按需 |
| `references/deployment.md` | 2131 | 是 | 按需 |
| `skill/wiserec-platform/README.md` | 5409 | 否（仅进 sdist） | 不会 |

Agent 可见内容合计约 3.6 万字符。相邻的 `skill-lab/` 另有 107 个 Markdown 文件、约 19.6 万字符，不分发。

### 2.2 分发链路

`setup.py` 构建时把 `SKILL.md`、`references/*.md` 和 `commands/ml.md` 复制到 `wiserec_cli/opencode_resources` 并生成 SHA256 清单；`opencode_install.py` 校验后安装：

- OpenCode：skill 装到 `~/.agents/skills/wiserec-platform`，`/ml` 装到 OpenCode 配置目录的 `commands/ml.md`，并删除旧的 `~/.config/opencode/skills/wiserec-platform`。
- codeagent：skill 和 command 都装到 `~/.cac`。
- 每次安装都会删除三个位置下的 `skills/wiserec-platform-detailed` 和 `commands/ml-lab.md`。

### 2.3 做得好的地方

- **渐进式加载**：`SKILL.md` 只放通用规则，专项内容按任务读取，结构符合 skill 的通行做法。
- **非交互约束与代码一致**：确认提示、`--select`、`--no-input`、保活不生效等说明，逐条核对 `messages.confirm`、`train_logs.py`、`service_logs.py`、`ping.py` 后均成立。
- **写操作纪律**：区分“请求已接受”与“远端已完成”，超时后先查状态再决定是否重放。
- **安装器质量高**：先校验后删除、拒绝符号链接父目录、失败回滚，测试覆盖充分。
- **命令覆盖有测试**：`test_command_index_covers_every_command` 保证 105 个叶子命令都出现在 `commands.md`。

## 3. 问题清单

### 3.1 事实错误与自相矛盾（优先修复）

**问题 1：`skill/wiserec-platform/README.md` 的安装路径已过期。**

README 写 skill 安装到 `~/.config/opencode/skills/wiserec-platform`，并称“每次安装都会完整替换两个目标目录”。实际代码自 11 月 3 日起改为装到 `~/.agents/skills/wiserec-platform`，并且会**删除** README 所说的旧位置（`remove_legacy_skills`）。根目录 `README.md`、`scripts/windows/INSTALL.md` 和使用手册已是新路径，只有这一份没改。按这份 README 排查“skill 没生效”或手工分发，会找错目录。

**问题 2：`commands.md` 与 `SKILL.md` 对执行实例日志下载的说法相反。**

`commands.md` 开头写“日志编号选择需由用户在交互终端完成”；`SKILL.md` 运行约束第 2 条和 `training.md` 要求传 `--select`。代码中 `--select` 存在且可完全非交互。Agent 若先读到 `commands.md`，会放弃一个本可完成的任务。同一行的“确认”列填的是“可用 `--select` 传编号或 `all`”，与该列语义不符。

**问题 3：`/ml-lab` 处于“已退役但仍在维护”的矛盾状态。**

- 安装器把详细版称为“废弃详细版”，每次安装都删除它；但 `skill/README.md` 仍称“仓库保留的 `/ml-lab` 属于实验入口”，`ml-lab.md` 仍提示用户“单独准备实验版 skill”——即使准备了，下次安装也会被删。
- `skill-lab/wiserec-platform-detailed/SKILL.md` 开头写“这是随 CLI 安装包提供的实验性详细说明”，与事实不符。
- `skill-lab/validation/verify.py` 当前退出码为 1，报告 25 行漂移，包括 `train detail`、`feature-task detail`、`train instance logs download` 三个命令未收录。它不在测试和 CI 中运行。
- 与此同时，近期的功能提交仍在同步修改 `skill-lab`，`test_detailed_skill_is_repository_only` 还强制要求它存在。每个命令变更要改两套文档，其中一套没人用、校验也不通过。

**问题 4：权限示例漏掉 6 条只读命令。**

用 README 的规则逐条匹配命令树，`ml quality` 下的 6 个 `list` 命令全部落到 `ask`，而同类只读查询都是 `allow`。没有测试约束这份清单，新增只读命令时容易再漏。

### 3.2 影响 Agent 效果的内容问题

**问题 5：参考文件混入面向人的展示细节。**

`SKILL.md` 要求“支持 `-o json` 的命令优先用 JSON”，但参考文件里有相当篇幅在描述表格怎么画，Agent 用不到。例如：

- `training.md`：时长如何显示为 `2h37min`、`1day8h22min31s`；周期列表是“无表头四列网格，20 条为五行，7 条为两行”；交互输入时“使用中文逗号按提示重输”“输入 `q` 取消”。
- `data.md`：比例“按整数四舍五入：`0.1538 → 15%`”。
- `services.md`：表格“依次展示主机名称、机器规格、站点……”；内部如何把 `nodeId` 填入 `node.hostId`。

这些内容像是从使用手册或开发记录搬过来的。它们对 Agent 的害处有两点：占用上下文；把“任务 ID 与 JOB ID 不互换”“不自动重传”这类真正要守的规则埋在段落中间。Agent 真正需要的是 JSON 字段路径、默认分页、参数取值范围和退出码含义。

**问题 6：会话预检规则重复三到五遍。**

“首次运行 `ml context --json`，确认 `%APPDATA%\ml\config.json`，再运行 `ml auth status`，后续不重复预检”这一套，在 `ml.md`、`SKILL.md`、`session.md`、`README.md`、`ml-lab.md` 各写了一遍，`session.md` 内部又出现多次。后果有两个：

- `/ml` 每次调用都注入约 700 字符，其中大半是 `SKILL.md` 已有的内容。
- 多份副本迟早漂移，问题 2 就是这类漂移的实例。

另外，“不重复预检”在各处被反复强调，属于对某次过度预检的矫正。这种反复强调对能力较弱的模型容易造成反向问题：该重新核对时（例如写操作前）也跳过。

**问题 7：`SKILL.md` 条目过密，关键规则位置靠后。**

运行约束第 2 条一条之内包含 5 条独立规则；会话入口 5 条每条都是一整段。最重要的安全规则（`product` 环境写操作须复述并确认）在第 48 行的一个列表项中部。开源 Agent 常搭配上下文较小或指令遵循较弱的模型，长段落里的第三、第四条规则最容易被漏掉。

**问题 8：Shell 相关说明有错误和无法核实的断言。**

- `SKILL.md` 说“本 skill 示例按 PowerShell 编写”，紧接着给出的回退路径却是 cmd 语法的 `%LOCALAPPDATA%\...`，在 PowerShell 中不会展开。正确写法在 `session.md` 里，但 Agent 未必去读。
- `session.md` 称 OpenCode“通常优先选用 PowerShell，其次是 Git Bash 和 cmd”。这是对外部软件内部行为的断言，随版本变化，仓库内无从验证。更稳妥的写法是让 Agent 从 shell 工具说明判断实际 shell，不给出优先级结论。
- 中文乱码的处理没有说明适用条件。CLI 在输出被重定向时已自行切换为 UTF-8（`cli.py` 的 `configure_windows_output`），只有在 PowerShell 内部再做管道处理时才需要设置 `[Console]::OutputEncoding`。不写明条件，Agent 可能给每条命令都加前缀，这又会影响权限规则匹配（见问题 10）。

**问题 9：skill 在为 CLI 的机器可读性缺口打补丁。**

- `ml auth status` 只输出 Rich 表格，没有 JSON 选项。它是预检必跑的命令，Agent 只能从表格文本里读 `status`、`businessId`。
- `ml context` 用 `--json` 而其他命令用 `-o json`，skill 专门花一句话提醒；其 JSON 键是中文（“当前环境”“配置路径”“CLI 版本”），skill 没有列出键名，Agent 要自己对应到 `auth status` 的 `profile`。
- `featureset config` 固定输出 JSON 且不接受 `-o`，`service logs` 不支持 JSON，都需要 skill 逐个说明例外。

这些例外每一条都要靠文字教会 Agent，改 CLI 比改文档更省事也更可靠。

### 3.3 安全与权限

**问题 10：权限规则可被 skill 自己教的调用方式绕过。**

README 的规则全部以 `ml ` 开头。但 skill 同时教了三种不以 `ml ` 开头的调用方式：`& "$env:LOCALAPPDATA\...\ml.exe" ...`、Git Bash 下的 `"$ml_exe" ...`、以及前置 `[Console]::OutputEncoding = ...;`。这些写法是否还能命中 `ml *` 规则取决于 OpenCode 对命令的解析方式；一旦不命中，`ask` 和 `deny` 都不生效。README 末尾提到了“可能影响匹配结果”，但没有给出对应规则。

**问题 11：凭据输出只靠文字约束。**

`ml jupyter terminal open` 在非终端环境会被 CLI 自身拒绝（`terminal.py` 的 `require_tty`），这是可靠的兜底。但 `ml login --show-secrets` 没有同类保护，代码会直接打印 cookie 和 csrftoken；能否拦住完全取决于 skill 文字和问题 10 中可能失效的 `deny` 规则。

**问题 12：示例把含敏感信息的命令设为免审批。**

`SKILL.md` 明确说资源模板详情、部署模板详情含未脱敏的 Secret，服务日志和远端文件可能含秘密；README 的权限示例却把 `resource template detail`、`deployment template detail`、`service logs`、`jupyter files read` 全部设为 `allow`。这可以是有意的取舍，但文档没有说明。另外 `read` 规则只拒绝 `*credentials.json`，同目录的 `business.json`、`config.json`、`history.jsonl` 没有覆盖，而 `SKILL.md` 禁止读取这些文件。

**问题 13：生产保护依赖环境命名。**

“`product` 环境的写操作必须确认”依赖环境恰好叫 `product`。配置里环境只有 `name` 和 `alias`，代码中没有“受保护环境”的概念；skill 自己也说环境标识“以实际配置为准”。如果生产环境叫别的名字，这条规则不会触发。

### 3.4 工程与维护

**问题 14：测试只查结构，查不出内容漂移。**

`tests/test_skill_resources.py` 检查命令是否被提到、链接是否有效、名称是否一致。以下漂移它都发现不了，而它们都可以从 Click 命令树机械地校验：

- skill 中出现的选项（如 `--select`、`--include-history`）在 CLI 中是否存在。
- “确认”列是否与命令是否带 `--yes` 一致。
- “支持 `-o json`”的说法是否与命令是否有 `--output` 一致。
- README 权限清单是否覆盖全部只读命令。

问题 2 和问题 4 都属于这一类。

**问题 15：没有行为评测。**

`skill-lab/validation/cases.md` 自己写明“尚未进行独立模型对照评估”。skill 的每次修改（包括“不重复预检”这类行为矫正）都没有办法验证是否真的改善了 Agent 行为，也无从知道在目标模型上是否有效。

**问题 16：已安装的 skill 无法识别版本。**

安装时不复制 `manifest.json`，`SKILL.md` 里也没有版本标记。用户反馈“Agent 用了不存在的参数”时，无法判断是 skill 旧、CLI 旧，还是项目目录里有同名旧副本。

**问题 17：目录布局不清晰。**

- `skill/commands/ml-lab.md` 放在正式目录，却要靠 `MANIFEST.in`、`setup.py`、测试三处排除。
- 面向维护者的 `README.md` 放在 skill 目录内，靠安装器白名单排除，但会被 `recursive-include skill/wiserec-platform *.md` 带进 sdist。
- `metadata.platform: windows` 和 `metadata.cli` 没有任何代码读取。
- `.DS_Store` 未加入 `.gitignore`，`skill/` 下已有两个未跟踪文件。

## 4. 优化建议

### 4.1 第一步：修正事实错误

只改文档，不涉及代码，建议立即做：

1. 把 `skill/wiserec-platform/README.md` 的安装路径改为与根 README 一致，或直接删掉安装一节并链接到 `scripts/windows/INSTALL.md`，避免再出现第四份副本。
2. 删除 `commands.md` 中“日志编号选择需由用户在交互终端完成”；把 `train instance logs download` 的 `--select` 写进命令列，“确认”列留空。
3. 权限示例补上 6 条 `ml quality ... list*` 规则。
4. `SKILL.md` 中的 `%LOCALAPPDATA%` 改为 PowerShell 写法，或只写“见 session.md”。

### 4.2 第二步：对 `/ml-lab` 做出明确决定

这是需要你拍板的一项。两个选择：

- **彻底退役（建议）**：删除 `skill/commands/ml-lab.md` 和 `skill-lab/`，同步清理 `MANIFEST.in` 的 `prune skill-lab`、`test_detailed_skill_is_repository_only`、`test_package_build.py` 中的相关断言；安装器的 `remove_retired_lab` 保留，用于清理存量机器。`verify.py` 里“从命令树读取参数、默认值、取值范围”的逻辑值得保留，改造后并入正式测试（见 4.4）。
- **继续保留**：那就要把 `verify.py` 修到通过并接入 CI，改掉“随安装包提供”的说法，并说明谁在用、怎么装。

依据是：安装器已把它定性为废弃，校验已经不通过，继续双份维护没有收益。

### 4.3 第三步：重写 Agent 可见内容

**`ml.md` 缩到最小。** 只保留三件事：加载 skill、`$ARGUMENTS`、无参数时给出用法。会话规则全部由 `SKILL.md` 负责，不再复述。

**`SKILL.md` 按“硬规则在前、一条一行”重排。** 建议结构：

```markdown
## 必须遵守
1. 只用 ml，不直接调平台接口，不读写 %APPDATA%\ml 下的文件
2. 不运行：ml jupyter terminal open/attach、ml login --show-secrets、无子命令的 ml history
3. 写操作前：重新核对环境、账号、业务和目标 ID
4. 受保护环境的写操作：先向用户复述环境、目标、参数，得到确认后再执行
5. 写操作超时或中断：先查远端状态，不直接重跑
6. 需要确认的命令：用户授权具体目标后才加 --yes

## 首次使用（每个聊天一次）
## 怎么调用（shell、超时、JSON）
## 按任务读取参考文件
```

每条规则只说一件事，原因和例外放到参考文件。“不重复预检”只在“首次使用”一节说一次。

**参考文件只留 Agent 需要的信息。** 每个命令保留：可直接复制的调用示例、JSON 结果的字段路径、默认分页与上限、参数取值限制、退出码含义、副作用与核验方式。删除表格列顺序、时长与百分比的显示格式、网格布局、交互输入的行为、CLI 内部字段映射。这些内容使用手册里已有，人看手册即可。

**Shell 说明改为判断式。** 不断言 OpenCode 选哪个 shell，改为“从 shell 工具说明确认实际 shell；PowerShell 和 Git Bash 的写法分别如下”。乱码处理写明条件：仅在 PowerShell 内对 `ml` 输出做管道处理时需要。

### 4.4 第四步：能生成的生成，能测试的测试

**`commands.md` 由代码生成。** 命令路径、参数、是否带 `--yes`、是否支持 `-o json` 都能从 Click 命令树得到；只有“副作用”需要人工维护，可放在一个小的数据文件里。生成脚本加 `--check` 模式并接入测试，做法与 `scripts/sync_versions.py` 一致。这样新增命令时不再手改速查表，问题 2 这类矛盾也不会再出现。

**补充四个测试**（都只读命令树，不访问平台）：

| 测试 | 能拦住的问题 |
| --- | --- |
| skill 中每个 `--选项` 在对应命令上存在 | 参数改名或删除后文档未同步 |
| “确认”列与命令是否带 `--yes` 一致 | 问题 2 |
| 权限示例对每个叶子命令给出预期结果，且无副作用的命令都为 `allow` | 问题 4 |
| `ml.md` 与 `SKILL.md` 的字符数上限 | 内容再次膨胀 |

第三项需要一份“哪些命令只读”的清单，正好与生成 `commands.md` 用的副作用数据共用。

**构建时写入版本。** 在 `setup.py` 复制资源时，把 `versions.toml` 中的 CLI 版本写入 `SKILL.md` 的 `metadata`，源文件不手写版本。`SKILL.md` 增加一句：`ml context --json` 报告的版本与 skill 版本不一致时提示用户重新运行安装程序。

### 4.5 第五步：CLI 侧的配合改动

这些改动能删掉 skill 里的多段说明，并把安全约束从“文字”变成“代码”。它们修改的是已有命令的选项，按 `AGENTS.md` 需同步使用手册；不新增命令，不触发版本递增规则。

1. **`ml auth status` 支持 `-o json`。** 预检不再解析表格。
2. **`ml context` 同时接受 `-o json`，并考虑在 JSON 中带上认证状态和 `businessId`。** 这样首次预检从两条命令减为一条。带认证信息会让 `context` 读取凭据文件，需确认是否仍符合它“无需登录”的定位。
3. **非终端环境拒绝 `--show-secrets`。** 仿照 `require_tty` 的做法，stdin 不是终端时直接报错。
4. **环境配置增加“受保护”标记**，并在 `ml context` 中输出。skill 的规则改为“受保护环境的写操作须确认”，不再依赖名称。
5. **可选：模板详情默认脱敏**，需要原值时显式加参数。这一项改变现有输出，影响面较大，需单独评估。

### 4.6 第六步：权限示例加固

- 增加覆盖完整路径调用的规则，例如 `*ml.exe *` 和 `*ml.cmd *` 默认 `ask`，`*--show-secrets*` 和 `*jupyter terminal open*` 用不带 `ml ` 前缀的模式 `deny`。具体写法必须在目标 OpenCode 版本上实测后再定。
- `read` 规则扩大到 `%APPDATA%\ml` 下的全部状态文件。
- 对问题 12 中四条含敏感内容的命令，在 README 中写明取舍；保守做法是改为 `ask`。

### 4.7 第七步：建立行为评测

仓库已有演示环境（`scripts/demo`，`ml context` 会报告运行模式），可以在不接触真实平台的前提下跑评测：

1. 准备 15 到 20 条任务，覆盖：普通查询、分页、名称不唯一、需要 `--yes` 的写操作、超时后的处理、被禁止的命令、认证过期、未选业务。
2. 每条写明预期：应运行的命令、不应运行的命令、应向用户询问的时机。可从 `skill-lab/validation/cases.md` 挑选改写。
3. 在 Windows 上用 OpenCode 的非交互运行方式，以团队实际使用的模型执行，记录命令序列并与预期对比。
4. 改 skill 前后各跑一次。尤其要验证第 4.3 步的精简没有让行为退化。

没有这一步，后续对 skill 的任何调整都只能凭感觉。

## 5. 建议的实施顺序

| 顺序 | 内容 | 涉及范围 | 风险 |
| --- | --- | --- | --- |
| 1 | 修正 4 处事实错误（4.1） | 仅 skill 文档 | 低 |
| 2 | 决定并处理 `/ml-lab`（4.2） | 文档、测试、`MANIFEST.in` | 低 |
| 3 | 补充测试、生成 `commands.md`、写入版本（4.4） | 脚本、测试、`setup.py` | 低 |
| 4 | 建立行为评测基线（4.7） | 新增评测资料 | 低 |
| 5 | 重写 `ml.md`、`SKILL.md` 和参考文件（4.3） | skill 文档 | 中，需用评测对比 |
| 6 | CLI 侧改动与权限加固（4.5、4.6） | CLI 代码、使用手册、README | 中 |

评测基线排在重写之前，是为了让重写有对照。

## 6. 未在仓库内核实的事项

以下判断依赖 OpenCode 的实际行为，本次评审没有在 Windows 上实测，落地前需要确认：

1. OpenCode 在 Windows 上实际选用的 shell，以及是否随版本变化。
2. OpenCode 对 PowerShell 命令做权限匹配时，如何处理 `& "路径" 参数`、分号连接的多条语句和变量形式的可执行文件。问题 10 的严重程度取决于此。
3. Agent 读取 `~/.agents/skills/wiserec-platform/references/*.md` 时，是否会因文件位于项目目录之外而触发额外的目录访问审批。
4. `~/.cac` 对应的 codeagent 对 skill 和 command 的加载规则是否与 OpenCode 相同。
5. 目标模型对当前 skill 的实际遵循情况。第 3.2 节关于“长段落规则易被漏掉”的判断是经验性的，需由 4.7 的评测证实。
