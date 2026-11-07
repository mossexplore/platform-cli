# 会话、Windows shell 与故障处理

## 首次确认与上下文复用

当前聊天尚无已确认上下文时，先运行 `ml context --json` 核对实际配置路径。确认它是当前 Windows 账号的 `%APPDATA%\ml\config.json` 后，再运行 `ml auth status`。

```powershell
ml context --json
ml auth status
```

- `context` 无需登录、不访问网络，包含运行模式、CLI 版本和路径、当前环境、实际配置路径。使用 `--json`，不加 `-o json`；只查看报告的路径，不读取配置、凭据或业务文件。它已经提供版本和环境，无需另外运行 `ml --version`、`ml env show`。
- `auth status` 不续期，显示 `profile`、`username`、`status`、`remaining_minutes`、`expires_at` 和 `businessId`。必须检查 `status=valid`，不能只看退出码；`profile` 应与 `context` 的环境一致。`businessId` 读取当前环境的 `selected.businessId`，可用于确认业务 ID；不使用其他来源或旧字段代替。
- `businessId` 缺失、为空或为 `-` 时，用 `ml business show` 核对；需要租户/团队名称时也可查询。未选业务再进入选择流程，不在每次查询前列出全部业务。
- 在当前聊天内复用已确认的 CLI 路径、配置来源、环境、账号、业务 ID 和按需取得的名称。用户发来下一条意图、重新调用 `/ml` 或再次加载 skill，都不自动使上下文失效。普通查询直接执行，已确认的命令语法也直接复用。
- 用户要求切换到另一环境时，运行对应的 `ml env use NAME`，再用上述两条命令更新上下文。与已确认环境相同时不重复切换；未指定环境时沿用已确认的当前环境，不擅自切换。切换用环境标识，显示名称可通过 `ml env list` 核对。开启自动保活时，目标环境未登录或登录过期会提示运行 `ml login`。
- `ml env list` 隐藏已确认未授权的环境，保留授权状态未知的环境。列表可显示「已授权」「登录使用中」「登录已过期」或「授权状态未知」。管理台类型显示为「搜推广工程平台」或「WiseMLOps平台」。
- Agent 必须使用 Windows 用户配置 `%APPDATA%\ml\config.json`，通常对应 `C:\Users\<用户名>\AppData\Roaming\ml\config.json`。CLI 安装包内的 `wiserec_cli/config.json` 用于初始化和同步这份用户配置。若实际配置路径不符，或此文件缺失，停止后续 CLI 操作并告知用户。

## 何时重新检查

| 场景 | 处理 |
| --- | --- |
| 同一上下文下的后续普通查询 | 直接执行业务命令，不重复预检 |
| 登录、退出、切换账号或业务 | 按对应命令结果更新上下文；必要时只补查认证或业务 |
| 切换环境、CLI 路径或配置来源，上下文丢失 | 重新运行 `context --json` 与 `auth status` |
| 长任务前、长时间中断后无法确认认证状态 | 只查 `auth status`；长任务核对剩余时间是否足够，不重查版本和业务列表 |
| 认证、业务或权限失败 | 进入下方对应处理，不重新执行完整检查清单 |
| 不熟悉的命令、用法错误、文档不一致 | 查该命令 `--help`；涉及安装或版本异常再查版本和路径 |
| 提交写操作前 | 重新用 `context --json` 与 `auth status` 核对实际环境、账号、业务及目标；需要名称时补查 `business show`，保留生产写操作确认 |

上下文只用于当前聊天的操作决策，不跨账号、跨聊天共享。不能靠聊天记录发现其他终端的配置切换，也不把历史认证状态当作实时授权。CLI 自身每次业务调用的认证、业务和权限检查始终保留；skill 不增加绕过方式。

## Windows shell

实际使用的 shell 以 shell 工具说明为准。OpenCode 在 Windows 上通常优先选用 PowerShell（`pwsh` 或 Windows PowerShell），其次是 Git Bash 和 cmd；从 Git Bash 启动 OpenCode 或在配置中指定了 shell 时，可能使用该 shell。具体选择规则可能随 OpenCode 版本变化。

- **找不到 `ml`**：shell 可能不加载 PowerShell 配置文件，`ml` 应位于系统或用户 PATH 中，不依赖配置文件中的 PATH 修改。用 `Get-Command ml` 核对。刚安装 CLI 时，OpenCode 进程仍是旧的 PATH，需要完全退出并重新打开 OpenCode。
- **引号**：PowerShell 中含空格或反斜杠的路径用单引号包住。Windows PowerShell 5.1 和 PowerShell 7.3 之前的版本会去掉参数里嵌入的双引号；有文件参数时（如 `--from-file`、`--request-file`、`--request-sample-file`）先把文本写入本地文件再传入，必须直接传含双引号的值（如 JSON 形式的 `--customize-config`）时，在这些版本中把每个 `"` 写成 `\"`，执行后核对平台上的实际值。
- **中文乱码**：在同一条命令前加 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;` 再运行 `ml`。

## 登录与业务选择

- **无缓存或已过期**：运行 `ml login`，shell 工具 `timeout` 至少设为 10 分钟。命令会打开 Edge，由用户完成 SSO 或验证码，之后复查 `ml auth status`。不能代替用户输入凭据，也不要靠运行业务命令来触发登录。
- **未选业务**：用 `ml business list` 取得当前环境的候选，按用户明确的选择运行 `ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID]`，按命令结果更新当前业务；输出不足以确认时，再用 `ml business show` 核对一次。必须传 `--tenant`；不传 ID 会进入交互选择，在 shell 工具中无法完成。业务 ID 不从其他环境复制。
- **业务目录缺失或失效**：`ml business refresh` 会打开 Edge 刷新目录，`timeout` 同样至少 10 分钟，刷新后重新核对选择。
- **权限拒绝**：停止该业务操作并报告原因，可用 `ml access status` 检查。环境策略可禁用单个命令或整个命令分组，禁用分组会覆盖其子命令。`ml tree --all` 显示已知的 `[当前环境禁用]` 和平台的 `[不支持]` 标记。树使用已同步的服务端策略，实际执行以实时鉴权为准。
- **退出登录**：`ml logout` 仅在用户要求或排障需要时运行。

## 失败分类

| 现象 | 下一步 |
| --- | --- |
| `ml` 不存在或版本异常 | 检查安装和 PATH，不继续业务命令 |
| `配置文件不存在` | 核对当前 Agent 账号的 `%APPDATA%\ml\config.json`。如果报错路径不同，告知用户实际路径并停止操作 |
| `安装包中缺少 config.json` | 在报错的 Agent 终端运行 `Get-Command ml` 和 `ml --version`，核对实际调用的 CLI。若该安装缺少包内配置，用完整安装包重新安装 |
| 认证过期或缺失 | 请用户登录后复查 |
| 未选业务 | 列候选并按用户选择设置；空结果不等于平台无数据 |
| 权限拒绝 | 停止并告知用户或管理员，不绕过检查 |
| 权限服务证书校验失败 | 使用 `ml access status --diagnose` 核对 CA 来源；公共证书请用户或管理员在实际配置的 `access_control` 中选择 `ca_source: certifi`；私有 CA 使用 `env` 或 `custom`，不反复重试或关闭校验 |
| 输出 `Aborted!` | 先确认中止原因：输出中 `Aborted!` 前紧跟确认提示（如 `确认克隆？ [y/N]:`）时，说明请求尚未提交，用户仍要求执行才补充 `--yes`；没有确认提示或无法确定时（如用户中断），按结果未知处理，先查远端状态 |
| 用法错误（退出码 2） | 查 `ml <子命令> --help` 修正参数，不按网络问题重试 |
| 工具超时 | 只读查询加大 `timeout` 重试；写操作先查远端是否已生效 |
| 网络超时 | 只读查询可有限重试；写操作先查远端状态 |
| 结果为空 | 核对环境、业务、筛选条件和分页，如实报告 |

一般退出码：0 成功，1 执行错误，2 参数用法错误。`jupyter exec` 和 `jupyter notebook run` 另有超时、丢失和中断状态，退出码 2 也可能表示结果未知，见 [jupyter.md](jupyter.md)。平台自动刷新认证时可能向 stdout 写提示，此时不要在混合文本中猜测 JSON。

## 权限服务 CA 排障

代理与 CA 来源独立。`use_env_proxy: false` 不代表忽略证书环境变量。部分 Agent 会向子进程注入 `SSL_CERT_FILE` 或 `SSL_CERT_DIR`，导致普通 CMD 成功但 Agent 证书校验失败；不要仅凭连接错误认定是代理或权限拒绝。

`ca_source` 支持 `certifi`、`env`、`custom`：随包配置显式使用 `certifi`，忽略环境 CA 并保留 HTTPS 校验；旧外部配置省略该字段仍按 `env` 行为处理，优先 `SSL_CERT_FILE` 再 `SSL_CERT_DIR`。`custom` 需同时指定绝对路径 `ca_file`，其他模式不得带此字段。所有模式验证证书及主机名，校验失败不会切换其他信任库。

只通过诊断核对当前来源并向用户报告；配置由用户或管理员维护，不擅自修改配置、系统证书、Agent 自带证书或全局环境变量。无需给所有 ml 命令固定添加清空 CA 的 shell 前缀，不关闭证书校验或权限检查。该设置仅适用于权限服务，不承诺修复平台业务接口自身的 TLS 问题。
