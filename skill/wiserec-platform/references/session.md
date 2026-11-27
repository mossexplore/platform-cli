# 会话、登录与 Windows PowerShell 规范

## 1. 登录与会话最短流程

```powershell
ml context --agent                  # 一步核对路径、环境、业务与登录状态
ml env list --agent                 # 未绑定环境时查候选
ml env use NAME --agent             # 切换环境（传入环境标识）
ml login --agent                    # 未登录/过期时打开 Edge 登录（工具超时 ≥ 600s）
ml auth status --agent              # 写操作/长任务/跨租户前核对角色与剩余有效期
ml business list --agent            # 未绑定业务时查候选
ml business TENANT_ID --agent       # 绑定租户（选团队加 use --tenant ID --team ID）
```

### 核心规则
- **标准配置路径核对**：Windows 为 `%APPDATA%\ml-go-preview\config.json`，macOS 为 `~/Library/Application Support/ml-go-preview/config.json`，Linux 为 `${XDG_CONFIG_HOME:-~/.config}/ml-go-preview/config.json`。若 `context` 报错或路径不符，立即停止并告知用户。
- **多会话自动隔离**：DeepSeek Harness（自动注入 `DSH_SHELL=1` 与 `DSH_SESSION_ID`）或 `ML_SESSION_ID` 下，每个会话独立维护环境与业务，新会话默认 `未绑定` 且绝不回退全局配置，但共享同环境的登录凭据与业务目录。严禁篡改上述环境变量。
- **只读与写操作分流**：
  - 普通只读查询：`ml context --agent` 已显示环境/业务已绑定且 `登录状态=有效` 时直接查询，省去 `auth status`。
  - 写操作、长任务、跨租户（`-A`）：必查 `ml auth status --agent`，核对 `status=valid`、`profile` 与 `context` 一致、`remaining_minutes` 充足、`role` 满足跨租户要求。
- **登录细节（`ml login --agent`）**：
  - 会打开专用 Edge 由用户完成 SSO/验证码，**执行工具超时至少设为 10 分钟（600 秒）**。
  - 每次登录自动优先恢复同账号在同环境/同平台仍有效的上次业务选择；无有效选择时依次回退 Edge 缓存 `ai-businessId` 或 `scopePermissions` 首个租户。
  - 登录返回 JSON 已含环境、账号、角色和 `businessId`，有效时直接继续业务操作，不必再查 `business list`。
  - 禁止 `--show-secrets`；禁止靠运行业务命令触发登录；禁止代替用户输入凭据。
- **环境切换**：与当前环境相同时不重复切换；用户给中文显示名时从 `ml env list --agent` 的 `items` 匹配“环境名”取“环境标识”（未找到或多匹配时请用户确认）。`env list` 未登录时仅显示默认可见环境，登录后额外显示获授权环境。
- **业务切换与刷新**：
  - 仅按租户切换：`ml business TENANT_ID --agent` 或 `ml business use TENANT_ID --agent`。
  - 指定团队/部门：`ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID] --agent`。
  - 核对当前租户/团队名：`ml business show --agent`。
  - 业务目录缺失或提示与目录不一致：`ml business refresh --agent`（同样打开 Edge，超时 ≥ 600 秒）。
- **退出登录**：仅在用户明确要求或排障需要时执行 `ml logout --agent`（清除登录态，保留上次业务选择）。

## 2. 何时重新检查

| 场景 | 动作 |
| --- | --- |
| 未指定租户/团队的只读查询 | 沿用当前会话已确认上下文，无需重复预检 |
| 用户指定了租户或团队 | 用 `ml business show --agent` 核对；不匹配时按授权切换或确认 |
| 切换环境或上下文丢失 | 重新执行 `ml context --agent`（写操作前补 `ml auth status --agent`） |
| 长任务前、长时间中断后 | 仅查 `ml auth status --agent` 核对 `remaining_minutes` |
| 提交写操作前 | 核对 `ml context --agent` 与 `ml auth status --agent` 的环境、账号、业务及目标 ID |
| 报错或权限/证书/保活异常 | 按需查阅 [troubleshooting.md](troubleshooting.md) |

## 3. Windows PowerShell 调用规范

- **找不到 `ml`**：刚安装后重启 Agent 继承新 PATH；用 `where.exe ml` 核对，或直接调用默认绝对路径并在后续调用中复用：
  ```powershell
  & "$env:LOCALAPPDATA\Programs\WiseRecCLIGo\ml.exe" context --agent
  ```
  便携包使用解压目录中的 `ml.exe`。WSL 中请切换到 Windows shell。
- **引号规范**：PowerShell 中含空格、反斜杠或英文逗号（如 `--name 'NAME,NAME'`、`--select '1,3'`）的值**必须用单引号包住**。旧版 PowerShell（5.1 / <7.3）会剥离参数中的双引号：有文件参数时（`--from-file`、`--request-sample-file`）优先写文件传入；必须直接传 JSON 字符串（如 `--customize-config`）时将 `"` 转义为 `\"`，更新后核对平台实际值。
- **UTF-8 编码**：CLI 重定向输出为 UTF-8，仅实际出现中文乱码时核对 shell 编码，不为每条命令固定加编码前缀。
