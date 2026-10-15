# 会话、Windows shell 与故障处理

## 最短预检

```powershell
ml --version
ml env show
ml auth status
ml business show
```

逐条检查退出码和实际字段。用户指定了环境时，先运行 `ml env use dev`、`ml env use mirror`、`ml env use explore` 或 `ml env use product` 中对应的一条。切换环境后重新核对认证和业务。

- `ml --version` 成功才说明 `ml` 可调用。
- `ml auth status` 只读本地缓存、不续期；无缓存会失败，过期也可能退出 0，必须看 `status` 与 `remaining_seconds`。
- `ml business show` 必须显示当前环境有效的租户或团队。`auth status` 中的 `business_id` 可能是旧值，不作依据。
- 使用自定义配置时，`--config PATH` 放在子命令之前，例如 `ml --config 'C:\Work\config.json' env show`；也可设置 `ML_CONFIG`。同一任务内所有命令使用同一配置来源。

## Windows shell

实际使用的 shell 以 shell 工具说明为准。OpenCode 在 Windows 上通常优先选用 PowerShell（`pwsh` 或 Windows PowerShell），其次是 Git Bash 和 cmd；从 Git Bash 启动 OpenCode 或在配置中指定了 shell 时，可能使用该 shell。具体选择规则可能随 OpenCode 版本变化。

- **找不到 `ml`**：shell 可能不加载 PowerShell 配置文件，`ml` 应位于系统或用户 PATH 中，不依赖配置文件中的 PATH 修改。用 `Get-Command ml` 核对。刚安装 CLI 时，OpenCode 进程仍是旧的 PATH，需要完全退出并重新打开 OpenCode。
- **引号**：PowerShell 中含空格或反斜杠的路径用单引号包住。Windows PowerShell 5.1 和 PowerShell 7.3 之前的版本会去掉参数里嵌入的双引号；有文件参数时（如 `--from-file`、`--request-file`）先把文本写入本地文件再传入，必须直接传含双引号的值（如 JSON 形式的 `--customize-config`）时，在这些版本中把每个 `"` 写成 `\"`，执行后核对平台上的实际值。
- **中文乱码**：在同一条命令前加 `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;` 再运行 `ml`。
- **Git Bash**：路径改用正斜杠或单引号，例如 `ml --config 'C:/Work/config.json' env show`。

## 登录与业务选择

- **无缓存或已过期**：运行 `ml login`，shell 工具 `timeout` 至少设为 10 分钟。命令会打开 Edge，由用户完成 SSO 或验证码，之后复查 `ml auth status`。不能代替用户输入凭据，也不要靠运行业务命令来触发登录。
- **未选业务**：用 `ml business list` 取得当前环境的候选，按用户明确的选择运行 `ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID]`，再用 `ml business show` 核对。必须传 `--tenant`；不传 ID 会进入交互选择，在 shell 工具中无法完成。业务 ID 不从其他环境复制。
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
