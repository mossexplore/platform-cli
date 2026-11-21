# WiseRec CLI Go 客户端

Go 客户端使用独立版本，由根目录 `versions.toml` 的 `components.cli_go` 管理。运行 `build.cmd` 或 `build-release.ps1` 时，打包脚本会自动同步 Go 版本文件。Windows x64 安装后使用同一套 `ml` 命令和 WiseRec Platform Skill。支持范围用 `ml tree --all` 核对，实际参数用子命令的 `--help` 核对。

Go 的各级 `--help` 随 EXE 分发，采用 Python CLI 的用法、说明和面板布局，参数及子命令以 Go 的实际支持范围为准。维护时可在安装了历史 CLI 依赖的 Python 环境中运行 `python cli-go/scripts/sync-python-help.py`，从只读的 `cli-python/` 生成帮助文案。详见 [仓库维护规则](../AGENTS.md)。

## 一键打包

同时构建 ZIP 和 MSI 时，请在 Windows x64 上准备 Go 1.25 或以上、Python 3.12、.NET SDK 和 WiX Toolset 5.0.2。**先安装 .NET SDK，再安装 WiX。**

在 PowerShell 中从仓库根目录进入 `cli-go`。本节后续命令都在该目录执行。安装工具后重新打开终端时，请先回到 `platform-cli\cli-go`。

```powershell
Set-Location .\cli-go
```

### 1. 安装并验证 .NET SDK

在 PowerShell 中运行以下命令，安装 .NET 10 SDK。也可以从微软页面下载 Windows x64 的 **SDK 安装程序**。[微软 .NET SDK 安装说明](https://learn.microsoft.com/en-us/dotnet/core/install/windows)

```powershell
winget install --id Microsoft.DotNet.SDK.10 --exact --architecture x64
```

安装后关闭并重新打开 PowerShell，再运行 `dotnet --list-sdks`。如果没有列出 SDK，请检查安装结果。如果仍提示找不到 `dotnet`，先确认 `C:\Program Files\dotnet\dotnet.exe` 是否存在；若存在，把 `C:\Program Files\dotnet` 加入 PATH 后重开终端。

### 2. 安装并验证 WiX

确认 `dotnet --list-sdks` 列出了 SDK 后，在同一个 Windows 用户账号下运行：

```powershell
dotnet tool install --global wix --version 5.0.2
wix --version
```

如果 WiX 已安装但 PowerShell 找不到 `wix`，重新打开终端。若仍找不到，把 `%USERPROFILE%\.dotnet\tools` 加入用户 PATH 后重开终端。

### 3. 安装 Go 并检查 Python

下载 Go 1.25 或以上的 Windows x64 安装包，文件名以 `windows-amd64.msi` 结尾。双击安装后重新打开 PowerShell。如果使用 VS Code 内置终端，请重启 VS Code。 [Go 官方下载](https://go.dev/dl/)

```powershell
go version
python --version
```

预期 `go version` 显示 Go 版本及 `windows/amd64`，`python --version` 显示 `Python 3.12.x`。如果找不到 `python`，安装 Python 3.12 时勾选将 Python 加入 PATH，然后重开终端。

如果 PowerShell 提示找不到 `go`，用默认安装路径检查：

```powershell
& "$env:ProgramFiles\Go\bin\go.exe" version
```

如果能打印版本，把 `C:\Program Files\Go\bin` 加入 Windows 用户 `Path`，重新打开终端后再运行 `go version`。如果文件不存在，请核对 Go 是否安装成功，或按实际安装目录检查。

### 4. 准备配置并打包

已有当前目录的 `config.json` 时，直接检查其中的平台地址和权限服务配置。

```powershell
if (-not (Test-Path .\config.json)) {
    Copy-Item ..\cli-python\config.example.json .\config.json
}
notepad .\config.json
```

保存配置后，在资源管理器中双击 `cli-go\build.cmd`。它会读取同目录的 `config.json`，生成 ZIP 和 MSI。窗口会实时显示资源准备、配置校验、Go 编译、WiX 打包和 ZIP 压缩的步骤及工具输出，完成后显示产物路径或失败原因。每次构建在 `cli-go\dist\` 下创建新的输出目录。如果之前已把离线模块缓存解压到 `cli-go\dist\go-module-cache`，双击脚本会默认复用它。

从 PowerShell 打包时，也可以执行以下命令。

```powershell
.\scripts\build-release.cmd -ConfigPath .\config.json
```

也可使用 `./scripts/build-release.ps1`。从终端打包时加 `-Verbose` 可显示同样的详细输出。配置优先取 `-ConfigPath PATH`，其次依次查找 `./config.json`、`../cli-python/config.json` 和 `../config.json`。只打 ZIP 时加 `-PortableOnly`，也可在装有 PowerShell 的 macOS 或 Linux 上执行。默认输出在 `cli-go/dist/`，可用 `-OutputDirectory DIR` 指定其他目录。构建脚本校验环境和权限配置并编译进 `ml.exe`。更新这些配置需重新出包。构建输入请使用获准分发的环境信息，密码、Token 等秘密由服务端管理。

| 产物 | 内容 |
| --- | --- |
| `wiserec-cli-VERSION-windows-x64.zip` | 含部署配置的 `ml.exe`、正式 Skill 和 `/ml` 资源、`release.json` 和本说明 |
| `wiserec-cli-VERSION-windows-x64.msi` | 同一个 `ml.exe`、正式 Skill 和 `/ml` 的每用户安装包 |

开发时只需裸 EXE，可运行 `./scripts/build-windows.ps1 -OutputDirectory ./dist/exe -ConfigPath ./config.json`。命令使用相同的构建配置优先级，生成的 EXE 可单独运行。

### Go 依赖下载超时

如果打包时请求 `proxy.golang.org` 超时，可在能联网的机器上准备离线缓存。先将当前终端的 `GOMODCACHE` 指向一个新的空目录，再从同一版本的 `cli-go` 目录执行 `go mod download` 和 `go mod verify`。将新缓存中的 `cache/download` 放进 ZIP，压缩包根目录应为 `cache/`，内部保留 `download/`。

拿到离线 Go 模块缓存 ZIP 后，在 Windows 的 `platform-cli\cli-go` 下运行。将 `CACHE_ZIP_PATH` 替换为压缩包路径。

```powershell
$modCache = Join-Path (Get-Location).Path 'dist\go-module-cache'
Expand-Archive -LiteralPath 'CACHE_ZIP_PATH' -DestinationPath $modCache
$env:GOMODCACHE = $modCache
$env:GOPROXY = 'off'
go mod download
go mod verify
```

两条 `go mod` 命令成功后，在同一个 PowerShell 窗口运行 `.\scripts\build-release.cmd -ConfigPath .\config.json`。这些环境变量只在当前窗口生效。若仓库的 `go.mod` 或 `go.sum` 更新，请准备与新提交匹配的缓存。

## MSI 安装、升级与卸载

1. 双击 MSI，或通过 `msiexec` 安装。控制面板和 Windows“已安装的应用”中的名称为 **WiseRec CLI**。安装范围为当前用户，程序位于 `%LOCALAPPDATA%\Programs\WiseRecCLIGo\ml.exe`。
2. 如果用户 PATH 中已有旧版 WiseRec Python 安装器注册的入口，MSI 会自动移除该条目并继续安装。旧版程序、配置和登录数据会保留。安装失败回滚时会恢复移除的旧入口。
3. 交互安装期间使用同一个进度条显示检查环境、安装 CLI、配置命令和安装 Skill 等阶段。用重新打包的同版本 MSI 安装时，选择「卸载并安装」后，Windows Installer 会移除已有安装并安装新包，保留环境配置和登录数据。选择「取消」会保留已有安装。再次打开已经安装的同一 MSI 文件时，如需修复，请通过「已安装的应用」操作。CLI 安装成功后显示「安装成功」提示及本次安装的 CLI 版本。点击「确定」关闭窗口，重新打开终端与 Agent，再运行 `where.exe ml`、`ml --version` 和 `ml context --json` 核对入口、版本和配置路径。

系统 PATH 中的冲突由管理员调整。其他工具目录中的 `ml` 需要手动核对，以免删除它们共享的 PATH 条目。PowerShell 别名或函数可用 `Get-Command ml -All` 检查。

```powershell
msiexec /i "PATH_TO_MSI"
where.exe ml
ml --version
ml context --json
ml tree --all
```

升级或卸载前，结束仍在执行的 Go 命令，并对正在保活的环境运行 `ml auth ping stop`。直接运行更高版本 MSI 即可升级。修复可在 Windows“已安装的应用”中操作，或执行 `msiexec /fa "PATH_TO_INSTALLED_MSI"`。卸载可在同一界面执行，或运行 `msiexec /x "PATH_TO_INSTALLED_MSI"`。静默执行可加 `/qn /norestart /l*v "PATH_TO_LOG"`。Skill 或快捷命令安装失败时，交互安装会提示「Skill 未安装成功，请手动安装」，CLI 仍可使用。可使用上述修复命令重试，也可解压同批便携 ZIP，按下方目录说明手动复制 `agent/` 中的 Skill 和快捷命令。静默安装可从 MSI 日志查看 Skill 安装结果。升级拒绝降级覆盖。卸载移除 MSI 安装的程序、PATH 条目、Skill 和快捷命令，保留两套客户端的配置和登录数据。恢复使用 Python 时先卸载 Go MSI，再恢复 Python PATH 或重跑 Python 安装包。

MSI 自动将正式 Skill 放入 `~/.agents/skills/wiserec-platform` 和 `~/.cac/skills/wiserec-platform`，并将 `ml.md` 放入 OpenCode 配置目录的 `commands/` 和 `~/.cac/commands/`。OpenCode 默认目录为 `~/.config/opencode`。如需自定义，安装前设置用户环境变量 `OPENCODE_CONFIG_DIR` 为绝对路径。修复、升级和卸载沿用首次安装选定的位置，切换目录时卸载后重装。MSI 停用历史 `ml-lab.md` 和旧 Skill 的 `SKILL.md` 入口，保留其余用户文件。

### 版本拒绝时从终端升级

在权限管理系统的「升级说明地址」中直接填写 MSI 的 HTTPS 下载链接。OBS 对象可以使用无后缀的名称，带签名查询参数的链接按原样填写。自动升级仅接受经证书验证的 HTTPS 权限服务返回的下载链接。

通过 MSI 安装的 Go 客户端在交互终端遇到版本过低时会询问是否升级。确认后，终端在开始下载时显示下载地址。客户端与训练日志下载共用代理选择规则，支持 `HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 和系统手动代理。下载后检查 MSI 产品、架构和准入版本要求，并按包内版本将临时文件命名为 `wiserec-cli-VERSION-windows-x64.msi`。本次命令退出后，Windows Installer 开始安装。脚本、JSON 输出和便携 ZIP 可走手动升级。

## 便携 ZIP

解压后在 PowerShell 中用 `.\ml.exe` 或绝对路径调用。这种方式可与 Python CLI 并行试用。解压不会修改系统、注册 PATH 或安装 Skill。需要在当前终端用 `ml` 时，可临时把解压目录放到该终端 PATH 首位，再用 `where.exe ml` 核对。

```powershell
.\ml.exe --version
.\ml.exe context --json
$env:Path = "$(Get-Location);$env:Path"
ml --version
```

## 首次使用与状态

首次运行需要配置的命令时，`%APPDATA%\ml-go-preview\config.json` 写入形如 `{"current":"dev"}` 的环境选择。新版首次读取旧配置时，只保留仍在 EXE 内置列表中的 `current`；旧环境已移除、文件缺失或无法解析时，使用包内默认环境。`ml env use NAME` 只能选择内置列表中的环境。登录、业务选择、浏览器会话和历史也在独立 Go 用户目录内。MSI 与便携 Go 客户端共用这一套 Go 状态。Python 客户端仍使用 `%APPDATA%\ml\`。浏览器登录依赖已安装的 Microsoft Edge。

```powershell
ml env list
ml env use NAME
ml login
ml auth status
ml business show
```

如需切换业务，执行 `ml business use --tenant TENANT_ID`。Go 业务命令需要启用在线权限校验，并配置可访问的权限服务。需要企业 CA 时，由出包人员在构建配置中设置 `access_control.ca_source` 与 `ca_file`。权限服务收到 Go 的独立版本，请按实际准入规则验证环境。

## DeepSeek Harness 保活

DeepSeek Harness 的自动保活由 [Windows Desktop 宿主插件](../dsh-plugin/wiserec-cli/README.md) 调度，插件独立打包。终端继续使用 CLI worker。用 `ml auth ping tick --capabilities` 确认 CLI 构建具备插件接口，用 `ml auth ping status` 检查插件报到与最近平台确认。

## 验证范围

在 `cli-go` 下运行 `go test ./...` 和 `go vet ./...`。独立的 [Windows 打包工作流](../.github/workflows/cli-go-windows.yml) 使用示例配置构建测试产物，验证 ZIP 和 MSI 的二进制一致性，以及旧 PATH 自动清理、失败回滚、版本、修复、升级、降级拒绝和卸载。真实平台登录、在线权限和 Jupyter 需在获准环境另行验收。
