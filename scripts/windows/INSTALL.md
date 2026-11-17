# WiseRec CLI Windows 安装说明

## 一键安装

1. 解压整个发布 ZIP，不能只复制单个 Wheel。
2. 双击 `install.cmd`。
3. 安装成功后关闭并重新打开 CMD 或 PowerShell。
4. 执行：

```powershell
ml --version
ml env show
ml login
```

安装过程不需要管理员权限。默认安装到：

```text
%LOCALAPPDATA%\Programs\WiseRecCLI
```

安装器会创建独立 Python 虚拟环境，不会污染用户现有项目的 Python 依赖，并将
`ml.cmd` 所在目录移到当前用户 `PATH` 的首位，避免用户安装的其他 Python 入口抢先匹配。安装器会清理所选 Python 和安装虚拟环境中已识别的 wiserec-cli editable 安装，并校验最终 Wheel、版本和用户配置路径。

## 配置覆盖规则

每次安装成功前，安装器都会用新包中的 `config.json` 更新当前用户的
`%APPDATA%\ml\config.json`，同版本重装也会强制覆盖。仅保留原配置的 `current` 值；
环境定义、管理台类型、地址、本地禁止命令策略、自动保活、权限系统及其他字段全部采用安装包内容，
本地新增字段和环境也会被移除。首次安装使用包内默认 `current`。
仅当旧文件可读取为 JSON 对象、`current` 为非空字符串且对应环境存在于新包中时保留；
否则自动采用安装包指定的默认 `current`，不因此中断安装。其他旧字段不参与合并或校验。
安装包配置无效或目标文件无法写入时仍会报错。

CLI 运行时只读取当前账号的 `%APPDATA%\ml\config.json`。配置缺失时重新运行安装程序。直接安装正式 Wheel 后，可使用同一 Python 运行 `python -m wiserec_cli.install_config` 初始化配置。

### 为安装包配置客户端证书自动选择

发布方在**构建内部安装包前**编辑项目根目录的 `config.json`。在对应 `profiles` 条目中加入
`client_certificate_origins`，填写证书弹窗显示的 HTTPS 主机和端口。下面的地址是占位示例。

```json
{
  "name": "dev",
  "alias": "开发环境",
  "api_endpoint": "https://console.example.com/dashboard",
  "client_certificate_origins": ["https://auth.example.com:443"]
}
```

默认端口为 443。每个条目只接受明确的 HTTPS 主机和端口，支持填写多个地址。
没有证书请求的环境可以省略该字段或使用空数组。

用户照常在自己的 Windows 账号下运行 `install.cmd`。安装和升级时，安装器会将包内所有环境配置的认证地址同步到当前账号的 Edge 策略。一张匹配证书时自动使用，多张时 Edge 显示选择框。已存在的站点规则会保留。移除配置中的地址并重新安装后，安装器会移除自己添加且内容未被修改的规则。

若设备已有计算机级证书自动选择策略、明确关闭多证书提示或限制用户写入策略，安装器会提示由 IT 处理，用户仍可按 Edge 弹窗继续登录。用户级策略适用于该 Windows 账号下的 Edge。部署后可在 `edge://policy` 检查策略是否生效。

## PowerShell 安装方式

如果系统策略不允许双击脚本，可打开 PowerShell，在解压目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

需要重建整个虚拟环境（包括所有依赖）时，执行 `install.cmd -Force`：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Force
```

使用指定的企业内部 Python 包源：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -IndexUrl "https://pypi.company.example/simple"
```

如果发布人员已经把企业源写入联网发布包，双击 `install.cmd` 即可，无需用户传参。
包源选择顺序为显式 `-IndexUrl`、`PIP_INDEX_URL` 环境变量、发布包预设值、用户 pip
配置或 pip 默认源。使用环境变量时，安装器不会把其中可能存在的凭据打印或复制到
命令行。脚本不会自动回退到公网附加源。

企业源使用私有 CA 时，优先把企业根证书安装到 Windows 信任存储；也可以指定 PEM
证书链文件：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -IndexUrl "https://pypi.company.example/simple" `
  -Cert "C:\Certificates\company-ca.pem"
```

不要把用户名、密码或令牌写入发布包中的源地址。需要认证时，应使用企业统一的 pip
配置或由安全环境变量提供认证信息。

自定义安装目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -InstallDirectory "D:\Tools\WiseRecCLI"
```

## 安装要求

- Windows 10 或 Windows 11。
- Windows PowerShell 5.1 或 PowerShell 7.x。
- Python 3.9 或更高版本。
- Microsoft Edge。
- 联网包安装时需要能够访问 Python 包下载源，内部源需包含全部直接及传递依赖。
- 离线包已经包含 Python 依赖，不需要在安装时访问包下载源。

离线包文件名中的 `py311` 等标记表示对应 Python 3.11。部分依赖与 Python 小版本和
Windows 架构绑定，因此用户 Python 主次版本必须与离线包一致。安装器会自动校验。
联网包只要求 Python 3.9 或更高版本；同一个 `windows-py3-online.zip` 可供 Python
3.12 和 3.13 用户安装，依赖会按实际解释器版本下载。

## Tab 补全

PowerShell 用户可在安装后执行：

```powershell
ml --install-completion powershell
```

重新打开 PowerShell 后即可使用 Tab 补全固定命令和选项。Windows CMD 不支持
Typer 的命令补全。

## 升级

解压新版本发布包，再次运行其中的 `install.cmd` 即可。CLI 程序会被升级，用户目录
中的登录缓存和 Edge Profile 不会因升级虚拟环境而删除。

每次执行安装器都会在目标虚拟环境中卸载旧的 `wiserec-cli`，再安装本次解压包内的
Wheel，即使新旧版本号相同也会替换 CLI 文件。已有且满足要求的依赖继续复用；
离线包只使用包内依赖。随后安装器刷新用户 `config.json`、注册命令并验证
`ml --version`。如需连依赖一起重建，运行 `install.cmd -Force`。

## 常见问题

### Edge 登录时弹出客户端证书选择

Windows 安装器会根据包内配置同步当前用户策略。若设备由企业统一管理，IT 也可以通过 Microsoft Edge 管理策略为指定认证站点开启自动选择。
请先确认实际发起证书请求的 HTTPS 主机及端口。登录如果跳转到独立认证站点，应填写发起请求的认证站点。

1. 在 [`AutoSelectCertificateForUrls`](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/autoselectcertificateforurls) 的现有列表中为每个认证站点加入一条规则，保留其他站点的条目。以下地址是示例，请替换为实际主机及端口。

   ```json
   {"pattern":"https://auth.example.com:443","filter":{}}
   ```

   可在源码仓库根目录运行下面的命令。将输出的每一行分别加入组策略的自动选择列表。

   ```powershell
   python scripts/windows/edge_client_certificate_policy.py https://auth.example.com https://sso.example.com:8443 |
     ConvertFrom-Json | Select-Object -ExpandProperty AutoSelectCertificateForUrls
   ```

2. 启用 [`PromptOnMultipleMatchingCertificates`](https://learn.microsoft.com/en-us/deployedge/microsoft-edge-policies/promptonmultiplematchingcertificates)，让 Edge 在有多张候选证书时保留选择框。
3. 在试点设备的 `edge://policy` 中确认两项策略已生效，再运行 `ml login`。只有一张候选证书时应直接继续登录，多张时应弹出选择框。若没有候选证书，由 IT 核对设备的证书下发情况。

如需撤销，请在原管理策略中移除本次新增的站点规则，并还原本次调整的多证书提示设置。

### 找不到 `ml` 命令

安装后必须重新打开 CMD 或 PowerShell，让新的用户 `PATH` 生效。

### `ml --version` 提示找不到旧模块

包名调整后，旧 Python 安装目录中的 `ml.exe` 可能仍引用旧模块。
在 PowerShell 中检查实际匹配的入口，并直接验证新安装：

```powershell
where.exe ml
& "$env:LOCALAPPDATA\Programs\WiseRecCLI\bin\ml.cmd" --version
```

使用自定义安装目录时，请替换上述路径。如果完整路径可以正常执行，可在当前
PowerShell 窗口临时调整优先级：

```powershell
$env:Path = "$env:LOCALAPPDATA\Programs\WiseRecCLI\bin;" + $env:Path
ml --version
```

使用修复后的安装器重新安装，会将入口移到用户 `PATH` 首位；随后关闭并重新打开
终端。如果旧入口来自系统 `PATH`、当前目录或 PowerShell 别名，仍可能被优先选择，
可通过完整路径调用，并用 `Get-Command ml -All` 检查冲突。
如果完整路径不存在，请先完整解压发布包并运行 `install.cmd`。

### 找不到 Python

从 Python 官方网站安装 Python 3.9 或更高版本。推荐同时安装 Windows Python
Launcher (`py.exe`)。

### 找不到 Edge

确认 Microsoft Edge 已安装。如果 Edge 由公司安装在非标准路径，可执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -SkipEdgeCheck
```

该参数只跳过安装阶段检查；执行 `ml login` 时仍然需要可用的 Microsoft Edge。

### 校验失败

安装器会检查 `CHECKSUMS.sha256`。校验失败说明发布包缺少文件或内容被修改，应重新
下载并完整解压发布 ZIP。

## OpenCode skill 与 command

OpenCode/codeagent 集成分两个阶段：先安装并验证 CLI，再安装正式 skill `wiserec-platform` 和 `/ml` 快捷入口。不安装 `skill-lab` 详细版。第二阶段失败时 CLI 仍可使用，修复文件权限或占用问题后重新运行安装程序。

OpenCode 的正式 skill 安装到 `~/.agents/skills/wiserec-platform`，`/ml` 位于当前 OpenCode 配置目录的 `commands/ml.md`；codeagent 使用 `~/.cac/skills/wiserec-platform` 和 `~/.cac/commands/ml.md`。`OPENCODE_CONFIG_DIR` 可指定 OpenCode 配置目录。每次安装更新正式 skill，并清理共享目录、当前 OpenCode 目录和 codeagent 目录中的历史 `wiserec-platform-detailed` 与 `commands/ml-lab.md`，其他资源保留。

完成后重新打开 Agent 会话，输入 `/ml 查询当前业务下的模型` 使用正式 skill；不带需求时可查看上下文和用法。直接通过 pip 安装 Wheel 不自动安装 Agent 资源，自动安装入口为官方 Windows 安装包。

历史安装若使用过其他自定义 OpenCode 配置目录，需在该目录重新运行安装程序才能清理对应旧副本。

制作安装包前，在项目根目录将 `config.example.json` 复制为同目录的 `config.json`，修改正式环境配置后再运行打包脚本。打包仅使用这份 `config.json`，缺失时直接报错，绝不自动采用样例。Wheel、源码分发包和 Windows 安装包均携带正式配置；安装后的用户文件仍为 `config.json`。无需在用户目录创建 `config.example.json`。
