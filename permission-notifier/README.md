# 独立权限通知助手

Windows 托盘与本地网页应用。通过权限系统领取任务，逐个调用消息接口；不依赖、不修改业务 CLI。

## 安装与启动

需要 Python 3.12。将本项目单独交付到用户电脑，不放入 CLI 安装包。**完整解压安装包后，双击根目录的 `install.cmd`** 即可安装；安装成功或失败都会保留窗口，按任意键关闭。无需手动执行 `.ps1` 或修改系统执行策略。

已发布的 1.0.7.7 ZIP 附件保持原样。如果解压后没有 CMD 入口，可分别下载 [install.cmd](https://raw.githubusercontent.com/mossexplore/platform-cli/main/permission-notifier/install.cmd) 和 [uninstall.cmd](https://raw.githubusercontent.com/mossexplore/platform-cli/main/permission-notifier/uninstall.cmd)，保存到解压根目录，与 `pyproject.toml` 同级；保留完整的 `scripts` 目录。不要将文件保存为 `.cmd.txt`。后续源码安装包会直接包含这两个入口。

也可以在命令提示符或 PowerShell 中运行：

```powershell
.\install.cmd
```

安装时添加 `-AutoStart` 可注册当前用户登录启动任务；不需要系统服务账号。企业 Python 包源可通过 `-IndexUrl` 指定，不在参数中嵌入凭据。例如：

```powershell
.\install.cmd -AutoStart
.\install.cmd -IndexUrl "https://你的包源地址/simple"
```

首次安装需要能获取依赖。安装失败时查看窗口中的错误，处理后重新运行 `install.cmd`。升级或重复安装前先通过托盘退出助手，安装会保留个人配置和任务状态。

安装完成后使用桌面“权限通知助手”快捷方式。托盘菜单可打开管理页面、暂停/恢复、查看日志和退出；关闭浏览器不会停止助手。管理地址：

```text
http://127.0.0.1:18765
```

已有实例运行时，再次启动只打开页面。端口被其他程序占用时启动失败，不会监听外部地址。

## 启动失败定位

按 **Win + R**，粘贴以下命令并回车，可打开当前用户的日志：

```text
notepad "%LOCALAPPDATA%\PermissionNotifier\logs\assistant.log"
```

通常对应 `C:\Users\你的Windows用户名\AppData\Local\PermissionNotifier\logs\assistant.log`，实际位置以 `%LOCALAPPDATA%` 为准。记录报错时间和最后几行，不发送含 Token/auth 的 `assistant.json`。

在 PowerShell 中检查端口是否已有程序监听：

```powershell
Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue |
    Select-Object LocalAddress, LocalPort, OwningProcess
```

无输出表示当前未发现监听，不代表启动失败一定与端口无关；有输出时可按 `OwningProcess` 到任务管理器核对程序。如果已是助手，尝试打开 `http://127.0.0.1:18765`；不要直接结束未知进程。

关闭失败弹窗、确认没有助手实例运行后，可在 PowerShell 中使用已安装的 Python 前台启动，排除托盘相关问题：

```powershell
& "$env:LOCALAPPDATA\Programs\PermissionNotifier\venv\Scripts\python.exe" -m permission_notifier.main --headless
```

保持窗口打开，再访问本地网页；结束诊断时在页面点击“退出助手”或在该窗口按 Ctrl+C。此命令使用原配置和任务状态，正常启动后会按原暂停状态工作。

1.0.7.7 的通用弹窗不等于端口被占用。若桌面快捷方式失败、日志为 `ValueError`，但上述前台方式可用，可能是 `pythonw.exe` 无控制台时网页服务的日志初始化问题。当前源码已修复该问题，并在错误日志中增加失败阶段和系统错误码；仅补入 CMD 入口不会更新已安装的 Python 代码，原 Release 附件也不会自动包含源码修复。

## 首次配置

1. 权限服务先迁移至结构 12，并配置 `NOTIFICATION_OWNER_ADMIN_ID` 为你的现有管理员 ID。
2. 登录权限系统“个人通知”，开启通知，输入 `reset` 生成 Token；30 分钟内在本地绑定。
3. 本地网页填写权限系统地址和助手 Token，保存并绑定。
4. 填写消息 URL、auth、可选 sender，添加启用的接收 UID。每个 UID 单独请求一次。
5. 明确成功规则：默认“尚未确认”，不自动发送。只有确认 HTTP 2xx 即代表接受时选择该规则；也可按真实响应配置 JSON 字段与期望值。期望值填写合法 JSON，例如 `true`、`0` 或 `"ok"`。
6. 勾选对象，主动发送测试消息；检查逐项结果后保存配置并恢复通知。

消息请求 JSON 为 `content`、`receiver`、`auth`；sender 非空才加入。auth 不放入 HTTP Authorization；助手 Token 才用于访问权限系统的 Bearer 认证。

权限系统需 HTTPS，本机联调允许 HTTP 回环地址。消息接口支持 HTTP/HTTPS。两条连接可以独立配置代理、CA 文件及是否使用当前用户代理环境，不关闭 TLS 校验。

## 配置与数据

主文件：`%LOCALAPPDATA%\PermissionNotifier\assistant.json`。明文保存 Token/auth、配置及恢复状态；安装器限制目录为当前用户与 SYSTEM 访问。不要发送原文件到群聊或提交版本控制。网页不回显原凭据，留空保留，替换/清除显式进行。

网页保存后无需重启。当前 HTTP 请求沿用开始时配置；新接收列表用于新任务。已有任务保留目标快照，切换消息接口时需在明细中显式迁移未完成项。切换权限系统地址会等待旧任务和回传处理完毕，旧连接信息仅在等待期间保留；需要取消切换时把原地址及凭据重新保存。

不确定任务不会自动重发：先在消息客户端核对，再选择“确认已发送”“重试此对象”或“取消此对象”。成功对象不会随整单重试。即使所有对象结束为失败/不确定，后续任务仍可继续；存在此类任务时权限系统地址切换需要先处置。

文件损坏或不能写入时，助手停止新发送并提示。退出后恢复有效文件再启动，不要直接清空以继续发送。当前同一安装实例可备份恢复；换电脑时需保留实例与任务文件，且确保旧电脑助手已退出，然后在服务端重置 Token 并绑定。没有原快照时不能自动重发旧任务。

## 自动启动与卸载

```powershell
& "$env:LOCALAPPDATA\Programs\PermissionNotifier\autostart.ps1" -Enable
& "$env:LOCALAPPDATA\Programs\PermissionNotifier\autostart.ps1" -Disable
```

正常退出不会立即重启；下次登录遵循自动启动设置。暂停持久保存，重新启动仍暂停。注销、关机和休眠期间不能发送。

升级前通过托盘退出，再运行 `install.cmd`；配置保留。

**卸载前先通过托盘或本地网页退出助手，再双击解压目录中的 `uninstall.cmd`。** 默认删除助手程序、快捷方式和登录启动任务，保留个人 JSON 配置、凭据、任务记录及日志。命令行也可运行：

```powershell
.\uninstall.cmd
```

仅在确定不再需要个人数据时使用以下命令，并在提示时输入 `DELETE` 确认；取消或输入其他内容不会删除个人数据：

```powershell
.\uninstall.cmd -DeleteData
```

无需也不应卸载业务 CLI。卸载窗口会显示结果并等待按键关闭。

## 开发与测试

```bash
python -m pip install -e . pytest
python -m pytest -q
PERMISSION_SERVICE_SOURCE=/path/to/platform-cli/access-service python -m pytest -q
python -m permission_notifier.main --headless --data-dir /tmp/notifier-test
```

最后两项用于联调；跨项目测试还需安装权限服务依赖。测试使用模拟消息发送，不访问真实接口。Windows 托盘/任务计划需在实际 Windows 用户环境验收。

构建私有源码包和 Wheel：`python -m build`。构建包含 Windows 安装脚本的独立 ZIP：`python scripts/build.py`。本项目随 1.0.7.7 Release 作为单独附件交付，不放入 CLI 安装包或公共 Python 包仓库。当前不含 Python 解释器和离线依赖包，联网安装所需依赖需由用户环境提供。
