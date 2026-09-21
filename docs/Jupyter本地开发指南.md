# Jupyter 本地开发与 Web Studio 联调

第一阶段：真实 Jupyter Server + CLI 直连，支持完整 Notebook 前台执行和交互 Terminal。执行期间保持本地 CLI 运行；不提供后台托管、自动重跑或恢复 Kernel 内存状态。

## 安装和启动

在项目根目录执行，Python 3.9+：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[jupyter-local]'
.venv/bin/python scripts/jupyter_local.py
```

该脚本前台运行 JupyterLab，默认监听 `127.0.0.1:8888`。按 Ctrl+C 后遵循 Jupyter 提示停止服务。换端口使用 `--port 8889`，只生成配置使用 `--prepare-only`。脚本不后台派生服务，不修改已有 dev/test 环境配置。端口被占用时启动失败，不会悄悄换端口。

Windows 对应使用 `.venv\Scripts\python.exe` 和 `.venv\Scripts\ml.exe`。交互 Terminal 的 Windows 输入桥接已实现，但当前真实端到端验证环境为 macOS。

安装后激活虚拟环境可直接使用 `ml` 和 `jupyter lab`。项目脚本是推荐启动入口，因为它同时配置了隔离的工作目录、Token、业务上下文和运行时目录。

所有本机开发数据位于被 Git 忽略的 `.jupyter-local/`：

| 文件 | 用途 |
|---|---|
| `config.json` | 独立 CLI 配置，当前环境为 jupyter-local |
| `business.json` | 本地测试业务目录与 selected.businessId |
| `token` | 自动生成的认证 Token，不打印到终端，文件权限为 600 |
| `jupyter_server_config.json` | Jupyter 服务配置，含 Token，文件权限为 600 |
| `workspace/` | Jupyter 可访问的文件根目录 |
| `runtime/` | Jupyter 本地运行信息 |

网页入口为 `http://127.0.0.1:8888/lab`；如需网页登录，从本机 token 文件获取 Token。CLI 直接读取 token 文件，无需打开网页。

## 使用

另开一个本机终端：

```bash
source .venv/bin/activate
export ML_CONFIG="$PWD/.jupyter-local/config.json"
ml --version
ml jupyter doctor
ml jupyter notebook run examples/jupyter/hello.ipynb --download .jupyter-local/results
ml jupyter terminal open
```

`doctor` 验证 HTTP 认证、Kernel 列表和 Terminal 接口，不创建 Kernel。WebSocket 在执行或连接 Terminal 时验证。结果文件按执行 UUID 分目录保存，失败也保留 Notebook 和 summary.json。

Terminal 中可输入普通命令；Ctrl+C 传给远程 Shell，Ctrl+D 发送 EOF，Ctrl+] 仅离开本地连接。另开终端可以执行：

```bash
ml jupyter terminal list
ml jupyter terminal attach 1
ml jupyter terminal close 1
```

将 `1` 换成实际终端名称。close 会终止指定远程终端，可能影响其中的进程。退出客户端不承诺保留任务，重连不承诺完整历史回放。

## direct 模式生产配置

在生产环境 profile 中增加 `jupyter` 对象：

```json
{
  "name": "production",
  "api_endpoint": "https://console.example.com/dashboard",
  "jupyter": {
    "server_url": "https://notebook.example.com/user/alice/",
    "token_env": "ML_JUPYTER_PRODUCTION_TOKEN",
    "kernel": "python3"
  }
}
```

server_url 支持路径前缀；省略时使用当前 profile.api_endpoint。这里的示例域名必须替换为真实地址。不允许 URL 内嵌 Token、用户名密码、查询参数或 fragment。不自动跟随 HTTP/WS 重定向。连接不继承系统代理；需通过可直接访问的网关地址连接。

Token 来源优先为指定环境变量（默认 ML_JUPYTER_TOKEN），否则读取 token_file。token_file、可选 business_file 和 ca_file 均相对 config.json 所在目录解析。推荐为不同环境设置不同 token_env。ca_file 为内部 CA 证书；默认启用 TLS 校验，遵循已有环境 verify_ssl 设置。

生产不设置 business_file 时读取 CLI 原有 business.json，要求当前环境已有有效业务选择。每次 HTTP 与 WebSocket 握手都携带该环境 selected.businessId；错误或不一致时拒绝连接。access_control 开启时继续进行平台认证与权限检查，关闭时仅使用 Jupyter Token，不自动打开管理台登录。

原生 Jupyter 不按 businessid 提供租户隔离；生产仍须由 Jupyter 身份、工作空间权限及网关完成真正隔离。

## Web Studio 动态模式

Web Studio 模式通过当前平台登录态查询实例并动态获取 Jupyter 地址，不读取 direct 模式的 `token_env`、`token_file` 或 `business_file`。配置示例：

```json
{
  "name": "production",
  "api_endpoint": "https://console.example.com/dashboard",
  "jupyter": {
    "mode": "webstudio",
    "server_urls_by_region": {
      "cn-southwest-2": "https://10.1.1.1:8443",
      "cn-north-4": "https://10.1.1.1:8000"
    },
    "kernel": "python3"
  }
}
```

CLI 使用 queryEnvList 返回的实例 `region` 精确选择网关前缀，再拼接 accessUrl 返回的 `/lab?token=...` 路径。同一平台环境下的不同实例可以使用不同前缀。映射模式不向单一 `server_url` 或其他 region 回退；缺少 region、缺少映射或绝对 accessUrl 跨源时拒绝连接。

```bash
ml login
ml business use
ml webstudio list --status online
ml webstudio login <envId>
ml webstudio show
ml jupyter doctor
ml jupyter notebook run examples/jupyter/hello.ipynb --download results
ml jupyter terminal open
```

所有 Jupyter 命令均支持 `--studio-id ENV_ID` 临时指定实例。未指定时使用 `webstudio login` 保存的默认实例；每次操作仍重新查询实例状态、region 和访问地址，不复用旧 Token。

Token 非空时，CLI 访问 `/lab?token=...` 建立会话并发送 Token 认证头；Token 为空时不发送 Authorization。HTTP 写请求复用 Jupyter 下发的 Cookie 与 XSRF 信息，WebSocket 复用同源 Cookie。平台登录 Cookie 和 CSRF 不会转发给 Jupyter。

## 已知边界

- 只上传指定 Notebook；相对依赖文件不会自动同步。先放入远程目录，再用 --cwd 指定。
- 默认在本次远程 ml-runs/UUID 目录执行；--cwd 指定时在该目录执行，Notebook 快照仍存入它下面的 ml-runs/UUID。
- 不覆盖原始 Notebook；保留输入和执行输出副本。远程目录不会自动删除，按需人工清理。
- 文本实时输出，图像/HTML 保存在 Notebook 内，不单独导出；交互 Widget 状态、完整实时日志落盘、大型输出限流和任意产物下载不在首期。
- 前台执行退出、断线或休眠可能导致结果不完整；绝不自动重放执行请求。收到 Ctrl+C 会尝试中断并清理本次 Kernel。
- Kernel 清理不能撤销已经发生的外部写入，也不保证回收代码自行分离的后台进程。
- 同一 Terminal 多端连接共享 Shell；避免多人同时输入。
- Web Studio 命令会将包含 Token 的完整访问地址输出到 stderr 用于排障，不要把输出上传到公共日志。
- `doctor` 的 Kernel 和 Terminal GET 检查通过，不代表 Terminal 创建权限或 WebSocket 一定可用；实际执行和 attach 才会验证对应能力。

## 验证与打包

```bash
.venv/bin/python -m pip install pytest build
.venv/bin/python -m pytest -q
ML_JUPYTER_TEST_CONFIG="$PWD/.jupyter-local/config.json" .venv/bin/python -m pytest -q tests/test_jupyter_live.py
.venv/bin/python -m build
```

真实服务测试会创建并清理测试 Kernel 和 Terminal，保留测试执行目录；请仅对专用开发服务运行，不指向生产。
