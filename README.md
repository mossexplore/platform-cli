# ml CLI

`ml` 是 WiseMLOps平台的 Python 命令行客户端。Playwright 仅用于在 Microsoft
Edge 中登录；登录成功后，Cookie、CSRF Token、账号、中文名、部门和过期时间会按
profile 保存到本地。后续业务命令使用 HTTPX 请求接口。

## 安装

需要 Python 3.9 或更高版本。Windows PowerShell：

```powershell
py -m pip install --upgrade pip
py -m pip install -e .
ml --help
```

脚本使用系统安装的 Microsoft Edge，不需要运行 `playwright install chromium`。

## 配置

默认读取当前目录的 `config.json`。也可以通过全局参数或环境变量指定：

```powershell
ml --config C:\path\to\config.json env show
$env:ML_CONFIG = "C:\path\to\config.json"
```

认证默认有效 30 分钟，由秒数配置：

```json
{
  "auth": {
    "expires_in_seconds": 1800
  },
  "browser": {
    "channel": "msedge",
    "session_probe_timeout": 5000,
    "login_timeout": 300000
  }
}
```

认证信息保存在用户配置目录的 `ml/credentials.json`，不会写入项目配置或提交到
Git。每个 profile 独立保存。命令执行前会检查有效期；过期时自动打开 Edge
专用 Profile，优先复用已有平台会话，无需重复输入验证码；只有平台会话确实失效
时才要求用户重新登录。如果服务端提前返回 401 或 403，也会刷新认证并重试一次。

每个环境使用独立的持久化浏览器目录：

```text
ml/browser-profiles/profile-dev
ml/browser-profiles/profile-test
```

CLI 会自动监听 `/ai/user/info` 请求确认登录结果，用户不需要再按回车。认证成功并
更新本地认证信息后，Edge 会自动关闭，原业务命令随后继续执行。`login_timeout`
控制等待用户登录的最长时间，单位为毫秒，默认 5 分钟。

`api.verify_ssl` 是所有环境的默认 HTTPS 证书校验设置。某个可信的内部环境需要
单独关闭校验时，可在对应的 `profiles` 项中覆盖；其他环境继续继承全局设置：

```json
{
  "api": {
    "verify_ssl": true
  },
  "profiles": [
    {
      "name": "internal",
      "api_endpoint": "https://10.0.0.1/dashboard",
      "output_format": "table",
      "verify_ssl": false
    },
    {
      "name": "dev",
      "api_endpoint": "https://console-dev.cloudtest.cn/dashboard",
      "output_format": "table"
    }
  ]
}
```

关闭证书校验只应用于显式配置的环境，并且只建议用于完全可信的内部网络。

从旧版 `wo` 首次升级时，如果新的认证文件尚不存在，CLI 会自动复制旧的
`wo/credentials.json` 到 `ml/credentials.json`，原文件仍会保留。

## 命令

```powershell
ml login
ml login --show-secrets
ml logout
ml logout --all
ml logout --forget-browser
ml logout --all --forget-browser
ml auth status

ml env list
ml env show
ml env use dev

ml user info
ml user info --output json

ml mep config get
ml mep config get mep_service_access_type --output json
```

普通 `logout` 只清除 CLI 的短期认证缓存，保留 Edge 持久会话，方便下次无验证码
恢复。使用 `--forget-browser` 会同时删除专用 Edge Profile，之后可能需要重新输入
验证码。

## 增加新接口

通用认证、超时、重试和错误处理位于 `PlatformClient`。业务接口按领域放在
`src/wisemlops_cli/services/`，CLI 参数放在 `src/wisemlops_cli/commands/`。
增加接口时不要在命令模块中直接拼接 Cookie 或 URL。

```text
commands/mep.py -> services/mep.py -> client.py
```

如果后端提供 OpenAPI，可以把生成的 Python Client 放在独立的 `generated/`
目录，service 层负责适配生成代码，命令层结构无需改变。
