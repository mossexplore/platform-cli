# CLI 独立演示环境使用指南

演示环境和正式环境都使用 `ml` 命令。演示环境使用合成数据，不连接真实平台。正式 CLI 安装包不包含演示实现、种子或专用依赖。

## 权限接入前提

业务数据是模拟的，权限检查、版本准入和调用日志走真实权限管理系统。请管理员登记 `demo-dev` / `https://demo-dev.mock.invalid`、`demo-test` / `https://demo-test.mock.invalid` 两个独立环境，并为实际演示账号分配所需授权。不要复用正式环境的 origin 或修改正式授权。安装器不创建账号或授权。

权限服务当前按客户端上报用户名检查授权，不验证真实平台登录身份；本地演示登录不能当作真实身份认证。账号须由管理员指定。权限服务不可用或拒绝时，业务命令停止。离线包只保证离线安装依赖，运行仍需要能访问权限服务。`ml context` 可离线查看权限地址及账号。

## 安装与录屏

解压独立的 `wiserec-cli-<版本>-demo-online.zip`，在解压目录执行：

```bash
python install-demo.py --permission-url https://PERMISSION_HOST --username YOUR_ACCOUNT
```

需要 Python 3.9 或更新版本。离线包必须在与构建机兼容的 Python、操作系统和架构上安装；不包含 Python 本体。安装目录必须是全新目录，不覆盖已有演示或正式安装。

Windows 双击 `start-demo.cmd`，Linux/macOS 执行 `./start-demo.sh`。启动器只设置当前子终端的环境变量，不修改系统 PATH，不修改标题和提示符。

```bash
ml context
ml login
ml train list
ml dataset list
ml model list
ml deployment template list
```

录屏前使用 `ml context` 确认“演示（模拟数据）”。关闭专用终端即可退出；不要在普通终端中手工设置演示 PATH。模拟后端发生错误时命令直接失败，不会切换真实平台。

## 连续业务操作

以下占位符从相应列表中获取：

```bash
ml train start TASK_ID
ml train history list TASK_ID
ml train clone TASK_ID --name demo-copy --yes
ml algorithm clone ALGORITHM_ID --name demo-algorithm --version demo --yes
ml dataset files upload DATASET_ID samples/clicks.csv
ml dataset files list DATASET_ID
ml model deploy MODEL_ID --template TEMPLATE_ID --dry-run
ml model deploy MODEL_ID --template TEMPLATE_ID --yes
ml service list
```

写入保存在工作区数据库，关闭终端后仍保留。模拟任务启动后处于运行中，使用管理脚本推进逻辑时间至少 60 秒后转为成功。不会实际训练模型或创建云资源。

## 工作区管理

Windows 使用 `manage-demo.cmd`，POSIX 使用 `./manage-demo.sh`：

```text
manage-demo.cmd status
manage-demo.cmd identity --username AUTHORIZED_ACCOUNT
manage-demo.cmd advance --seconds 60
manage-demo.cmd fault --path /ai/backend/modelDev/modelTrain/list --status 503 --count 1
manage-demo.cmd reset --scenario empty --yes
manage-demo.cmd reset --scenario standard --yes
```

账号名称来自权限系统；identity 不会授予权限。切换账号后执行 `ml login`，原凭据会被清除，业务选择按新账号重新初始化。

场景：standard、empty、large、expired-session、partial-failure、malformed-response。权限拒绝及版本封禁应在权限管理系统配置。reset、advance、fault 和 Jupyter 启动前需要通过真实授权。重置会清理管理范围内的模拟业务和客户端状态，保留 exports 和用户文件。存在 Jupyter 登记时拒绝重置。

模拟上传单次请求限制为 16 MiB，超限明确报错。正式平台的上传容量限制保持不变。

## Jupyter 实际执行

完整的命令执行需要 Linux/POSIX；Windows 可用 Linux 虚拟机。Jupyter 是实际执行环境，不是操作系统沙箱。

在演示专用 Python 环境安装可选依赖（联网示例）：

```bash
runtime/bin/python -m pip install 'jupyterlab>=4,<5' 'ipykernel>=6,<7'
./manage-demo.sh jupyter --port 18888
```

该命令在前台运行；可在另一终端使用 `manage-demo` 的 `jupyter-status` 查询状态，或 `jupyter-stop` 通过本地认证接口停止服务。另开演示专用终端：

```bash
ml webstudio list
ml webstudio start STUDIO_ID
ml webstudio login STUDIO_ID
ml jupyter doctor
ml jupyter files list
```

仅允许连接演示管理器登记的 127.0.0.1 服务。关闭前台 Jupyter 使用 Ctrl+C；管理器只终止自己创建的子进程，并清理连接登记。未启动服务时执行命令会失败，不返回伪造执行结果。

## 源码开发和构建

在独立开发虚拟环境中：

```bash
python -m pip install -e . -e ./devtools/mock-platform
python -m wiserec_cli_mock.manage --workspace /absolute/new-demo init --permission-url https://PERMISSION_HOST --username YOUR_ACCOUNT
```

开发调用可设置 `WISEREC_DEMO_WORKSPACE` 并执行 `python -m wiserec_cli_mock.bootstrap`。外部分发使用同名 `ml` 包装入口。

```bash
python -m pip install build
python scripts/demo/build-demo.py
python scripts/demo/build-demo.py --offline
```

正式出包继续使用 `scripts/windows/build-release.cmd` 或 `scripts/build-install.cmd`。演示包独立构建，不加入正式发布依赖。GitHub 仓库源码归档仍包含仓库内的开发源码；正式 Python 分发包和安装 ZIP 排除这些内容。
