# 会话、环境与故障处理

## 最短预检

在 Windows PowerShell 5.1 或 7 的普通终端中依次执行：

```powershell
ml --version
ml env show
ml auth status
ml business show
```

每步检查退出码和实际字段。若用户已明确指定环境，先 `ml env use dev|mirror|explore|product` 中的**一个具体标识**，再执行预检。不能把竖线写进实际命令。`ml --version` 成功才表示可调用；安装后找不到命令时重新打开终端，用 `Get-Command ml` 或 `where.exe ml` 核对 PATH。

`ml auth status` 仅读取本地缓存，不续期。无缓存会失败；过期可能返回退出码 0，必须看 `status` 与 `remaining_seconds`。认证有效且需要访问业务资源时，`ml business show` 必须显示当前环境有效的租户或团队选择。`auth status` 中的 `business_id` 可能是旧缓存值，以 `business show` 为准。环境切换后认证和业务选择均重新核对。

若使用自定义配置，`--config PATH` 放在子命令之前，例如 `ml --config 'C:\Work\config.json' env show`；也可用 `ML_CONFIG`。一次任务内对所有命令使用同一配置来源，避免检查和执行落到不同平台。不要在命令中打印配置或凭据内容。

## 登录与业务选择

- 无缓存或已过期：在有图形界面且安装 Edge 的 Windows 会话执行 `ml login`，让用户完成 SSO 或验证码，再复查 `ml auth status`。agent 可以启动命令并等待用户交互，但不能代替用户输入凭据，也不能假定无图形界面的终端可登录。
- 未选业务：用 `ml business list` 取得当前环境候选，按用户明确的租户/团队选择执行 `ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID]`，再 `ml business show` 核对。`--tenant` 为必选项，不能只传 team/department。业务 ID 不从其他环境复制。
- `ml business refresh` 会启动浏览器读取业务目录；仅在目录确实缺失或失效时使用。刷新后重新核对选择。
- 权限拒绝时停止该业务操作并报告原因。`ml access status` 可用于检查；除非正在排查连接问题，不运行 `--diagnose`，因为它可能显示内部地址和账号。

## 失败分类

| 现象 | 下一步 |
| --- | --- |
| `ml` 不存在或版本异常 | 检查安装、PATH 和实际命中的入口；不继续业务命令 |
| 认证过期或缺失 | 登录后复查；不要靠业务命令触发隐式 Edge 登录 |
| 未选业务 | 列候选并选择当前环境业务；不把空结果视作平台无数据 |
| 权限拒绝 | 停止并告知用户或管理员处理，不绕过检查 |
| 用法错误 | 查 `ml <子命令> --help`，修正参数，不按网络问题重试 |
| 网络超时 | 只读查询可在确认环境后有限重试；写操作先查是否已经生效 |
| 结果为空 | 核对环境、业务、筛选条件和分页；无数据时如实报告 |

`ml` 的一般退出码：0 成功，1 执行错误，2 参数用法错误。Notebook 有自己的超时和中断状态，不能仅凭 0/1/2 概括。平台自动认证刷新可能向 stdout 写提示；将其视为人类信息，不在混合文本中凭括号位置猜测 JSON。
