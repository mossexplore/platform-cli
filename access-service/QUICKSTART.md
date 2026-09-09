# Linux 解压运行

支持 Linux x86_64、glibc ≥ 2.28（如 Ubuntu 20.04+、Rocky / AlmaLinux 8+）。不支持 ARM64、Alpine / musl 或 CentOS 7。包内包含 Python 3.12 和全部 Python 依赖，无需安装系统 Python、sudo 或 systemd，运行时不访问公网。

## 1. 解压

```bash
sha256sum -c cli-access-linux-x86_64-python312.tar.gz.sha256
tar -xzf cli-access-linux-x86_64-python312.tar.gz
cd cli-access
```

## 2. 填写数据库连接

准备可访问的 MySQL 8.x 数据库（本包不含 MySQL）。新建数据库可参考：

```sql
CREATE DATABASE cli_access CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

账号需具备本数据库读写及建表、索引等迁移权限。已有权限服务可以使用原有数据库，但升级前应备份数据库。

```bash
cp .env.example .env
chmod 600 .env
vi .env
```

至少修改 `DATABASE_URL`：

```dotenv
DATABASE_URL=mysql+pymysql://账号:密码@数据库IP:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8008
TLS_CERT_FILE=
TLS_KEY_FILE=
```

数据库密码中的 `@`、`:`、`/`、`#` 等特殊字符须 URL 编码。以上为内网 HTTP 配置。

## 3. 启动

```bash
bash start.sh
```

首次运行自动准备内置 Python、离线安装依赖、初始化数据库；没有启用的管理员时，交互提示创建管理员，密码至少 12 字符。已有管理员和授权数据会保留。

浏览器打开 `http://服务器IP:8008`。按 Ctrl+C 停止；下次仍使用 `bash start.sh`。需要允许客户端连接服务器 TCP 8008 端口。

可在另一终端检查：

```bash
curl http://127.0.0.1:8008/healthz
```

正常返回 `{"status":"ok"}`。必须先完成一次交互式初始化，之后可后台运行：

```bash
nohup bash start.sh > server.log 2>&1 &
echo $! > server.pid
```

再次启动前确认前一进程已停止，避免端口冲突。退出 SSH 后持续运行并自动重启的正式服务可使用 README 中的 systemd 安装方式。

## 管理员维护

```bash
bash manage.sh create-admin
bash manage.sh reset-password
```

## 升级与接口兼容

在新目录解压，再将旧配置复制到新目录 `.env`，确认仍连接同一数据库后启动。不要复制旧 `.venv` 或覆盖正在运行的目录。本次管理界面改版及账号上报调整无需新增数据库迁移；启动器会检查现有结构。

此版本权限检查接收 CLI 当前登录账号，不调用业务平台 `/ai/user/info`。CLI 必须同步更新为发送 `username` 的版本，否则返回 HTTP 422。

## 常见问题

- `CHANGE_ME` 提示：尚未填写实际数据库连接信息。
- 数据库初始化失败：检查 MySQL 服务、账号来源限制、数据库是否存在及迁移权限。
- 校验失败：重新传输完整压缩包；不要编辑包内源文件及校验清单，配置只修改 `.env`。
- 架构或 glibc 不兼容：提供 `uname -m` 和 `getconf GNU_LIBC_VERSION` 输出，需另行构建对应运行包。
- 8008 已被占用：停止旧服务或修改 `.env` 中的 `LISTEN_PORT`。
