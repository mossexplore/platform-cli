# ml CLI

`ml` 是 WiseMLOps平台的 Python 命令行客户端。Playwright 仅用于在 Microsoft
Edge 中登录；登录成功后，Cookie、CSRF Token、用户名和过期时间会按 profile
保存到本地。后续业务命令使用 HTTPX 请求接口。

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
ml --config C:\path\to\config.json profile show
$env:ML_CONFIG = "C:\path\to\config.json"
```

认证默认有效 30 分钟，由秒数配置：

```json
{
  "auth": {
    "expires_in_seconds": 1800
  }
}
```

认证信息保存在用户配置目录的 `ml/credentials.json`，不会写入项目配置或提交到
Git。每个 profile 独立保存。命令执行前会检查有效期；过期时自动打开 Edge
重新登录并覆盖该 profile 的本地认证信息。如果服务端提前返回 401 或 403，也会
强制刷新并重试一次。

从旧版 `wo` 首次升级时，如果新的认证文件尚不存在，CLI 会自动复制旧的
`wo/credentials.json` 到 `ml/credentials.json`，原文件仍会保留。

## 命令

```powershell
ml login
ml login --show-secrets
ml logout
ml logout --all
ml auth status

ml profile list
ml profile show
ml profile use dev

ml user info
ml user info --output json

ml mep config get
ml mep config get mep_service_access_type --output json
```

登录成功后认证信息会立即保存。按照当前浏览器生命周期要求，Edge 会继续保持
打开；手动关闭 Edge 后，登录命令或原业务命令继续执行。

## 增加新接口

通用认证、超时、重试和错误处理位于 `PlatformClient`。业务接口按领域放在
`src/wisemlops_cli/services/`，CLI 参数放在 `src/wisemlops_cli/commands/`。
增加接口时不要在命令模块中直接拼接 Cookie 或 URL。

```text
commands/mep.py -> services/mep.py -> client.py
```

如果后端提供 OpenAPI，可以把生成的 Python Client 放在独立的 `generated/`
目录，service 层负责适配生成代码，命令层结构无需改变。
