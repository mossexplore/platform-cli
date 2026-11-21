# 会话、Windows shell 与故障处理

## 首次确认与上下文复用

当前聊天尚无已确认上下文时，先运行 `ml context --json` 核对实际配置路径。确认它是当前平台的标准用户配置（Windows 上为 `%APPDATA%\ml-go-preview\config.json`）后，再运行 `ml auth status`。

```powershell
ml context --json
ml auth status
```

- `context` 无需登录、不访问网络，包含运行模式、上下文模式、会话 ID、当前环境、当前业务、CLI 版本和路径、实际配置路径与会话文件路径。使用 `--json`，不加 `-o json`；只查看报告的路径，不读取配置、凭据、会话或业务文件。JSON 键为“运行模式”“上下文模式”“会话 ID”“当前环境”“当前业务”“CLI 版本”“CLI 路径”“配置路径”“会话文件”等；将“当前环境”与 `auth status` 的 `profile` 对照，无需另外运行 `ml --version`、`ml env show`。
- **多会话自动隔离**：在 DeepSeek Harness（自动注入 `DSH_SHELL=1` 与 `DSH_SESSION_ID`）或设置了 `ML_SESSION_ID` 时，CLI 自动进入会话隔离模式，每个会话独立保存所选环境与租户/团队，互不覆盖全局配置或其他会话，但共享同一环境的登录凭据与业务目录。新会话默认“未绑定环境、未绑定业务”且绝不静默回退全局配置；若 `当前环境` 为 `未绑定`，先按用户要求执行 `ml env use NAME`（未指定时向用户确认，不猜测默认环境），再核对 `ml auth status` 并按需执行 `ml business use --tenant TENANT_ID [--team TEAM_ID]`。严禁在命令中手工覆写 `DSH_SESSION_ID`、`DSH_SHELL` 或 `ML_SESSION_ID`。
- `auth status` 当前仅输出表格，没有 `-o json` 选项；不续期，显示 `profile`、`username`、`status`、`remaining_minutes`、`expires_at` 和 `businessId`。必须检查 `status=valid`，不能只看退出码；`profile` 应与 `context` 的环境一致。`businessId` 读取当前生效上下文的业务 ID（会话隔离模式读取当前会话绑定，普通终端读取全局 `selected.businessId`），可用于确认业务 ID；不使用其他来源或旧字段代替。
- `businessId` 缺失、为空或为 `-` 时，先看 `context` 是否为“未绑定”，需要核对当前已选租户/团队名称时运行 `ml business show`。未选业务再进入选择流程，不在每次查询前列出全部业务。
- 在当前聊天内可复用已确认的 CLI 路径、配置来源和命令语法。会话隔离模式下与其他并行会话互不干扰；普通非隔离终端仍共用本地 CLI 状态，此时其他会话的切换可能改变生效环境或业务。
- 用户要求切换到另一环境时，运行对应的 `ml env use NAME`，再用上述两条命令更新上下文。与已确认环境相同时不重复切换；未指定环境且当前已绑定时沿用当前环境，不擅自切换。若用户给的是显示名，用 `ml env list -o json` 匹配“环境名”，取唯一匹配行的“环境标识”用于切换。未找到或匹配多行时，请用户确认环境标识。开启自动保活时，目标环境未登录或登录过期会提示运行 `ml login`。
- **Harness 自动保活**：Go CLI 支持通过 Harness 的非交互 Shell 保活，前提是当前环境已登录且已选业务。成功登录、切换环境或业务、执行业务请求后刷新登记，登记默认 30 分钟到期。用 `ml auth ping status` 查看当前环境的终端数、会话数和上次平台确认时间。手动恢复用 `ml auth ping start`，停止用 `ml auth ping stop`，停止会影响当前环境下的其他会话。
- `ml env list` 默认输出表格。加 `-o json` 返回环境数组，无可展示环境时返回 `[]`。两种格式都隐藏已确认未授权的环境，保留授权状态未知的环境。列表可显示「已授权」「登录使用中」「登录已过期」或「授权状态未知」。管理台类型显示为「搜推广工程平台」或「WiseMLOps平台」。
- 核对当前平台标准用户配置路径：Windows 为 `%APPDATA%\ml-go-preview\config.json`，macOS 为 `~/Library/Application Support/ml-go-preview/config.json`，Linux 为 `${XDG_CONFIG_HOME:-~/.config}/ml-go-preview/config.json`。首次加载内置配置时会初始化环境选择。若 `context` 报错或路径不符，停止后续操作并告知用户。

## 何时重新检查

| 场景 | 处理 |
| --- | --- |
| 用户未指定租户或团队的普通查询 | 按 CLI 当前选择执行，汇报时以能核实的实际业务为准 |
| 用户指定租户或团队 | 先用 `ml business show` 核对。当前选择不匹配时，按用户明确要求切换或请用户确认 |
| 登录、退出、切换账号或业务 | 按对应命令结果更新上下文；必要时只补查认证或业务 |
| 切换环境、CLI 路径或配置来源，上下文丢失 | 重新运行 `context --json` 与 `auth status` |
| 长任务前、长时间中断后无法确认认证状态 | 只查 `auth status`；长任务核对剩余时间是否足够，不重查版本和业务列表 |
| 认证、业务或权限失败 | 进入下方对应处理，不重新执行完整检查清单 |
| 不熟悉的命令、用法错误、文档不一致 | 查该命令 `--help`；涉及安装或版本异常再查版本和路径 |
| 提交写操作前 | 重新用 `context --json` 与 `auth status` 核对上下文模式、会话 ID、环境、账号和业务，并核对目标 ID。业务与已确认目标不一致时，停止提交并重新确认 |

聊天记录只保留本聊天的操作上下文。当前业务以 CLI 生效状态为准，其他会话或终端的切换可能使旧记录失效。CLI 每次业务调用仍执行认证、业务选择和权限检查。

## Windows shell

实际使用的 shell 以工具说明为准，不根据 Agent 名称或版本推断。以下仅提供现有 Windows 安装的调用示例，不改变工具权限或加载配置。

- **找不到 `ml`**：刚安装后请完全退出并重新打开 Agent，让它继承新 PATH。用 `where.exe ml` 核对实际入口。仍找不到时，按安装方式使用下面的绝对路径。便携包使用解压目录中的 `ml.exe`。
- **引号**：PowerShell 中含空格或反斜杠的路径用单引号包住。Windows PowerShell 5.1 和 PowerShell 7.3 之前的版本会去掉参数里嵌入的双引号；有文件参数时（如 `--from-file`、`--request-file`、`--request-sample-file`）先把文本写入本地文件再传入，必须直接传含双引号的值（如 JSON 形式的 `--customize-config`）时，在这些版本中把每个 `"` 写成 `\"`，执行后核对平台上的实际值。
- **中文乱码**：CLI 对 Windows 重定向输出使用 UTF-8；接收端仍需使用一致的解码方式。仅在发生乱码时核对实际 shell 和输出接收方式。在 PowerShell 中可按需要设置 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;` 并验证结果，不为每条命令固定添加前缀，不修改 CLI 代码解决编码问题。

Windows Git Bash 可用 `cygpath -u` 转换 `LOCALAPPDATA` 后拼接安装路径。PowerShell 中可直接调用默认安装路径：

```powershell
& "$env:LOCALAPPDATA\Programs\WiseRecCLIGo\ml.exe" context --json
```

确认配置路径后，用同一个 `ml.exe` 执行 `auth status` 和后续命令。在不同 shell 调用之间复用已确认的绝对路径。WSL 中请切换到 Windows shell 使用这套安装。

## 登录与业务选择

- **无缓存或已过期**：运行 `ml login`，为执行工具至少预留 10 分钟，工具参数名和单位以其说明为准。命令会打开 Edge，由用户完成 SSO 或验证码，之后复查 `ml auth status`。不能代替用户输入凭据，也不要靠运行业务命令来触发登录。
- **未选业务**：用 `ml business list` 取得当前环境的候选，按用户明确的选择运行 `ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID]`，按命令结果更新当前业务；输出不足以确认时，再用 `ml business show` 核对一次。必须传 `--tenant`；不传 ID 会进入交互选择，不符合本 skill 的非交互执行要求。业务 ID 不从其他环境复制。
- **业务目录缺失或失效**：`ml business refresh` 会打开 Edge 刷新目录，同样预留至少 10 分钟，刷新后重新核对选择。
- **权限调用日志**：排查授权请求时，在权限管理系统的「完整命令」核对选项、参数和顺序。Go 客户端上报全部参数值，包括敏感值与内联脚本；本地历史仍脱敏。报告日志时只摘录排查所需的内容。
- **退出登录**：`ml logout` 仅在用户要求或排障需要时运行。

## 环境禁用排查

正常执行命令，遇到权限拒绝后不重试。

- 若提示「当前环境 `<环境名>` 禁止执行」或「已由管理员禁止执行」，直接告知用户环境名和完整命令路径。
- 若提示「服务端拒绝命令」或「当前账号或命令未获授权」，且原因不明确，在同一环境运行一次 `ml tree --all`。目标命令标记为 `[当前环境禁用]` 时，告知用户该命令在此环境被禁用；标记为 `[不支持]` 时，说明当前管理台不支持该命令。
- 若命令树没有明确标记，或提示策略尚未同步，告知用户 CLI 的原始错误，并说明「暂无法确认该命令是否被当前环境禁用」。

禁用命令分组会覆盖其子命令。命令树使用已同步的策略，实际执行以实时鉴权为准。

## 失败分类

| 现象 | 下一步 |
| --- | --- |
| `ml` 不在 PATH 中 | 直接调用默认安装目录的 `ml.exe`，路径见上方示例 |
| 默认路径缺少 `ml.exe` 或版本异常 | 向用户核对安装目录和实际调用的版本 |
| `配置文件不存在` | 按上方列出的当前平台用户配置路径核对。路径不符或文件缺失时，告知用户实际路径并停止操作 |
| `安装包中缺少 config.json` 或内置配置无效 | 在报错的 Agent 终端运行 `Get-Command ml` 和 `ml --version`，核对实际调用的 CLI。若该安装缺少包内配置，用完整安装包重新安装 |
| 认证过期或缺失 | 请用户登录后复查 |
| 当前会话尚未绑定环境 | 确认用户目标环境后执行 `ml env use NAME`，再核对认证与业务 |
| 当前会话在环境下尚未选择业务或业务绑定已失效 | 用 `ml business list` 核对候选，按用户选择执行 `ml business use --tenant TENANT_ID [--team TEAM_ID]` |
| `缺少有效的 DSH_SESSION_ID` 或 `ML_SESSION_ID 无效` | 停止操作并报告实际错误，不尝试绕过或回退全局配置 |
| 未选业务 | 列候选并按用户选择设置；空结果不等于平台无数据 |
| `当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh` | 刷新当前环境的业务目录，再用 `ml business show` 核对所选业务。需要重新选择时请用户确认目标 |
| 权限拒绝 | 停止当前操作，按[环境禁用排查](#环境禁用排查)处理 |
| `CLI_VERSION_TOO_OLD` | 转告终端显示的版本要求，请用户在交互终端确认升级，或联系管理员获取安装包。开始下载时显示 MSI 地址，检查安装包后按包内版本显示文件名。终端提示无法自动升级时，按提示核对 MSI 地址、代理、权限服务或安装路径。Agent 调用不代替用户确认 |
| 权限服务证书校验失败 | 使用 `ml access status --diagnose` 核对 CA 来源；公共证书请用户或管理员在实际配置的 `access_control` 中选择 `ca_source: certifi`；私有 CA 使用 `env` 或 `custom`，不反复重试或关闭校验 |
| 拒绝确认或在默认拒绝的提示中直接回车 | 训练、克隆和部署等命令会显示对应的取消提示。交互拒绝 `history clear` 时显示“已清理 0 条历史记录”。用户仍要求执行且已授权具体目标时才传 `--yes` |
| `history clear` 提示“非交互清理必须传入 --yes” | 有记录匹配时，非交互清理需要显式确认。先核对清理范围，得到用户授权后才传 `--yes` |
| 显示“已取消操作”且退出码为 1 或 130 | 分别对应命令入口捕获的中止和键盘中断。若无法确定写请求是否已经提交，先查远端状态再决定是否重试 |
| 用法错误（退出码 2） | 查 `ml <子命令> --help` 修正调用参数，不按网络问题重试；缺失能力或程序缺陷交维护人员处理，不改码 |
| 工具超时 | 只读查询延长执行等待时间后有限重试；写操作先查远端是否已生效 |
| 网络超时 | 只读查询可有限重试；写操作先查远端状态 |
| 结果为空 | 核对环境、业务、筛选条件和分页，如实报告 |

通常退出码 0 表示命令正常退出，1 表示执行错误，2 表示参数用法错误。`jupyter exec` 和 `jupyter notebook run` 另有超时、丢失和中断状态，退出码 2 也可能表示结果未知，见 [jupyter.md](jupyter.md)。认证进度提示写入 stderr。自动登录成功会打印用户信息表，未重定向该表的命令可能将它写入 stdout。若 stdout 混有登录表格，先核对认证状态，再重新执行只读查询。

## 权限服务 CA 排障

代理与 CA 来源独立。`use_env_proxy: false` 不代表忽略证书环境变量。部分 Agent 会向子进程注入 `SSL_CERT_FILE` 或 `SSL_CERT_DIR`，导致普通 CMD 成功但 Agent 证书校验失败；不要仅凭连接错误认定是代理或权限拒绝。

`ca_source` 支持 `certifi`、`env`、`custom`：随包配置显式使用 `certifi`，忽略环境 CA 并保留 HTTPS 校验；旧外部配置省略该字段仍按 `env` 行为处理，优先 `SSL_CERT_FILE` 再 `SSL_CERT_DIR`。`custom` 需同时指定绝对路径 `ca_file`，其他模式不得带此字段。所有模式验证证书及主机名，校验失败不会切换其他信任库。

只通过诊断核对当前来源并向用户报告；配置由用户或管理员维护，不擅自修改配置、系统证书、Agent 自带证书或全局环境变量。无需给所有 ml 命令固定添加清空 CA 的 shell 前缀，不关闭证书校验或权限检查。该设置仅适用于权限服务，不承诺修复平台业务接口自身的 TLS 问题。
