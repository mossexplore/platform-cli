# WiseMLOps CLI Windows 安装说明

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
%LOCALAPPDATA%\Programs\WiseMLOpsCLI
```

安装器会创建独立 Python 虚拟环境，不会污染用户现有项目的 Python 依赖，并将
`ml.cmd` 所在目录添加到当前用户的 `PATH`。

## PowerShell 安装方式

如果系统策略不允许双击脚本，可打开 PowerShell，在解压目录执行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1
```

重新创建虚拟环境：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 -Force
```

自定义安装目录：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\install.ps1 `
  -InstallDirectory "D:\Tools\WiseMLOpsCLI"
```

## 安装要求

- Windows 10 或 Windows 11。
- Python 3.9 或更高版本。
- Microsoft Edge。
- 联网包安装时需要能够访问 Python 包下载源。
- 离线包已经包含 Python 依赖，不需要在安装时访问包下载源。

离线包文件名中的 `py311` 等标记表示对应 Python 3.11。部分依赖与 Python 小版本和
Windows 架构绑定，因此用户 Python 主次版本必须与离线包一致。安装器会自动校验。
联网包只要求 Python 3.9 或更高版本。

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

## 常见问题

### 找不到 `ml` 命令

安装后必须重新打开 CMD 或 PowerShell，让新的用户 `PATH` 生效。

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
