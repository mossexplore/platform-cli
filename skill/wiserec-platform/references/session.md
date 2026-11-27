# 会话、业务切换与 Windows PowerShell 规范

基础上下文检查与登录闭环见 [SKILL.md](../SKILL.md)；遇到报错、权限拒绝、CA 证书或保活异常见 [troubleshooting.md](troubleshooting.md)。

## 环境与业务切换补充

- **环境切换**：与当前环境相同时不重复切换；用户给中文显示名时，从 `ml env list --agent` 的 `items` 匹配“环境名”取“环境标识”（未找到或多匹配时请用户确认）。
- **租户与团队切换**：
  - 仅切租户：`ml business TENANT_ID --agent` 或 `ml business use TENANT_ID --agent`。
  - 指定团队/部门：`ml business use --tenant TENANT_ID [--team TEAM_ID] [--department DEPARTMENT_ID] --agent`。
  - 核对当前租户/团队名称：`ml business show --agent`。
  - 业务目录缺失或失效：`ml business refresh --agent`（打开 Edge，工具超时 ≥ 600 秒）。
- **退出登录**：仅在用户明确要求或排障需要时执行 `ml logout --agent`（清除登录态，保留上次业务选择）。

## Windows PowerShell 避坑

- **找不到 `ml`**：新安装后重启 Agent 继承 PATH；也可直接调用默认绝对路径并在后续调用中复用（便携包用解压目录的 `ml.exe`，WSL 切 Windows shell）：
  ```powershell
  & "$env:LOCALAPPDATA\Programs\WiseRecCLIGo\ml.exe" context --agent
  ```
- **引号规范**：含空格、反斜杠或英文逗号的值（如 `--select '1,3'`、`--directory 'D:\logs'`）**必须用单引号包住**。旧版 PowerShell（5.1 / <7.3）会剥离参数中的双引号：有文件参数时（`--from-file`、`--request-sample-file`）优先写文件传入；必须直接传 JSON 字符串（如 `--customize-config`）时把 `"` 转义为 `\"`，更新后核对平台实际值。
