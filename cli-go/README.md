# WiseRec CLI Go 客户端

Go 客户端使用独立版本，当前源码版本为 `1.0.11`，由根目录 `versions.toml` 的 `components.cli_go` 管理。Windows x64 安装后使用同一套 `ml` 命令和 WiseRec Platform Skill。支持范围用 `ml tree --all` 核对，实际参数用子命令的 `--help` 核对。

## 一键打包

构建机需要 Go 1.25 或以上、Python 3.12、Windows x64 和 WiX Toolset 5.0.2。WiX 可通过 .NET SDK 安装，安装后确认 `wix` 可在 PATH 找到。

```powershell
dotnet tool install --global wix --version 5.0.2
Copy-Item cli-python/config.example.json cli-go/config.json
# 先编辑 cli-go/config.json，填写获准分发的环境地址和权限服务配置。
.\cli-go\scripts\build-release.cmd
```

也可使用 `./cli-go/scripts/build-release.ps1`。配置优先取 `-ConfigPath PATH`，其次依次查找 `cli-go/config.json`、`cli-python/config.json` 和仓库根目录的 `config.json`。只打 ZIP 时加 `-PortableOnly`，也可在装有 PowerShell 的 macOS 或 Linux 上执行。使用 `-OutputDirectory DIR` 指定新输出目录；默认输出在 `dist/cli-go/`。构建脚本校验环境和权限配置并编译进 `ml.exe`。更新这些配置需重新出包。构建输入请使用获准分发的环境信息，密码、Token 等秘密由服务端管理。

| 产物 | 内容 |
| --- | --- |
| `wiserec-cli-go-VERSION-windows-x64.zip` | 含部署配置的 `ml.exe`、正式 Skill 和 `/ml` 资源、`release.json` 和本说明 |
| `wiserec-cli-go-VERSION-windows-x64.msi` | 同一个 `ml.exe`、正式 Skill 和 `/ml` 的每用户安装包 |

开发时只需裸 EXE，可运行 `./cli-go/scripts/build-windows.ps1 -OutputDirectory DIR -ConfigPath PATH`。命令使用相同的构建配置优先级，生成的 EXE 可单独运行。

## MSI 安装、升级与卸载

1. 打开 PowerShell 或 CMD，运行 `where.exe ml`。如果已有 Python 或其他客户端的 `ml`，先从用户或系统 PATH 移除对应目录，保留 Python 的配置、登录数据和程序文件。若是由会话别名或函数提供的入口，也先移除相应的 shell 配置。
2. 双击 MSI，或通过 `msiexec` 安装。安装范围为当前用户，程序位于 `%LOCALAPPDATA%\Programs\WiseRecCLIGo\ml.exe`。安装器发现其他已注册在 Windows 用户或系统 PATH 的 `ml` 时会阻止安装。
3. 重新打开终端与 Agent。运行 `where.exe ml`、`ml --version` 和 `ml context --json` 核对入口、版本和配置路径。

```powershell
msiexec /i "PATH_TO_MSI"
where.exe ml
ml --version
ml context --json
ml tree --all
```

升级或卸载前，结束仍在执行的 Go 命令，并对正在保活的环境运行 `ml auth ping stop`。直接运行更高版本 MSI 即可升级。修复可在 Windows“已安装的应用”中操作，或执行 `msiexec /fa "PATH_TO_INSTALLED_MSI"`。卸载可在同一界面执行，或运行 `msiexec /x "PATH_TO_INSTALLED_MSI"`。静默执行可加 `/qn /norestart /l*v "PATH_TO_LOG"`。升级拒绝降级覆盖。卸载移除 MSI 安装的程序、PATH 条目、Skill 和快捷命令，保留两套客户端的配置和登录数据。恢复使用 Python 时先卸载 Go MSI，再恢复 Python PATH 或重跑 Python 安装包。

MSI 自动将正式 Skill 放入 `~/.agents/skills/wiserec-platform` 和 `~/.cac/skills/wiserec-platform`，并将 `ml.md` 放入 OpenCode 配置目录的 `commands/` 和 `~/.cac/commands/`。OpenCode 默认目录为 `~/.config/opencode`。如需自定义，安装前设置用户环境变量 `OPENCODE_CONFIG_DIR` 为绝对路径。修复、升级和卸载沿用首次安装选定的位置，切换目录时卸载后重装。MSI 停用历史 `ml-lab.md` 和旧 Skill 的 `SKILL.md` 入口，保留其余用户文件。

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

## 验证范围

在 `cli-go` 下运行 `go test ./...` 和 `go vet ./...`。独立的 [Windows 打包工作流](../.github/workflows/cli-go-windows.yml) 使用示例配置构建测试产物，验证 ZIP 和 MSI 的二进制一致性，以及冲突检测、版本、修复、升级、降级拒绝和卸载。真实平台登录、在线权限和 Jupyter 需在获准环境另行验收。
