# 故障排查、环境禁用与保活排障

仅在命令报错、权限拒绝、证书失败或保活异常时查阅本文档。

## 1. 环境禁用与权限拒绝排查

遇到权限拒绝后**不要重试**，按报错信息处理：

- 提示「当前环境 `<环境名>` 禁止执行」或「已由管理员禁止执行」：直接告知用户环境名和完整命令路径。
- 提示「服务端拒绝命令」或「当前账号或命令未获授权」且原因不明：在同一环境执行一次 `ml tree --all --agent`，检查目标命令的 `availability`：
  - `disabled`：告知用户该命令在此环境被禁用；
  - `unsupported`：说明当前管理台（WiseRec / MLOps）不支持该命令；
  - 无标记或策略未同步：报告原始错误，说明暂无法确认是否被环境禁用。

禁用分组会覆盖其子命令；实际执行以服务端实时鉴权为准。

## 2. 常见失败分类速查

| 现象 | 下一步 |
| --- | --- |
| `ml` 不在 PATH 中 | 用默认路径 `& "$env:LOCALAPPDATA\Programs\WiseRecCLIGo\ml.exe"` |
| `配置文件不存在` 或路径不符 | 告知用户实际配置路径并停止 |
| `安装包中缺少 config.json` / 内置配置无效 | 查 `Get-Command ml` 与 `ml --version`，请用户用完整安装包重装 |
| 认证过期或缺失 | 引导并执行 `ml login --agent`（预留 ≥ 600 秒） |
| 当前会话未绑定环境 | 确认目标环境后执行 `ml env use NAME --agent` |
| `ml env use` 报“本地状态正在使用” | 同会话运行 `ml context --agent`；仍在原环境时稍后重试 |
| 未选业务或业务绑定失效 | `ml business list --agent` 查候选并按用户选择绑定 |
| `selected.businessId 与业务目录不一致` | 运行 `ml business refresh --agent` 后用 `ml business show --agent` 核对 |
| `缺少有效的 DSH_SESSION_ID` / `ML_SESSION_ID 无效` | 停止并报告原始错误，不绕过或回退全局配置 |
| `CLI_VERSION_TOO_OLD` | 转告版本要求，请用户在交互终端升级或联系管理员；Agent 不代确认 |
| 权限服务证书校验失败 | 运行 `ml access status --diagnose --agent` 核对 CA 来源（见第 4 节） |
| `history clear` 报“非交互清理必须传入 --yes” | 先核对清理范围，获用户明确授权后再传 `--yes` |
| 退出码 2（用法错误） | **优先按 stderr 中的 `[提示]`/`[用法]`/`[选项]` 直接修正**，仍不明确时再查 `--help`；不按网络问题重试 |
| 显示“已取消操作”（退出码 1/130）或超时/断连 | 只读查询可有限重试；**写操作先查远端状态再决定是否重试** |
| 结果为空 | 核对环境、业务、筛选条件与分页，如实报告 |
| “插件尚未登记” / “插件调度已过期” / “自动保活未能确认启动” | 运行 `ml auth ping status --agent` 核对（见第 3 节） |

通常退出码 `0` 正常、`1` 执行错误、`2` 用法错误（`jupyter exec` / `notebook run` 的特殊退出码见 [jupyter.md](jupyter.md)）。认证进度写 stderr；若旧版登录输出混入 stdout，先核对认证状态再重跑只读查询。

## 3. 自动保活与 Harness 插件状态

- 交互终端使用 CLI 后台保活；DeepSeek Harness 使用宿主保活插件（同一环境有符合条件的 Harness 会话时插件优先，终端进程待命并在会话关闭或插件过期后接手）。
- 用 `ml auth ping status --agent` 查看调度状态、插件报到时间与上次平台确认成功时间；`ml auth ping stop --agent` 停止当前环境保活，`ml auth ping start --agent` 恢复。
- Harness 会话行标识：绿=正常，红=登录过期，黄=暂未确认，灰=待检查/暂停。
- **Agent 不直接调用插件协议 `ml auth ping tick --json`**。
- Edge 兼容说明：登录/刷新若见 `unknown IPAddressSpace value: Private` 或“还原页面”提示，以命令最终退出码与结果为准。
- 权限调用日志：Go 客户端上报完整参数值（本地历史已脱敏），排查时在权限系统「完整命令」核对，回复时仅摘录必要内容。

## 4. 权限服务 CA 证书排障

代理与 CA 来源独立（`use_env_proxy: false` 不忽略证书环境变量）。部分 Agent 会向子进程注入 `SSL_CERT_FILE` / `SSL_CERT_DIR`，导致普通终端成功而 Agent 证书校验失败，勿误判为代理或权限拒绝。

- `ca_source` 可选：`certifi`（随包默认，忽略环境 CA）、`env`（优先 `SSL_CERT_FILE` 再 `SSL_CERT_DIR`）、`custom`（需配绝对路径 `ca_file`）。
- 仅通过 `ml access status --diagnose --agent` 核对并向用户报告；由用户/管理员修改配置，**禁止关闭证书校验或擅自改环境/系统证书**。
