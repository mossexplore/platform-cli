# 会话、Windows shell 与故障处理

## 首次确认与上下文复用

当前聊天尚无已确认上下文时运行：

```powershell
ml context --json
ml auth status
```

- `context` 无需登录、不访问网络，包含运行模式、CLI 版本和路径、当前环境、实际配置路径。使用 `--json`，不加 `-o json`；只查看报告的路径，不读取配置、凭据或业务文件。它已经提供版本和环境，无需另外运行 `ml --version`、`ml env show`。
- `auth status` 不续期，显示 `profile`、`username`、`status`、`remaining_minutes`、`expires_at` 和 `businessId`。必须检查 `status=valid`，不能只看退出码；`profile` 应与 `context` 的环境一致。`businessId` 读取当前环境的 `selected.businessId`，可用于确认业务 ID；不使用其他来源或旧字段代替。
- `businessId` 缺失、为空或为 `-` 时，用 `ml business show` 核对；需要租户/团队名称时也可查询。未选业务再进入选择流程，不在每次查询前列出全部业务。
- 在当前聊天内复用已确认的 CLI 路径、配置来源、环境、账号、业务 ID 和按需取得的名称。用户发来下一条意图、重新调用 `/ml` 或再次加载 skill，都不自动使上下文失效。普通查询直接执行，已确认的命令语法也直接复用。
- 用户要求切换到另一环境时，运行对应的 `ml env use dev|mirror|explore|product`，再用上述两条命令更新上下文。与已确认环境相同时不重复切换；未指定环境时沿用已确认的当前环境，不擅自切换。
- 使用自定义配置时，`--config PATH` 放在子命令之前，例如 `ml --config 'C:\Work\config.json' context --json`；也可设置 `ML_CONFIG`。所有业务命令沿用已确认的同一配置来源，变更来源后重新确认。

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
- **Git Bash**：路径改用正斜杠或单引号，例如 `ml --config 'C:/Work/config.json' env show`。

## 登录与业务选择

- **无缓存或已过期**：运行 `ml login`，shell 工具 `timeout` 至少设为 10 分钟。命令会打开 Edge，由用户完成 SSO 或验证码，之后复查 `ml auth status`。不能代替用户输入凭据，也不要靠运行业务命令来触发登录。
- **未选业务**：用 `ml business list` 取得当前环境的候选，按用户明确的选择运行 `ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID]`，按命令结果更新当前业务；输出不足以确认时，再用 `ml business show` 核对一次。必须传 `--tenant`；不传 ID 会进入交互选择，在 shell 工具中无法完成。业务 ID 不从其他环境复制。
- **业务目录缺失或失效**：`ml business refresh` 会打开 Edge 刷新目录，`timeout` 同样至少 10 分钟，刷新后重新核对选择。
- **权限拒绝**：停止该业务操作并报告原因，可用 `ml access status` 检查。
- **退出登录**：`ml logout` 仅在用户要求或排障需要时运行。

## 失败分类

| 现象 | 下一步 |
| --- | --- |
| `ml` 不存在或版本异常 | 检查安装和 PATH，不继续业务命令 |
| 认证过期或缺失 | 请用户登录后复查 |
| 未选业务 | 列候选并按用户选择设置；空结果不等于平台无数据 |
| 权限拒绝 | 停止并告知用户或管理员，不绕过检查 |
| 输出 `Aborted!` | 先确认中止原因：输出中 `Aborted!` 前紧跟确认提示（如 `确认克隆？ [y/N]:`）时，说明请求尚未提交，用户仍要求执行才补充 `--yes`；没有确认提示或无法确定时（如用户中断），按结果未知处理，先查远端状态 |
| 用法错误（退出码 2） | 查 `ml <子命令> --help` 修正参数，不按网络问题重试 |
| 工具超时 | 只读查询加大 `timeout` 重试；写操作先查远端是否已生效 |
| 网络超时 | 只读查询可有限重试；写操作先查远端状态 |
| 结果为空 | 核对环境、业务、筛选条件和分页，如实报告 |

一般退出码：0 成功，1 执行错误，2 参数用法错误。`jupyter exec` 和 `jupyter notebook run` 另有超时、丢失和中断状态，退出码 2 也可能表示结果未知，见 [jupyter.md](jupyter.md)。平台自动刷新认证时可能向 stdout 写提示，此时不要在混合文本中猜测 JSON。
