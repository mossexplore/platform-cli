# Jupyter WebSocket 诊断脚本

在出现故障的机器上，使用安装 `ml` 的同一个 Python 环境运行
`diagnose_jupyter_ws.py`。脚本复用该环境实际导入的 CLI 配置、认证、业务选择和
WebSocket 实现，不需要复制 Token。启动时可能按 CLI 原有流程提示管理台认证，
并可能更新本地凭据及连接缓存。

先用 `ml jupyter terminal list` 确认已有终端名称，再运行：

```bash
python diagnose_jupyter_ws.py --studio-id ENV_ID --terminal NAME --output jupyter-ws-report.json
```

从仓库根目录运行时，脚本路径为 `scripts/diagnose_jupyter_ws.py`。
可将这个 Python 文件单独复制到故障机器，无需安装脚本额外依赖；原 CLI 依赖必须完整。
若 `python` 与 `ml` 不属于同一安装环境，请使用该 CLI 环境中 Python 的完整路径。

可选参数：

| 参数 | 含义 |
| --- | --- |
| `--config PATH` | 与 `ml --config PATH` 使用同一个配置文件；省略时沿用 `ML_CONFIG` 或默认规则 |
| `--studio-id ENV_ID` | 指定实例；省略时使用当前选择的实例 |
| `--terminal NAME` | 指定已有终端；省略时只检查 HTTP，不尝试 WebSocket，返回退出码 1 并提示补充终端名称 |
| `--output PATH` | 保存 UTF-8 JSON 报告，拒绝覆盖已有文件；省略时仅输出到控制台 |

报告包含北京时间、Python/CLI/依赖信息、代理及 CA 环境变量是否存在、
HTTP 检查和 WebSocket 握手耗时、目标地址、Origin、认证信息是否存在、
底层异常链的类型及可用错误码。报告不会包含 Token、Cookie 值、原始异常正文、
响应头或响应体；URL 去掉用户凭据、查询参数和片段。报告仍包含域名、实例路径、
当前环境名及本地 Python/模块路径，转发前按组织要求检查这些信息。

脚本只查询终端并短暂连接指定终端，随后断开；不创建、删除终端，不发送 Shell 输入。
复用的 CLI 连接实现决定实际认证及代理行为，报告中的策略描述对应本仓库当前实现。
退出码 0 表示 HTTP 和握手成功，1 表示失败或缺少有效终端，130 表示用户取消。
握手成功不代表已验证完整 Shell 交互，也不能排除间歇性故障。

常见结果：

| 结果 | 下一步 |
| --- | --- |
| `SSLCertVerificationError` | 核对企业 CA、证书链和主机名；检查 `jupyter.ca_file` |
| `gaierror` | 比较本机 DNS 与浏览器代理/PAC 的解析路径 |
| 超时、连接重置 | 按报告时间查网关及 Jupyter 日志，确认访问路径与后端状态 |
| HTTP 401/403 | 比较浏览器与 CLI 的 Cookie、Token、Origin、权限和版本策略 |
| HTTP 3xx | 核对登录跳转和目标路径；当前 CLI 禁止 WebSocket 跟随重定向 |
| HTTP 404 | 核对实例路径及终端是否仍存在 |
| HTTP 502/503/504 | 检查网关到后端的 WebSocket 转发 |

如需排除缓存因素，可另外执行 `ml webstudio login ENV_ID --refresh`，
然后用新的报告文件名再次诊断。脚本本身不会主动强制刷新缓存。
浏览器对照时，在开发者工具 Network → WS 中比较成功请求的域名、端口、路径、
Origin 和响应状态；不要复制认证值到报告。
