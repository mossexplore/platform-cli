# ml CLI

> WiseRec 平台的官方 Python 命令行客户端。

`ml` 是 [WiseRec](https://github.com/mossexplore/platform-cli) 平台的命令行客户端（要求 Python 3.9+）。它基于 [Typer](https://typer.tiangolo.com/) 构建，使用 [Playwright](https://playwright.dev/) 在 Microsoft Edge 中完成登录；登录成功后，Cookie、CSRF Token、账号、中文名、部门和过期时间会按 profile 保存到本地，后续业务命令使用 [HTTPX](https://www.python-httpx.org/) 请求平台接口。

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
release\wiserec-cli-<版本>-windows-py3-online.zip
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
3. 在 `%LOCALAPPDATA%\Programs\WiseRecCLI` 创建独立虚拟环境。
4. 安装或升级 CLI；版本一致时跳过包安装，更新时复用满足要求的依赖，不污染其他 Python 项目。
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
Windows 安装器每次安装（含同版本重装）都会用包内文件完整覆盖
`%APPDATA%\ml\config.json`，包括 `access_control`，不保留旧字段。
直接使用 pip 安装时，在首次读取默认配置时检测安装文件变化并覆盖；普通后续运行不重复覆盖，
因此 `ml env use` 的选择可持续使用到下一次安装。发布前应在包内设置正确的权限系统地址和启用状态。
当前目录配置以及通过 `--config` / `ML_CONFIG` 明确指定的文件属于独立配置，
不作为安装器覆盖目标；排查配置未更新时请确认没有使用这些覆盖来源。可通过全局
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
所有平台业务请求都会统一携带当前选择对应的 `ai-businessId` 和 `businessid`
请求头，由统一客户端自动添加，新增业务接口无需逐个补充。

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

## 训练任务与执行实例查询

```powershell
ml train list
ml train list --name wiserec --page 2 --page-size 20
ml train list --output json
ml train instance list f3483dc5-4525-4e50-8af7-a4117541f1dc
ml train instance list f3483dc5-4525-4e50-8af7-a4117541f1dc -o json
```

训练任务列表默认查询第 1 页、每页 10 条，`--name` 按任务名称模糊查询。
业务 ID 自动取当前环境的业务选择；未选择时先执行 `ml business use`。
除名称和分页参数外，列表请求的其他筛选字段固定使用管理台默认值。

执行实例命令接受完整任务 ID，自动逐页查找当前业务下的任务，再使用任务记录
返回的 `businessId` 和 `taskType` 查询实例；无需预先运行列表命令。
任务较多时查找会产生多次请求。实例固定返回第 1 页、每页 10 条，按 `createTime`
升序排列，暂不开放分页和排序参数；超过 10 条时表格会提示未展示全部实例。

表格展示空值为 `-`，数值零保留。大小按 1024 进制转换：零显示 `0B`，不足 1G
显示两位小数的 `M`，其余显示两位小数的 `G`。毫秒时间戳统一按上海时间
（Asia/Shanghai，UTC+08:00）显示为 `YYYY-MM-DD HH:mm:ss`。
执行实例表格依次展示：作业ID（`jobId`）、算法名称、CPU、GPU、内存、状态、执行节点、
集群、触发方式、开始时间、执行时长、存储桶。执行节点取 `hostIp`，触发方式取
`actionType`，开始时间取 `createTime`，存储桶取 `bucketName`。
执行实例的执行时长按查询结果展示时的当前时间减去 `createTime` 计算，以整分钟
显示，舍去不足一分钟的部分（例如 85 秒显示 `1min`）；开始时间为空时显示 `-`，
不足一分钟或开始时间晚于当前时间时显示 `0min`。
同一表格使用同一个当前时间。内存、状态和触发方式保留接口原值，不推测单位或中文含义。
执行记录的执行时长及 JSON 中的 `runningTime` 仍保留接口原值。
执行实例和执行记录表格的“作业ID”列固定为 36 字符宽，不换行、不截断，
其他长字段优先换行；终端过窄时请加宽窗口以查看完整表格。

`--output json`（或 `-o json`）返回 `count`、`pageIndex`、`pageSize`、`items`，
其中 `items` 保留完整原始记录，包括任务业务 ID、实例 `jobId`、空值、字节数和
毫秒时间戳。登录提示发送到标准错误，不混入 JSON 标准输出。未指定输出格式时
使用当前环境的 `output_format`。接口失败或任务不存在时命令以非零状态退出。

### 训练任务执行记录

```powershell
ml train history list 31835f9d-7464-429c-844b-3e393be2a4a0
ml train history list 31835f9d-7464-429c-844b-3e393be2a4a0 -o json
```

执行记录直接使用任务 ID 查询，不预先扫描训练任务列表。请求头统一携带当前业务的
`businessid` 和 `ai-businessId`，请求体不额外添加业务 ID 或任务类型。
查询固定第 1 页、每页 10 条，按 `createTime` 倒序，使用 `source="history"`、
字符串 `latestFlag="true"` 和空状态筛选，暂不开放分页、排序或筛选参数。

表格依次展示：作业ID（`jobId`）、算法名称、CPU、GPU、内存、状态、集群、节点数、执行时长、
大小、检查时间、开始时间、结束时间、触发方式、存储桶。触发方式取 `actionType`，
存储桶取 `bucketName`。三个时间字段分别取 `checkTime`、`createTime`、
`statusTime`，沿用上海时区及上述大小、空值展示规则。空列表显示“暂无执行记录”，
不据此判断任务不存在；总数超过 10 条时提示只展示第一页。
JSON 继续使用 `count`、`pageIndex`、`pageSize`、`items`，保留完整原始记录。

### 下载执行记录日志

```powershell
ml train history logs download <task-id> <job-id>
ml train history logs download <task-id> <job-id> --file ./logs/train.log
ml train history logs download <task-id> <job-id> --file ./logs/train.log -o json
```

命令直接将用户输入的 `jobId`、`taskId` 传给下载地址接口，不预先查询执行记录，
不进行 ID 有效性或归属校验，也不受执行记录第一页 10 条限制。
`businessId` 参数和 `businessid` 请求头使用当前业务选择，不再发送 `target`。
`isApplicantPromise` 固定发送 `true`。仅在 `code=0`、`des=success` 且 URL 为有效
HTTPS 地址时开始下载，否则显示错误码及描述。

CLI 直接流式下载，不需要打开浏览器。下载及最多 5 次 HTTPS 跳转使用独立客户端，
不携带平台认证或业务请求头。日志下载固定关闭证书校验（`verify=False`），不读取
环境配置中的 `verify_ssl`；平台接口请求仍沿用原有配置。默认使用响应提供的文件名（移除
目录成分），默认文件名末尾补充 `.zip`（已有该后缀时不重复添加），
缺省使用 `<job-id>-logs.zip`；也可用 `--file` 指定路径并保留指定文件名，父目录须已存在。
文件原样保存，不自动解压。目标文件已存在时，在扩展名前自动递增编号，例如
`logs.zip` → `logs (1).zip` → `logs (2).zip`，也适用于 `--file` 指定的路径，保留已有文件。
下载先写入同目录临时文件，完整接收后
通过硬链接发布最终文件并移除临时文件；目标文件系统须支持硬链接。

下载进度发送到标准错误。完成摘要包含 `taskId`、`jobId`、绝对保存路径 `path`、
实际字节数 `bytes` 和 `status=downloaded`；`-o json` 仅在标准输出打印 JSON 摘要，
获取有效地址后，下载开始前在标准错误完整打印 URL（包含查询参数），便于复制使用。
ID 有误时显示接口返回的 `code` 和 `des`。HTTP 错误、超时、连接中断或本地写入失败时非零退出。
网络下载失败时显示异常类型、具体消息和底层原因，例如 `ConnectError` 及
`SSLCertVerificationError`，便于区分证书问题、连接失败和传输异常。
错误消息内的 URL 替换为 `<下载地址>`；下载前打印的完整 URL 不受影响。

## 特征集列表

查询“样本工程 → 特征集”下的宽表或模型特征集：

```bash
ml featureset wide list
ml featureset model list --name test --page 2 --page-size 10
ml featureset wide list -o json
```

默认查询第 1 页、每页 10 条；`--name` 传入服务端名称查询条件。
使用当前环境所选业务，请先运行 `ml business use`。其他查询字段固定为接口默认值。
表格展示八列，空值显示 `-`，时间按北京时间（UTC+08:00）展示；
JSON 输出包含 `count`、`pageIndex`、`pageSize`、`items`，保留记录原始字段和时间。
更多说明见 [CLI 参考使用指南](docs/CLI参考使用指南.md#特征集列表)。

查询特征集配置：

```bash
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

两个入口均直接按 ID 查询，固定打印解析后的配置 JSON，不受环境的表格输出设置影响。
仅当接口返回 `code=0` 且 `des=success` 时解析 `featureJson`；输出保留中文和完整配置内容，
去除外层字符串包装引入的多余转义，真实内容所需的 JSON 转义仍保留。

## 增加新接口

通用认证、超时、重试和错误处理位于 `PlatformClient`。业务接口按领域放在
`src/wiserec_cli/services/`，CLI 参数放在 `src/wiserec_cli/commands/`。
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

### 可选在线权限管理

新增 `ml access status`，可接入账号与环境白名单，在业务命令执行前按 CLI 当前登录账号检查实时授权。独立管理服务支持 MySQL、Web 页面和 Linux 离线安装；离线包携带 Python 运行时及第三方依赖，不依赖服务器的 Python 3.7.4。

详见 [权限服务部署说明](access-service/README.md) 和 [CLI 使用指南](docs/CLI参考使用指南.md)。客户端检查不替代平台后端鉴权，需在分发配置中启用。

## 权限管理服务 Docker 部署

支持 GitHub Actions 自动测试、构建并发布 GHCR 镜像。配置、启动、日志、升级和发布流程见 [Docker 部署与发布指南](docs/权限管理系统Docker部署与发布指南.md)。

离线镜像安装、固定目录挂载、docker run 启停和故障排查，请参阅 [权限管理系统 Docker 安装部署与调试指南](docs/权限管理系统Docker安装部署与调试指南.md)。
