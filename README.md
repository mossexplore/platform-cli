# ml CLI

> WiseMLOps 平台的官方 Python 命令行客户端。

`ml` 是 [WiseMLOps](https://github.com/mossexplore/platform-cli) 平台的命令行客户端（要求 Python 3.9+）。它基于 [Typer](https://typer.tiangolo.com/) 构建，使用 [Playwright](https://playwright.dev/) 在 Microsoft Edge 中完成登录；登录成功后，Cookie、CSRF Token、账号、中文名、部门和过期时间会按 profile 保存到本地，后续业务命令使用 [HTTPX](https://www.python-httpx.org/) 请求平台接口。

![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

## 特性

- **统一登录与多环境**：通过 Microsoft Edge 持久化 Profile 登录，认证信息按 profile 本地保存，支持多环境快速切换。
- **业务上下文管理**：交互式选择租户 / 团队 / 部门，所有平台请求统一携带对应的业务请求头。
- **零污染安装**：Windows 一键安装包在用户目录创建独立虚拟环境，不污染其他 Python 项目。
- **多级别配置**：支持默认配置、当前目录配置、命令行参数与环境变量多级覆盖。

## 目录

- [安装](#安装)
  - [Windows 一键发布与安装](#windows-一键发布与安装)
- [配置](#配置)
- [命令](#命令)
- [增加新接口](#增加新接口)
- [贡献](#贡献)
- [许可证](#许可证)
- [问题反馈](#问题反馈)

## 安装

需要 Python 3.9 或更高版本，建议使用虚拟环境。

### 从源码安装（开发）

Windows PowerShell：

```powershell
py -m pip install --upgrade pip
py -m pip install -e .
ml --help
```

脚本使用系统已安装的 Microsoft Edge，不需要运行 `playwright install chromium`。

### Windows 一键发布与安装

发布人员在 Windows 项目根目录执行：

```cmd
scripts\windows\build-release.cmd
```

默认生成一个安装时下载依赖的联网发布包，可供 Python 3.12、3.13 等受支持版本使用：

```text
release\wisemlops-cli-<版本>-windows-py3-online.zip
```

企业内部有 Python 包源时，建议由发布人员将不含凭据的源地址写入发布包：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File .\scripts\windows\build-release.ps1 `
  -IndexUrl "https://pypi.company.example/simple" -Force
```

安装器会自动使用该地址，用户双击 `install.cmd` 即可。源地址不能包含用户名、密码或
令牌；认证可通过 `PIP_INDEX_URL` 等安全环境变量提供，并优先于包内预设地址。若发布包未预设源，
也可在安装时执行 `install.cmd -IndexUrl "https://pypi.company.example/simple"`。

如需生成与构建机 Python 小版本、架构绑定的离线包，显式传入 `-Offline`。

将 ZIP 发给用户。用户完整解压后双击 `install.cmd` 即可，无需管理员权限。安装器会：

1. 校验发布包 SHA-256。
2. 检查 Python 3.9+ 和 Microsoft Edge。
3. 在 `%LOCALAPPDATA%\Programs\WiseMLOpsCLI` 创建独立虚拟环境。
4. 安装或升级 CLI，不污染其他 Python 项目。
5. 将 `ml` 启动目录加入当前用户 `PATH`。
6. 执行 `ml --version` 验证安装。

构建与安装脚本最低要求 Windows PowerShell 5.1，并兼容 Windows 上的 PowerShell
7.x。脚本会在执行前检查版本和所需 PowerShell 命令，环境不满足时直接给出错误。

联网包只携带通用的项目 Wheel，安装时由所选 Python 从包源获取匹配的依赖，因此同一
个包可用于 Python 3.12 和 3.13，不受构建机 Python 小版本限制。企业内部源必须包含
项目依赖及其传递依赖对应的 Windows Wheel。脚本不会使用 `--extra-index-url` 回退公网，
避免依赖混淆。离线包中的依赖仍与 Python 小版本和 Windows 架构绑定。

安装后重新打开 CMD 或 PowerShell，即可在任意目录执行 `ml`。详细说明见
[`scripts/windows/INSTALL.md`](scripts/windows/INSTALL.md)。

## 配置

项目根目录的 `config.json` 是默认配置的唯一来源，构建 Wheel 时会自动放入安装包。
安装后首次执行 `ml login`、`ml env show` 等业务命令时，CLI 会将安装包内的默认配置
强制写入 `%APPDATA%\ml\config.json`。安装新版本或默认配置发生变化后，首次执行命令
也会再次覆盖该文件；同一版本的后续命令不会重复覆盖。升级前如需保留自定义环境，
请先备份该文件。当前目录存在 `config.json` 时优先使用当前目录配置，也可以通过全局
参数或环境变量指定：

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
    "login_timeout": 300000,
    "business_catalog_timeout": 30000
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

CLI 会自动监听 `/ai/user/info` 请求确认登录结果，用户不需要再按回车。认证成功后
会轮询当前页面的 `localStorage`，最多等待 `business_catalog_timeout` 毫秒，直到
`ai-businessList` 可读取并成功解析；随后打印读取和保存日志，缓存部门、租户、团队
目录，并用表格展示当前环境。更新本地认证信息后，Edge 才会自动关闭。`login_timeout`
控制等待用户登录的最长时间，单位为毫秒，默认 5 分钟；业务目录默认最多等待 30 秒。

业务目录和当前选择按环境保存在用户配置目录的 `ml/business.json`。业务命令要求
至少选择租户，不能只选择部门；团队只有 `teamStatus` 为 `available` 时才允许选择。
部门名称和分组键依次取 `settleTenantName.cn`、`settleTenantName.en`、顶层 `cn`，
不使用 `settleTenant`。
团队级选择使用 `teamList[].businessId` 作为请求头 `ai-businessId` 的值：

```powershell
ml business list
ml business use
ml business use --tenant mep
ml business use --tenant mep --team my-team
ml business show
ml business refresh
```

`ml business use` 不带参数时按“部门 → 租户 → 租户级或团队级”的顺序交互选择。
`ml business refresh` 会打开持久化 Edge Profile，重新读取浏览器中的业务目录并自动
关闭 Edge。已选团队被删除或变为非 `available` 状态后，当前选择会失效，必须重新
选择。旧版 `business.json` 不做迁移，登录或刷新时会直接根据浏览器缓存重新生成。
所有平台业务请求都会统一携带当前选择对应的 `ai-businessId` 请求头。

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

关闭证书校验只应用于显式配置的环境，并同时作用于平台接口请求和 Playwright
启动的持久化 Edge 上下文；只建议用于完全可信的内部网络。

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

## 贡献

欢迎通过 Issue 和 Pull Request 参与贡献。

1. Fork 本仓库并创建特性分支：`git checkout -b feature/your-feature`。
2. 在虚拟环境中安装开发依赖（见[安装](#安装)），确保测试通过：
   ```powershell
   py -m pytest
   ```
3. 提交信息请遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范，例如 `feat:`、`fix:`、`docs:`。
4. 向 `main` 分支提交 Pull Request，并在描述中说明改动动机与测试方式。

提交 Issue 前请先检索已有问题，避免重复。

## 许可证

本项目基于 [MIT 许可证](LICENSE) 开源。详见 [LICENSE](LICENSE) 文件。

## 问题反馈

如遇到问题或有功能建议，请在本仓库的 [Issues](https://github.com/mossexplore/platform-cli/issues) 中反馈。提交时请尽量包含：

- 复现步骤；
- 期望行为与实际行为；
- 运行环境（`ml --version` 输出与操作系统版本）。
