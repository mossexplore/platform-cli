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
3. 本地网页填写权限系统地址和助手 Token，点击保存配置；助手会自动绑定，无需额外操作。
4. 填写消息 URL、auth、可选 sender，添加启用的接收 UID。每个 UID 单独请求一次。
5. 消息接口固定以 HTTP 2xx 且响应 JSON 顶层 status 严格等于 "ok" 判断发送成功，无需选择成功规则或配置 JSON 字段。超时及其他未知响应需先核对消息，再处理。
6. 选择测试接收人，输入测试内容并发送；检查逐项结果后保存配置并恢复通知。

消息请求 JSON 为 `content`、`receiver`、`auth`；sender 非空才加入。auth 不放入 HTTP Authorization；助手 Token 才用于访问权限系统的 Bearer 认证。

权限系统需 HTTPS，本机联调允许 HTTP 回环地址。消息接口支持 HTTP/HTTPS。页面不提供代理、CA 文件或代理环境配置入口；已有网络配置保持生效，保存其他设置不会覆盖这些值，TLS 校验保持开启。

## 配置与数据

配置文件：`%LOCALAPPDATA%\PermissionNotifier\assistant.json`，保存 Token/auth、配置及配置切换信息。发送记录文件：同目录 `send-records.json`，保存任务恢复状态、待回传结果、逐次发送历史，不混入当前 Token/auth 配置。两个文件均受本机用户目录权限保护，不要分享原始文件。首次运行会自动将旧单文件格式拆分，保留实例编号、凭据和未完成任务。备份、换机或恢复时，应先退出助手，再同时保存和恢复这两个文件；升级后不支持用旧助手直接读取新格式。

网页保存后无需重启。当前 HTTP 请求沿用开始时配置；新接收列表用于新任务。已有任务保留目标快照，切换消息接口时需在明细中显式迁移未完成项。切换权限系统地址会等待旧任务和回传处理完毕，旧连接信息仅在等待期间保留；需要取消切换时把原地址及凭据重新保存。

不确定任务不会自动重发：先在消息客户端核对，再选择“确认已发送”“重试此对象”或“取消此对象”。成功对象不会随整单重试。即使所有对象结束为失败/不确定，后续任务仍可继续；存在此类任务时权限系统地址切换需要先处置。

文件损坏或不能写入时，助手停止新发送并提示。退出后恢复有效文件再启动，不要直接清空以继续发送。当前同一安装实例可备份恢复；换电脑时需保留两个数据文件，且确保旧电脑助手已退出，然后在服务端重置 Token 并绑定。没有原快照时不能自动重发旧任务。

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

页面顶部分别展示本地助手、权限系统连接及自动通知状态；权限系统连接依据当前配置绑定及最近两分钟的心跳判断。已保存配置清单显示缺失项，编辑后提示未保存。轮询间隔和超时位于高级设置中。消息接口通过主动测试验证，不能将权限系统已连接视作消息接口可用。

### 测试消息排查

测试直接请求消息接口，不经过权限系统。`queued: true` 只代表排队；等待页面刷新后查看“消息接口测试结果”。结果展示接收 UID、测试时间、HTTP 状态、目标域名、耗时及响应摘要。仅 HTTP 2xx 且响应 JSON 顶层 `status` 严格等于 `"ok"` 才判为成功；若没收到消息，用 UID、测试时间以及摘要中的流水号在消息服务查询投递记录。响应体支持嵌套 JSON、数组和普通文本，隐藏已配置凭据及敏感字段；最多展示 8000 字符，每层最多 100 项、12 层。也可在 `/api/status` 的 `test_results[].diagnostic.response_summary` 查看同一脱敏内容。

权限系统异常单独查看运行状态：`SERVICE_CONNECT_TIMEOUT` 是建立连接超时，`SERVICE_READ_TIMEOUT` 是等待响应超时，`SERVICE_PROXY_ERROR` 是代理异常，`SERVICE_CONNECTION_FAILED` 需检查 DNS、网络及 TLS，`SERVICE_LOCAL_NETWORK_CONFIG_ERROR` 需检查代理或 CA 文件配置。测试响应只在当前进程内保留，重启后清空。

Token 和 auth 已保存时，输入框默认显示四位掩码。输入新值后点击保存配置即可更新；保持原掩码保留已有值，主动清空输入框并保存会清除。点击眼睛可查看当前值，再次点击隐藏；普通配置和状态接口不会返回明文，明文只在本机主动点击眼睛时读取。保存或重新加载后恢复密码显示。

### 页面导航

左侧菜单提供连接配置、消息配置、发送记录和高级设置。连接配置仅用于权限系统地址、助手 Token 及连接验证。消息配置菜单下设“消息配置”和“测试与诊断”两个页签：消息配置仅维护消息接口、auth 和 sender；测试与诊断左侧维护接收 UID，右侧选择启用接收人、发送测试并查看 HTTP 状态、耗时及脱敏响应体。助手运行详情在连接配置页直接展示，工作线程运行中及已配置项以绿色标签显示，通知处理暂停以橙色标签显示；暂停通知不会停止工作线程保活。检查连接成功显示绿色结果，失败显示红色结果，修改连接参数后需重新检查。

各页保存按钮保存整个当前配置。菜单和页签切换保留未保存内容，重新加载会询问是否放弃修改。高级设置仅保留轮询间隔、消息请求超时、重新加载配置和退出操作。页面字号、控件高度与间距沿用权限管理系统的紧凑规格。

状态颜色统一为：绿色表示已配置或已接受，橙色表示暂停、等待重试或结果不确定，红色表示失败或异常，蓝色表示排队或发送中，灰色表示未配置、未知或已跳过。所有标识均保留文字说明；接口接受不代表实际送达。

### 发送记录查询

发送记录页按“任务 ID、发送时间、来源、接收者 UID、申请人、账号、申请时间、状态”展示。申请人、账号、申请时间从权限系统消息的对应行解析；无法解析或来源为接口测试时显示 `-`。申请时间统一转换为北京时间。每次发起发送、每位接收人分别记录；重试不会覆盖上次发送时间。来源为权限系统或接口测试，可组合开始时间、结束时间和来源查询，默认开始时间为当前时刻前 72 小时，结束时间为当前时刻；每次进入或再次点击发送记录菜单，结束时间更新为当前北京时间（精确到秒），保留开始时间和来源条件并查询第一页；每页 10 条，点击重置恢复最近三天范围及全部来源。时间按北京时间 `YYYY-MM-DD HH:mm:ss` 展示。任务 ID 完整显示，其他长字段可换行，窄屏横向滚动查看其他列。

新发送的历史记录持久保存，重启后可查询。测试响应摘要仍只在当前进程内保留。旧任务没有准确发送时间时显示“未知（旧记录）”，按时间筛选时不包含它们；升级前未保存的接口测试无法补回。已关闭的任务恢复快照可在超过 7 天后清理，已保存的独立发送历史不会随之删除。接口接受不等于实际送达。

底部仅在有未保存修改时提示；保存成功后隐藏底部提醒，保存结果通过上方操作提示展示。

测试内容支持编辑，不能为空或全为空白，最多 10000 字符。发送使用点击时的内容快照，并原样保存到发送历史；编辑测试内容不会标为配置修改。
