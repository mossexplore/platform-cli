# CLI Mock 独立演示环境配置、打包与使用指南

本文面向打包人员、权限管理员和使用演示包的同事，按“准备权限 → 打包 → 安装 → 核对环境 → 执行业务 → 排障”的顺序说明。

当前实现中，正式和演示环境都使用 `ml`；通过 `ml context` 主动查询环境，不修改终端标题、提示符或每条业务输出。业务数据由独立 Mock 后端提供，**权限检查、版本准入和调用日志使用真实权限管理系统**。正式 CLI 安装包不包含 Mock 实现、种子和专用依赖。

相关文档：[设计方案](CLI模拟数据与独立演示环境设计方案.md)、[测试用例](CLI演示环境测试用例.md)、[测试报告](CLI演示环境测试报告.md)、[完整命令手册](WiseRec%20CLI%20使用手册.md)。本文也会作为 `README.md` 自动放入下一次构建的演示 ZIP；仓库内文档链接需在代码仓中打开。

## 1. 先了解各部分的作用

| 部分 | 用途 | 是否需要连接真实服务 |
| --- | --- | --- |
| 正式 CLI | 操作真实业务平台 | 按正式配置连接 |
| 演示 CLI | 使用原业务命令操作合成数据 | 需要真实权限服务，不连接真实业务平台 |
| Mock 数据库 | 保存训练、算法、数据集、服务等演示数据 | 本地 SQLite |
| 权限管理系统 | 判断账号和环境授权、版本策略，记录调用 | 必须可达，不能本地模拟放行 |
| 可选 Jupyter | 实际执行 Notebook、Python 和终端命令 | 本机独立 Jupyter 服务 |

模拟训练不会占用真实 GPU，模拟部署不会创建 Kubernetes 资源。Jupyter 执行则是真实的，应只运行自己理解的代码。

推荐流程：打包人员构建独立 ZIP → 权限管理员准备演示授权 → 演示人员解压安装 → 打开专用终端 → 核对 `ml context` → 录屏操作。

## 2. 准备条件与占位符

示例中的值需要替换：

| 占位符 | 含义 | 示例 |
| --- | --- | --- |
| `PERMISSION_HOST` | 可从演示机器直连的权限服务主机 | `permission.example.com`，仅为说明用域名 |
| `YOUR_ACCOUNT` | 管理员登记并授权的账号，须完全一致 | 使用管理员提供的账号 |
| `TASK_ID` 等 | 在当前演示环境列表中查询到的 ID | 不复制正式平台 ID |
| `版本` | 构建脚本从仓库读取的 CLI 版本 | 当前源码为 `1.0.7.2` |

运行需要 Python 3.9 或更新版本以及 venv/pip；建议为构建与目标机器统一使用 Python 3.12。可选 Jupyter 和依赖解析还有各自的 Python 版本要求。离线包严格检查 Python 主次版本、操作系统和架构，建议使用相同 Python 补丁版本。

离线包不包含 Python 本体、权限管理系统、数据库服务或可选 JupyterLab。**离线安装依赖不等于可以脱离权限服务运行。** 外部录屏场地须提前确认权限服务可达，或由管理员在该网络部署同一权限系统并配置授权。

## 3. 对接真实权限管理系统

### 3.1 确认服务地址

已有权限系统时沿用其部署，不需要为了使用 Mock 升级或重新初始化生产数据库。尚未部署时，管理员参考 [权限管理系统 Docker 安装部署与调试指南](权限管理系统Docker安装部署与调试指南.md)，按目标发布版本完成部署。

`--permission-url` 支持以下形式：

```text
https://PERMISSION_HOST
https://PERMISSION_HOST/cli-permission
http://PERMISSION_HOST:8008
```

不要填写后台页面路径 `/admin`、接口完整路径 `/api/v1/access/check`、带用户名密码的 URL、查询参数或片段。不要填写 `access.mock.invalid`：权限服务必须是真实地址。

可从演示机器访问下面的健康地址，替换主机和协议后执行：

```bash
curl --max-time 5 https://PERMISSION_HOST/cli-permission/healthz
```

预期 HTTP 200 且响应为 `{"status":"ok"}`。健康检查只说明服务和数据库结构正常，**不代表某个账号已经获得授权**。

### 3.2 管理员登记两个演示环境

在权限后台的“环境管理”中登记或核对：

| 环境名 | 显示名称建议 | 平台源站 platform_origin | 状态 |
| --- | --- | --- | --- |
| `demo-dev` | CLI 演示开发 | `https://demo-dev.mock.invalid` | 启用 |
| `demo-test` | CLI 演示测试 | `https://demo-test.mock.invalid` | 按需启用 |

环境名和源站必须与表格完全一致。源站字段不要追加 `/dashboard`；它与 CLI 配置中的完整平台入口不是同一个字段。

这些保留域名仅供 Mock 业务路由和权限环境匹配使用，不需要 DNS、hosts 文件或部署网站。不要替换成正式平台域名，也不要将现有正式环境改名为演示环境。

### 3.3 登记账号和分配授权

在“人员授权”中：

1. 查找或登记实际演示人员的账号，确认账号启用。
2. 为其分配 `demo-dev`；需要切换演示环境时再分配 `demo-test`。
3. 确认授权启用且未过期，授权有效期覆盖录屏时间。
4. 在“版本管理”中检查适用于演示环境的策略，确认允许当前 CLI 版本；不要为演示修改正式环境的准入策略。

安装器不会创建用户、授权或修改版本策略。`identity --username` 也不会授予权限。

**身份边界：**现有权限服务接受客户端上报的用户名，并不独立验证平台登录身份。演示登录生成本地模拟业务会话，不会打开真实平台登录页；配置账号不等于完成真实身份认证。请由管理员指定账号，不要把这一机制作为 SSO 或防止恶意本地篡改的安全边界。客户端不需要保存权限后台管理员密码或网关密钥。

### 3.4 网络和企业证书

演示权限请求使用直连，忽略环境代理；`access_control.use_env_proxy` 必须为 `false`。网关应直接提供以下三个 POST 接口，不依赖重定向或交互式网页登录：

```text
/cli-permission/api/v1/access/check
/cli-permission/api/v1/access/summary
/cli-permission/api/v1/access/environments
```

HTTPS 校验默认开启。企业 CA 可通过 `SSL_CERT_FILE` 指向有效的 PEM CA 文件，并在启动演示终端前设置。

PowerShell 示例：

```powershell
$env:SSL_CERT_FILE = 'C:\certs\company-ca.pem'
.\start-demo.cmd
```

Linux/macOS 示例：

```bash
export SSL_CERT_FILE=/absolute/path/company-ca.pem
./start-demo.sh
```

不要用关闭权限或关闭证书校验解决连通性问题。权限拒绝、连接失败、超时、非正常 HTTP 状态和非法响应都会阻止业务操作。

## 4. 构建演示安装包

以下命令在**代码仓根目录**执行。打包不需要填写权限地址或账号，也不会把运行工作区打入 ZIP；这些值由安装人员指定。

### 4.1 准备独立构建环境

Windows PowerShell：

```powershell
py -3.12 -m venv .venv-demo-build
.\.venv-demo-build\Scripts\python.exe -m pip install --upgrade pip build
.\.venv-demo-build\Scripts\python.exe scripts/demo/build-demo.py --output release/demo-online-build
```

Linux/macOS：

```bash
python3 -m venv .venv-demo-build
.venv-demo-build/bin/python -m pip install --upgrade pip build
.venv-demo-build/bin/python scripts/demo/build-demo.py --output release/demo-online-build
```

脚本会构建正式核心 Wheel、检查其不含 Mock，再构建独立 Mock 扩展 Wheel，并加入安装、启动、管理脚本和本指南。不要同时运行多个构建命令，以免共用的构建目录相互干扰。

Windows 也提供 `scripts/demo/build-demo.cmd`。它使用 `py -3` 选择解释器，**不保证使用已激活虚拟环境**；使用此入口前应给该解释器安装 `build`：

```powershell
py -3 -m pip install build
.\scripts\demo\build-demo.cmd --output release/demo-cmd-build
```

需要准确控制 Python 版本时，优先使用前面的显式 Python 路径。

### 4.2 联网包与离线包

| 类型 | 构建参数 | 安装时的依赖来源 |
| --- | --- | --- |
| 联网包 | 默认，不传 `--offline` | 核心与扩展来自包内，其他依赖可从包源下载 |
| 离线包 | `--offline` | 所有必需 CLI 依赖从包内安装，禁止包源补包 |

Windows 离线构建：

```powershell
.\.venv-demo-build\Scripts\python.exe scripts/demo/build-demo.py --offline --output release/demo-offline-build
```

Linux/macOS 离线构建：

```bash
.venv-demo-build/bin/python scripts/demo/build-demo.py --offline --output release/demo-offline-build
```

**离线构建本身需要下载依赖。**脚本只下载 Wheel，若某个依赖没有当前平台兼容 Wheel，构建会失败。当前脚本不支持通过参数交叉构建：Windows 目标包在匹配的 Windows/Python/架构环境构建；Linux 包不能直接用于 Windows。

参数和产物：

| 项目 | 行为 |
| --- | --- |
| `--output DIRECTORY` | 输出目录；默认相对当前目录的 `release/demo` |
| `--offline` | 下载当前构建平台依赖并生成离线包 |
| 联网文件 | `wiserec-cli-版本-demo-online.zip` |
| 离线文件 | `wiserec-cli-版本-demo-offline.zip` |
| 重复构建 | 同名 ZIP 已存在时拒绝覆盖；换一个新的输出目录 |

不同平台的 ZIP 文件名不额外标出平台，请按平台/Python 分目录保管，并检查包内 `manifest.json` 的 `platform`、`python`、`architecture` 和 `offline`。不要仅凭文件名判断兼容性。

### 4.3 与正式打包脚本的关系

| 目的 | 使用入口 |
| --- | --- |
| 原正式 CLI 出包 | `scripts/windows/build-release.cmd` / `.ps1` |
| 原正式构建后安装 | `scripts/build-install.cmd` / `.ps1` |
| Mock 演示包 | `scripts/demo/build-demo.py` / `.cmd` |

正式脚本不会因为仓库新增 Mock 代码而自动包含演示扩展。正式 Wheel、sdist 和 Windows ZIP 有隔离检查；演示构建也先检查正式核心 Wheel。GitHub 自动生成的仓库源码归档仍包含开发源码，不等同于正式 Python 分发包。

## 5. 解压、安装与目录说明

将 ZIP 解压到一个**新的、专用的目录**，进入包含 `install-demo.py` 的内层目录。不要在仓库根目录寻找这个安装脚本直接安装：它需要同目录的 `manifest.json` 和 `packages`。

Windows PowerShell：

```powershell
py -3.12 install-demo.py --permission-url https://PERMISSION_HOST --username YOUR_ACCOUNT
```

Linux/macOS：

```bash
python3 install-demo.py --permission-url https://PERMISSION_HOST --username YOUR_ACCOUNT
```

联网包和离线包使用相同安装命令，安装器根据 manifest 选择依赖安装方式。安装器会校验文件哈希、创建独立虚拟环境、安装核心和扩展、初始化工作区并生成同名 `ml` 包装入口。安装完成后仍须实际执行权限检查，安装成功不代表已获授权。

目录结构：

```text
解压目录/
  install-demo.py          安装入口
  manifest.json           平台、Python、包哈希
  packages/               分发的 Wheel
  runtime/                独立 Python 环境，安装后生成
  bin/ml.cmd              Windows 演示命令包装器
  bin/ml                  POSIX 演示命令包装器
  start-demo.cmd/.sh      打开专用终端
  manage-demo.cmd/.sh     管理演示数据和本地服务
  workspace/
    config.json           演示 CLI 配置
    workspace.json        归属标记、场景、账号和权限地址
    state.sqlite3         持久化模拟业务数据
    client/               独立凭据、业务选择和客户端状态
    samples/clicks.csv     预置上传样例
    exports/              导出文件目录
    jupyter/              可选 Jupyter 工作目录
```

安装目标已存在 `runtime` 或 `workspace` 时拒绝覆盖，包括上次安装中途失败的情况。请保留需要的数据，在新目录重新解压安装；不要直接覆盖正式 Python 环境或正式 CLI。

## 6. 配置文件说明与变更方式

配置由安装器自动生成，无须手工编写。下面展示主要字段，**用于核对，不是要求覆盖文件**：

```json
{
  "current": "demo-dev",
  "auth": {"auto_ping": false},
  "api": {"retry_times": 0},
  "access_control": {
    "enable": true,
    "url": "https://PERMISSION_HOST",
    "use_env_proxy": false
  },
  "profiles": [
    {
      "name": "demo-dev",
      "alias": "demo-dev",
      "api_endpoint": "https://demo-dev.mock.invalid/dashboard",
      "jupyter": {"mode": "webstudio", "server_url": "http://127.0.0.1:18888/"}
    },
    {
      "name": "demo-test",
      "alias": "demo-test",
      "api_endpoint": "https://demo-test.mock.invalid/dashboard",
      "jupyter": {"mode": "webstudio", "server_url": "http://127.0.0.1:18888/"}
    }
  ]
}
```

| 字段或需求 | 说明和操作 |
| --- | --- |
| 当前环境 | 使用 `ml env use demo-dev` 或 `ml env use demo-test` 切换 |
| 权限账号 | 保存在 `workspace.json`；用管理脚本 `identity --username` 修改 |
| 权限地址 | 初始化时同时写入配置和归属标记，二者必须一致 |
| 更换权限服务 | 当前没有专门的地址迁移命令；推荐在新目录以新地址安装，并保留旧工作区备份 |
| `access_control.enable` | 必须为 `true`，不能关闭 |
| 平台入口和 profile 名称 | 固定为上述演示值，不能改成真实业务平台 |
| 业务 ID | 由 `client/business.json` 中当前环境选中业务产生，不要硬编码正式业务 ID |
| 超时 | 核心权限配置可接受 `timeout_seconds`，范围 1–120 秒；未设置时默认 15 秒 |

不支持通过 `ml --config` 引用正式配置或外部配置。工作区及其父路径不能是符号链接。不要把运行中的凭据、Jupyter token、真实权限账号配置或业务状态作为演示安装包重新分发。

## 7. 启动、检查与首次验收

在**解压目录**执行：

Windows：

```powershell
.\start-demo.cmd
```

Linux/macOS：

```bash
./start-demo.sh
```

启动器先校验演示配置，再打开专用终端；只修改该终端的环境变量，不修改系统 PATH、标题或提示符。**新终端的当前目录是 `workspace`。**

在这个专用终端执行：

```bash
ml context
ml context --json
ml login
ml access status
ml env list
ml business show
ml train list
```

验收时检查：

1. `ml context` 的运行模式为“演示（模拟数据）”，配置和状态路径指向本次解压目录，权限地址及账号正确。
2. `ml access status` 允许当前账号访问当前演示环境。
3. `ml train list` 显示合成训练数据；JSON 输出可使用 `ml train list -o json`。
4. 权限后台“调用日志”出现对应账号、`demo-dev`、`ml train list`、当前 businessid 和放行结果。

`ml login` 本身不说明已获得某个环境授权，必须完成业务调用验收。录屏前可先运行 `ml context` 核对，正式录屏时仍使用普通 `ml` 命令。

Windows 可用 `where ml`，POSIX 可用 `command -v ml` 检查命令路径，应优先命中本包的 `bin`。退出专用终端使用 `exit`；在原终端再次核对命令路径后再操作正式环境。

## 8. 日常业务操作示例

以下命令在演示专用终端执行；从当前列表获取 ID 替换占位符。完整参数以 `ml tree`、具体命令 `--help` 和正式命令手册为准。

### 8.1 查询、切换环境和业务

```bash
ml train list -o json
ml algorithm list
ml dataset list
ml model list
ml service list
ml env use demo-test
ml login
ml business list
ml business show
```

切换后权限系统会检查 `demo-test` 的独立授权。各演示环境和业务范围的数据相互隔离；只获 `demo-dev` 授权时不要假设 `demo-test` 也能访问。切换具体业务使用 `ml business use --help` 查看租户和团队参数。

### 8.2 训练、克隆与完成

```bash
ml train clone TASK_ID --name recording-copy --yes
ml train start TASK_ID
ml train history list TASK_ID
```

模拟训练不会按现实时间自动完成。先在另一个位于解压目录的管理终端执行 `advance --seconds 60`（见下一节），再查询历史：

```bash
ml train history list TASK_ID
ml train start TASK_ID
ml train cancel TASK_ID --yes
```

上面重新启动一次任务后再取消，以保证取消对象仍在运行。写入会持久化到 SQLite，关闭再打开专用终端仍可查询。

### 8.3 文件上传与下载

```bash
ml dataset files upload DATASET_ID samples/clicks.csv
ml dataset files list DATASET_ID
ml algorithm download ALGORITHM_ID --file exports/algorithm.zip
ml train config export TASK_ID --file exports/train.yaml
ml featureset wide list
ml featureset wide export FEATURESET_ID --file exports/features.csv
```

ZIP、CSV 和 YAML 是实际文件。模拟上传单次请求上限为 16 MiB，超限报错；重新导出时遵守命令已有的覆盖确认，或使用新的文件名。

### 8.4 模型部署演示

```bash
ml model list
ml deployment template list
ml model deploy MODEL_ID --template TEMPLATE_ID --dry-run
ml model deploy MODEL_ID --template TEMPLATE_ID --yes
ml service list
```

`--dry-run` 只预览，不创建模拟服务；正式提交后服务列表出现新记录。两种操作均须通过真实权限校验，不会部署真实平台资源。

## 9. 数据场景与管理脚本

建议另开一个终端，停留在**解压目录**执行管理命令。它与演示终端共用同一个工作区。

Windows PowerShell：

```powershell
.\manage-demo.cmd status
.\manage-demo.cmd identity --username YOUR_ACCOUNT
.\manage-demo.cmd advance --seconds 60
.\manage-demo.cmd fault --path /ai/backend/modelDev/modelTrain/list --status 503 --count 1
.\manage-demo.cmd reset --scenario standard --yes
```

Linux/macOS：

```bash
./manage-demo.sh status
./manage-demo.sh identity --username YOUR_ACCOUNT
./manage-demo.sh advance --seconds 60
./manage-demo.sh fault --path /ai/backend/modelDev/modelTrain/list --status 503 --count 1
./manage-demo.sh reset --scenario standard --yes
```

如果直接在启动器打开的 `workspace` 中管理，Windows 使用 `..\manage-demo.cmd`，POSIX 使用 `../manage-demo.sh`。管理脚本没有加入 PATH，不要假设直接输入 `manage-demo.cmd` 在所有目录均可找到。

| 场景 | 用途 |
| --- | --- |
| `standard` | 默认关联数据、查询和连续业务演示 |
| `empty` | 空列表和无数据行为 |
| `large` | 较多记录与分页 |
| `expired-session` | 首次登录产生过期模拟会话，下一业务操作刷新 |
| `partial-failure` | 训练列表接口失败一次，随后恢复 |
| `malformed-response` | 返回不满足业务契约的响应，验证错误处理 |

切换场景使用 `reset --scenario SCENARIO --yes`。重置会重建模拟数据库并清空 `client` 中的凭据和客户端状态，保留配置、权限地址、账号以及 `exports` 和其他用户文件。当前 profile 不会自动恢复为 `demo-dev`。重置前停止保活和本地 Jupyter；存在 Jupyter 登记时会拒绝重置。

切换账号会清除旧凭据，之后重新 `ml login`；新账号仍必须有当前环境授权。`reset`、`advance`、`fault`、`jupyter` 启动均先经过真实权限检查。

**没有 `permission-denied` 或 `version-blocked` 本地场景。**要演练权限拒绝，由管理员针对演示账号/环境临时撤销授权或设置演示范围的版本策略，观察业务失败和调用日志，再恢复原授权；不要改变正式环境策略。

## 10. 可选：本地 Jupyter 实际执行

完整 POSIX 命令执行建议在 Linux/虚拟机中演示。Windows 原生 CLI 安装与完整 Jupyter 终端能力是两个验证范围，不能混为一谈。

在 POSIX **解压目录**安装可选依赖并启动：

```bash
runtime/bin/python -I -m pip install 'jupyterlab>=4,<5' 'ipykernel>=6,<7'
./manage-demo.sh jupyter --port 18888
```

该命令保持前台运行；另开演示专用终端：

```bash
ml webstudio list
ml webstudio start STUDIO_ID
ml webstudio login STUDIO_ID
ml webstudio show
ml jupyter doctor
ml jupyter files list
ml jupyter exec -- python -c "print('hello from local Jupyter')"
```

本地服务仅监听 `127.0.0.1`，token 由管理器生成并保存在工作区。不要复制正式 Jupyter 配置；只允许连接本工作区登记的服务。Jupyter 根目录不是操作系统沙箱，执行代码仍具有本机用户权限。

在解压目录查询或停止服务：

```bash
./manage-demo.sh jupyter-status
./manage-demo.sh jupyter-stop
```

也可在前台服务终端按 Ctrl+C。不要手工删除登记文件后再启动第二个实例。权限故障不阻止停止自己登记的服务。

标准演示离线 ZIP 不带上述 Jupyter 可选依赖。完全离线演示 Jupyter 时，应在匹配目标环境的联网机器另行下载其 Wheel 依赖至独立目录，复制后使用运行环境的 pip `--no-index --find-links` 安装；不要修改原演示包的受校验文件。请先完成一次实际 Notebook/exec 验收再录屏。

## 11. 源码开发方式

只有修改 Mock 源码或运行测试时才需要此方式。普通录屏使用独立 ZIP 更方便，正式 Python 环境中不要安装 Mock 扩展。

POSIX 仓库根目录示例：

```bash
python3 -m venv .venv-demo-dev
.venv-demo-dev/bin/python -m pip install -e . -e ./devtools/mock-platform
.venv-demo-dev/bin/python -m wiserec_cli_mock.manage --workspace /absolute/new-demo init --permission-url https://PERMISSION_HOST --username YOUR_ACCOUNT
export WISEREC_DEMO_WORKSPACE=/absolute/new-demo
.venv-demo-dev/bin/python -m wiserec_cli_mock.bootstrap context --json
.venv-demo-dev/bin/python -m wiserec_cli_mock.bootstrap train list
```

`/absolute/new-demo` 必须尚不存在。开发时显式调用 bootstrap；仅设置工作区环境变量后运行正式 `ml`，不会自动启用 Mock。Windows 可将上述解释器改为 `.venv-demo-dev\Scripts\python.exe`，并用 PowerShell 设置 `$env:WISEREC_DEMO_WORKSPACE`。

业务 Mock 位于 `devtools/mock-platform/src/wiserec_cli_mock/`；正式核心位于 `src/wiserec_cli/`。不要将模拟路由、数据或场景复制到正式核心目录。

测试和包验收入口见 [测试用例](CLI演示环境测试用例.md) 与 [测试报告](CLI演示环境测试报告.md)。测试权限服务使用独立临时数据库，不会替你配置实际录屏账号。

## 12. 常见问题排查

| 现象 | 检查与处理 |
| --- | --- |
| `ml context` 显示真实平台 | 当前调用了正式入口；从演示解压目录运行 start-demo，再查命令路径 |
| 离线包 Python/系统/架构不匹配 | 对照 manifest；用匹配环境构建或换正确的目标包 |
| 目标包已存在，拒绝覆盖 | 为新构建指定新的 `--output` 目录 |
| 演示环境已存在，拒绝覆盖 | 新目录重新解压安装；不要覆盖原有 runtime/workspace |
| 演示包校验失败 | 重新获取完整 ZIP，不修改被 manifest 校验的包内文件 |
| 权限地址不匹配 | 配置与归属标记不一致；使用正确地址在新目录安装 |
| 无法连接权限服务 | 从演示机器检查健康地址、协议、端口、路由和 CA；权限请求不走环境代理 |
| 权限响应为 HTML、重定向或非法 JSON | 检查反向代理路由、登录页拦截和接口路径 |
| 环境未启用/地址不匹配 | 核对后台的 demo-dev/demo-test、启用状态及 origin，origin 不带 /dashboard |
| 账号未授权或授权过期 | 核对 context 账号、后台用户启用状态、当前环境授权和到期时间 |
| CLI 版本被拒绝 | 管理员检查作用于演示环境的版本策略；不关闭权限绕过 |
| 安装成功但 train list 失败 | 安装只创建运行环境；继续执行 access status，检查后台调用日志 |
| 场景下持续返回异常响应 | 检查 status 中的场景；通过授权后 reset 为 standard |
| 训练一直运行 | 使用管理脚本 advance 推进至少 60 秒，再查询 |
| Jupyter 未启动/无法连接 | 检查前台进程、端口占用及 jupyter-status；不要引用真实 Jupyter 凭据 |
| 重置被 Jupyter 登记阻止 | 正常停止服务并等待管理进程清理；异常退出时先核实残留服务，保留工作区排查 |
| 找不到 manage-demo 脚本 | 回到解压目录，或在 workspace 使用上一级相对路径 |
| 模拟接口未实现 | 记录完整命令和接口错误，补充 Mock 契约；不会回退真实平台 |

权限排障可在演示终端执行 `ml access status --diagnose`；该命令显示受限连接诊断，不应发送密码、Cookie、Token 或未经审查的工作区文件。查看权限日志时按演示账号、环境和时间筛选，核对放行/拒绝原因。

## 13. 备份、升级与结束演示

- 备份前停止保活、本地 Jupyter 和其他操作进程，再复制整个 `workspace`。它可能包含凭据和 token，应按本地敏感配置保管，不提交 Git。
- 当前没有自动工作区 schema 迁移命令。升级推荐新目录安装、重新核对权限和样例数据；不要把旧数据库直接覆盖到新包并假设兼容。
- 结束录屏后正常停止 Jupyter、执行 `ml auth ping stop`，再 `exit` 关闭专用终端。
- 卸载时保留需要的导出文件和备份，删除确认属于本次演示的独立解压目录即可；不需要卸载系统里的正式 `ml`，也不需要修改系统 PATH。
- 本指南说明的是当前实现。Linux 测试与 Windows 原生验证范围见测试报告；构建演示包不等于发布正式 CLI Release。
