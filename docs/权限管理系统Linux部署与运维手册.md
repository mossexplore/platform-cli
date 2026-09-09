# 权限管理系统 Linux 部署与运维手册

适用版本：项目 **0.3.35**，数据库结构版本 **6**。本文依据当前离线包的启动、安装、配置及迁移代码编写。命令中的服务器 IP、数据库账号、密码和域名须替换为实际值。

## 1. 部署方式与运行条件

| 项目 | 要求或说明 |
| --- | --- |
| 系统 | Linux x86_64，glibc ≥ 2.28，例如 Rocky / AlmaLinux 8+、Ubuntu 20.04+ |
| 不适用 | ARM64、Alpine / musl、CentOS 7；需要另外构建对应包 |
| Python | 包含独立 Python 3.12.14 和全部 Python 依赖，不使用或替换系统 Python |
| 数据库 | 已有 MySQL 8.x；安装包不包含 MySQL |
| 系统工具 | bash、tar、sha256sum、getconf、sort、awk；检查脚本还使用常规核心工具 |
| 网络 | 服务到 MySQL 可达；客户端到权限服务或 Nginx 可达；离线安装不访问公网 |
| 默认端口 | 8008，可通过配置修改 |
| 公共路径 | 管理台、API、静态文件和健康检查统一以 `/cli-permission` 开头 |

部署前检查：

```bash
uname -m
getconf GNU_LIBC_VERSION
ss -lntp 'sport = :8008'
```

选择一种方式使用，不要让两种方式同时占用同一端口：

| 项目 | 解压目录直接运行 | systemd 服务安装 |
| --- | --- | --- |
| 适用场景 | 快速部署、手动运维、无 sudo 权限 | 长期运行、开机自启、异常退出自动重启 |
| 程序目录 | 自选，例如 `/srv/cli-access` | 固定 `/opt/cli-access` |
| 配置文件 | 解压目录中的 `.env` | `/etc/cli-access/env` |
| 启停方式 | `bash start.sh`、进程信号 | `systemctl` |
| 日志位置 | 当前终端或自己重定向的 `server.log` | `journalctl -u cli-access` |
| 管理命令 | `bash manage.sh ...` | `/opt/cli-access/.venv/bin/python -m app.manage ...` |

本文“暂停服务”指正常停止进程，需要时重新启动。不要使用 `kill -STOP` 挂起进程：它会保留监听端口却不处理请求，容易造成超时。

## 2. 下载、校验和解压

上传以下两个文件到 Linux 同一个目录：

- `cli-access-linux-x86_64-python312.tar.gz`
- `cli-access-linux-x86_64-python312.tar.gz.sha256`

在存放文件的目录执行：

```bash
sha256sum -c cli-access-linux-x86_64-python312.tar.gz.sha256
tar -xzf cli-access-linux-x86_64-python312.tar.gz
cd cli-access
sha256sum --check --quiet SHA256SUMS
```

第一项应显示 `OK`，最后一项成功时通常无输出。后续示例假定直接运行的解压目录是 `/srv/cli-access`；请按实际目录调整。

不要修改包内程序、启动脚本、`.env.example` 或 `SHA256SUMS`。启动器每次检查包内文件，修改后会报校验失败。业务配置写入新建的 `.env`，它不在包内校验清单中。

## 3. 准备数据库与配置

### 3.1 MySQL 数据库

由数据库管理员建立数据库和专用账号。建库示例：

```sql
CREATE DATABASE cli_access CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

专用账号需要该库的 SELECT、INSERT、UPDATE、DELETE、CREATE、ALTER、INDEX、REFERENCES 权限，来源地址允许权限服务器连接。初始化和升级需要建表及修改表结构权限。

已有服务升级时使用原库，不要重复建库，也不要把数据库名改成空的新库。开始升级前先备份，详见第 10 节。

### 3.2 配置项

直接运行时：

```bash
cd /srv/cli-access
cp .env.example .env
chmod 600 .env
vi .env
```

上面的复制只用于首次安装，已有 `.env` 不要覆盖。内网 HTTP 示例：

```dotenv
DATABASE_URL=mysql+pymysql://cli_access:URL_ENCODED_PASSWORD@数据库IP:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8008
TLS_CERT_FILE=
TLS_KEY_FILE=
```

| 配置项 | 如何填写 |
| --- | --- |
| `DATABASE_URL` | 固定使用 `mysql+pymysql://`；填写实际数据库账号、密码、地址、端口和库名 |
| `charset` | 使用 `utf8mb4`；不能填写排序规则 `utf8mb4_bin` 或 `utf8mb4_general_ci` |
| `COOKIE_SECURE` | 浏览器使用 HTTP 时为 `false`，使用 HTTPS 时为 `true` |
| `LISTEN_HOST` | 直接对外提供服务用 `0.0.0.0`；同机 Nginx 转发可用 `127.0.0.1` |
| `LISTEN_PORT` | 默认 `8008`；改动后同步调整防火墙、Nginx 和客户端地址 |
| `TLS_CERT_FILE` / `TLS_KEY_FILE` | 服务直接提供 HTTPS 时同时填写绝对路径；HTTP 或 Nginx 终止 TLS 时均留空 |

数据库密码里的 `@`、`:`、`/`、`#`、`%` 等特殊字符需 URL 编码。例如密码里的 `@` 写为 `%40`，`#` 写为 `%23`。不要把 Markdown 链接格式 `[地址](地址)` 复制到配置中。

HTTP 会明文传输登录信息，正式环境可通过第 7 节的 HTTPS Nginx 接入。systemd 模式下证书文件必须允许服务账号 `cli-access` 读取，且不能放在受保护的 `/root` 目录中。

程序加载配置文件时不会覆盖进程中已存在的同名环境变量。直接运行若发现修改 `.env` 不生效，检查启动终端是否预先导出了这些变量；确认不需要后清除，再启动：

```bash
unset DATABASE_URL COOKIE_SECURE LISTEN_HOST LISTEN_PORT TLS_CERT_FILE TLS_KEY_FILE
```

## 4. 方式一：解压目录直接运行

### 4.1 首次前台启动

```bash
cd /srv/cli-access
bash start.sh
```

启动器依次校验文件、准备内置 Python、离线安装依赖、迁移数据库，然后启动服务。首次安装没有启用的超级管理员时，会提示输入账号和密码；密码至少 12 字符，输入时不回显。

另开终端检查：

```bash
curl --noproxy '*' --connect-timeout 5 --max-time 15 \
  http://127.0.0.1:8008/cli-permission/healthz
```

正常响应为 `{"status":"ok"}`。浏览器访问 `http://服务器IP:8008/cli-permission`。

前台按 **Ctrl+C** 正常停止。关闭终端前需要持续运行时，先停止前台实例，再按下一节后台启动。

### 4.2 后台启动

必须先完成首次交互初始化。确认端口没有被其他实例占用，再执行：

```bash
cd /srv/cli-access
nohup bash start.sh >> server.log 2>&1 &
echo $! > server.pid
sleep 2
ps -p "$(cat server.pid)" -o pid,ppid,args
tail -n 80 server.log
```

`>>` 追加日志，保留已有内容；`>` 会覆盖原日志。`server.pid` 是本次启动的进程号记录，不是服务存活保证。启动脚本使用 `exec`，正常情况下记录的 PID 会成为 Python 服务 PID。

再次执行健康检查确认就绪。`nohup` 不提供开机自启或崩溃自动重启，需要这些功能时使用 systemd。

### 4.3 查看状态、暂停、恢复和重启

```bash
cd /srv/cli-access
ps -p "$(cat server.pid)" -o pid,ppid,args
ss -lntp 'sport = :8008'
```

停止前确认 PID 对应本服务，避免陈旧的 PID 文件误指向其他进程。确认后正常停止：

```bash
kill -TERM "$(cat server.pid)"
```

等待正在处理的请求结束，再检查端口和进程。没有 PID 文件时：

```bash
sudo ss -lntp 'sport = :8008'
ps -ef | grep -E 'app.portable|app.serve' | grep -v grep
```

从结果中找出本实例的 PID，再对该 PID 执行 `kill -TERM`。不要使用 `killall python` 或按所有 Python 进程批量结束。

如果正常停止长时间无效，检查日志并再次确认 PID 后，最后才使用 `kill -KILL 实际PID`；强制结束不会等待请求完成。

恢复运行：重新执行第 4.2 节后台启动命令。重启：先正常停止、确认端口释放，再启动。修改 `.env` 后也需要重启。

## 5. 方式二：安装为 systemd 服务

本方式需要 sudo/root 权限和 systemd。请在发布包解压目录运行安装，不要在 `/opt/cli-access` 中运行。

### 5.1 首次安装

```bash
cd /实际发布包解压目录/cli-access
sudo bash install.sh
```

第一次会创建 `/etc/cli-access/env` 并退出，提示先填写配置，这是正常步骤。编辑后重新安装：

```bash
sudo vi /etc/cli-access/env
sudo bash install.sh
```

安装器离线准备 `/opt/cli-access`，执行数据库迁移，启用开机自启并启动服务。随后创建超级管理员：

```bash
cd /opt/cli-access
sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env create-admin
sudo systemctl status cli-access --no-pager
```

systemd 不会交互创建账号，必须执行上述本地管理命令。配置位于 `/etc/cli-access/env`，修改解压目录 `.env` 对此模式无效。

### 5.2 日常启停

| 操作 | 命令 |
| --- | --- |
| 查看完整状态 | `sudo systemctl status cli-access --no-pager` |
| 判断是否运行 | `sudo systemctl is-active cli-access` |
| 启动 / 恢复 | `sudo systemctl start cli-access` |
| 暂停 / 正常停止 | `sudo systemctl stop cli-access` |
| 重启 | `sudo systemctl restart cli-access` |
| 开启开机自启 | `sudo systemctl enable cli-access` |
| 取消开机自启 | `sudo systemctl disable cli-access` |
| 停止并取消自启 | `sudo systemctl disable --now cli-access` |
| 查看实际服务配置 | `sudo systemctl cat cli-access` |

`stop` 不取消开机自启，`disable` 单独执行不停止当前进程。服务配置为失败后约 5 秒自动重启，因此不要用反复杀进程代替 `systemctl stop`。

修改 `/etc/cli-access/env` 后执行 `restart`；只有修改 systemd unit 或 drop-in 才需要先 `sudo systemctl daemon-reload`。每次重启后检查状态、日志和健康接口。

## 6. 日志在哪里，如何查看

### 6.1 运行日志

直接后台运行的日志就在启动时指定的文件，例如：

```bash
cd /srv/cli-access
tail -n 100 server.log
tail -F server.log
```

`tail -F` 持续查看，Ctrl+C 只退出日志查看，不会停止服务。相对路径 `server.log` 取决于执行重定向时的目录，服务不会自动在 `/root/cli-access` 创建该文件。

systemd 模式：

```bash
sudo journalctl -u cli-access -n 100 --no-pager
sudo journalctl -u cli-access -f
sudo journalctl -u cli-access --since '30 minutes ago' --no-pager
sudo journalctl -u cli-access -b --no-pager
```

导出近期日志供排查：

```bash
sudo journalctl -u cli-access --since '1 hour ago' --no-pager > cli-access-journal.log
```

日志时间以系统/journal 的时区设置为准；管理页面业务时间按北京时间显示。journal 的持久化和保留周期由服务器 journald 配置决定，不由应用控制。

### 6.2 三类记录的区别

| 类型 | 位置 | 内容与限制 |
| --- | --- | --- |
| 运行日志 | 终端、`server.log` 或 journal | 启动、关闭、程序异常等；**当前 `app.serve` 关闭 Uvicorn 逐请求 access log**，健康检查或权限请求成功不一定新增文本日志 |
| CLI 调用记录 | 管理台“CLI 调用日志”；MySQL `cli_call_logs` | 权限检查的账号、环境、命令、业务 ID、通过/拒绝等；通过不代表后续业务执行成功 |
| 管理操作审计 | 管理台“操作审计” | 管理员操作及变更信息；不保存明文密码 |

HTTP 422 这类字段校验失败不写 CLI 调用表；请求未到服务、未启用权限检查、执行帮助等本地命令也不会写入。数据库故障时无法持久化记录，检查会失败。因此“server.log 没新增内容”不能单独证明请求未到服务。

如果需要逐请求 HTTP 状态，查看已配置的 Nginx access/error 日志；路径取决于实际 Nginx 配置，常见为 `/var/log/nginx/access.log` 和 `/var/log/nginx/error.log`。不要为开访问日志直接改离线包源码，否则会触发完整性校验。

### 6.3 日志保留

`nohup` 文件不会自动轮转。可安排维护窗口：停止服务，将 `server.log` 改名归档，再后台启动生成新文件；长期运行建议采用 systemd 并由系统管理 journal 保留策略。

CLI 调用记录和审计在 MySQL 中，不会随文本日志删除而清除；需另行制定数据库归档策略。分享排障材料前检查其中是否包含配置、账号或其他内部信息。

## 7. 挂载现有 Nginx，统一前缀

Nginx 与权限服务位于同一台机器时，服务配置：

```dotenv
LISTEN_HOST=127.0.0.1
LISTEN_PORT=8008
COOKIE_SECURE=true
TLS_CERT_FILE=
TLS_KEY_FILE=
```

以上假定浏览器通过 Nginx HTTPS 访问。在已有 HTTPS `server {}` 中加入：

```nginx
location = /cli-permission {
    return 308 /cli-permission/;
}
location /cli-permission/ {
    proxy_pass http://127.0.0.1:8008;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $remote_addr;
    proxy_read_timeout 30s;
}
```

**`proxy_pass` 不带尾部斜杠，也不要 rewrite 去掉前缀。** 服务实际接收的路径必须是 `/cli-permission/...`。完整独立 HTTPS 配置及限流示例见包内 `nginx.conf.example`。

由运维人员按已有站点规则合并配置，检查后重载：

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --noproxy '*' --connect-timeout 5 --max-time 15 \
  https://实际管理域名/cli-permission/healthz
```

企业 CA 使用 `curl --cacert /实际/ca-bundle.pem ...` 验证。不要把关闭证书校验当作正式配置。

若 Nginx 不在同机，`127.0.0.1` 不可用，需要调整上游及监听地址、防火墙，并另行确认可信代理设置；当前服务仅信任来自 `127.0.0.1` 的转发头。

## 8. 管理员、环境与 CLI 配置

### 8.1 管理员账号

- 超级管理员可创建、启停普通管理员及重置其密码；普通管理员可管理人员、环境和业务授权，查看记录。
- 创建普通管理员时生成 32 字符随机密码，成功后可复制账号和密码；关闭后不再展示，可通过重置重新生成。
- 普通 HTTP 页面可能不允许浏览器自动复制，此时按提示手动 Ctrl+C。
- 停用或重置密码会使该管理员已有会话失效；重新启用需重新登录。
- 管理员账号与 CLI 业务人员账号独立，管理员身份不会自动赋予业务环境授权。

服务器本地维护（直接运行方式）：

```bash
cd /srv/cli-access
bash manage.sh create-admin
bash manage.sh reset-password
```

systemd 方式：

```bash
cd /opt/cli-access
sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env create-admin
sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env reset-password
```

本地 `create-admin` 创建的是超级管理员，需交互设置密码；`reset-password` 不改变账号启用状态或角色。若没有可用超级管理员，可由服务器维护人员新建一个不同账号的超级管理员恢复管理入口。

### 8.2 环境和授权

先在“环境管理”新增环境，再在“人员与授权”新增人员并选择环境，或通过该人员的“管理授权”配置权限；确认人员、环境、授权都启用且授权未过期。例如：

| 配置位置 | 示例 |
| --- | --- |
| CLI 当前环境 | `dev` |
| CLI 的 `dev.api_endpoint` | `https://10.12.12.138/wiserec/main` |
| 管理台环境标识 | `dev` |
| 管理台平台地址 | `https://10.12.12.138` |
| 管理台人员账号 | 与 CLI 当前环境登录账号一致 |

平台地址只取协议、主机和端口，不含业务路径；显式非默认端口需要保留。不要填写权限服务自身地址。权限服务不调用业务平台 `/ai/user/info`；它根据 CLI 上报字段和本地授权数据判定。

### 8.3 CLI 接入

在现有 `config.json` 顶层合并以下字段，不要覆盖其他环境配置：

```json
{
  "access_control": {
    "enabled": true,
    "url": "http://权限服务器IP:8008/cli-permission",
    "timeout_seconds": 15,
    "use_env_proxy": false
  }
}
```

通过 Nginx 时 URL 改为 `https://实际管理域名/cli-permission`。0.3.33 权限请求默认忽略环境代理；`use_env_proxy: true` 才恢复环境代理。该设置不改变业务平台请求的代理策略。HTTPS 仍验证证书，企业 CA 可通过 CLI 进程的 `SSL_CERT_FILE` 配置。

```bash
ml --version
ml access status --diagnose
```

Windows 指定配置文件示例：

```powershell
ml --config "C:\Users\你的账号\AppData\Roaming\ml\config.json" access status --diagnose
```

确保已完成当前环境登录和业务选择。诊断输出可确认实际权限 URL、环境、平台源地址、代理策略、连接目标和 HTTP 状态。

## 9. 健康检查与权限检查验证

健康检查仅证明从执行机器到该地址的连接及服务数据库健康，不代表其他客户端网络或业务授权已通过。

### 9.1 分段检查

1. 权限服务器本机请求 `http://127.0.0.1:8008/cli-permission/healthz`。
2. CLI 所在机器请求实际配置的权限地址 `/cli-permission/healthz`。
3. 使用 Nginx 时分别验证服务直连和 Nginx 域名。
4. 最后从 CLI 所在机器执行完整权限请求和 `ml access status --diagnose`。

Linux 完整权限请求示例（账号和环境先在管理台授权；业务 ID 换成当前环境已选业务）：

```bash
curl --noproxy '*' -i --connect-timeout 5 --max-time 15 \
  -H 'Content-Type: application/json' \
  -H 'businessid:当前业务ID' \
  --data '{"username":"l00123456","environment":"dev","platform_origin":"https://10.12.12.138","command":"ml access status"}' \
  http://权限服务器IP:8008/cli-permission/api/v1/access/check
```

成功示例：`{"allowed":true,"username":"l00123456","environment":"dev"}`。HTTP 200 也可能携带 `allowed:false`，需要同时看响应体。

提交 `{}` 返回 422 是正常的字段校验结果，只能说明到达了接口，不能判断真实账号是否有权限。

## 10. 升级、备份与恢复

### 10.1 升级前备份

保存旧发布包及对应校验文件，备份当前配置和 MySQL。以下备份示例需要系统安装 MySQL 客户端并具备备份权限；密码通过提示输入：

```bash
umask 077
backup_dir="/安全备份目录/cli-access-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$backup_dir"
# 直接运行方式；systemd 方式改为备份 /etc/cli-access/env
cp /srv/cli-access/.env "$backup_dir/env.backup"
mysqldump -h 数据库IP -P 3306 -u 备份账号 -p \
  --single-transaction --no-tablespaces cli_access > "$backup_dir/cli_access.sql"
```

确认备份命令成功，并按组织流程验证备份可恢复；有正式数据库备份平台时使用现有平台。停止旧应用写入后再做最终升级备份，可明确回退的数据时间点。

### 10.2 直接运行方式升级

1. 在新目录解压并验证新包，不覆盖正在运行的目录。
2. 备份数据库和旧 `.env`，正常停止旧服务并确认端口释放。
3. 将旧 `.env` 复制到新目录，确认连接原有数据库。
4. 在新目录执行 `bash start.sh`，观察迁移及启动结果。
5. 验证健康接口、管理员登录、权限检查及调用记录，再转为后台运行。

不要复制旧 `.venv`、`python`、`.portable-ready` 或旧 `SHA256SUMS`。当前结构版本为 6：版本 2 升级时新增 `admins.role`，版本 3 升级时新增 `cli_call_logs.full_command`，版本 4 升级时新增人员和环境的时间及操作人字段；原有管理账号保留为超级管理员，原停用状态保持。版本 1 会先补调用日志表再升级。迁移可重复执行，但 MySQL DDL 自动提交，不能假定事务失败会撤销全部结构变更。

需要单独迁移时，在新包目录配置好 `.env` 后执行：

```bash
bash manage.sh migrate
```

### 10.3 systemd 方式升级

备份数据库及 `/etc/cli-access/env`，停止旧服务，然后在新发布包解压目录执行：

```bash
sudo systemctl stop cli-access
sudo bash install.sh
sudo systemctl status cli-access --no-pager
sudo journalctl -u cli-access -n 100 --no-pager
```

安装器保留 `/etc/cli-access/env`，会更新程序、迁移数据库并启用及启动服务；之前取消的开机自启也会被重新启用。升级后按实际要求调整。

### 10.4 回退原则

数据库已升为版本 6 时，不要直接启动只支持旧结构版本的程序。先停止新服务，由数据库维护人员确认兼容性，或将升级前备份恢复到独立数据库，配合对应旧程序及配置验证后切换。

恢复旧备份会丢失备份之后新增的授权、账号和审计记录。应先保留故障现场数据库和配置，并明确恢复时间点；本文不提供会覆盖生产数据库的一键恢复命令。

## 11. 常见故障处理

| 现象 | 检查与处理 |
| --- | --- |
| `1 computed checksum did NOT match` | 区分压缩包外层校验与包内校验；外层失败重新传输匹配的包和校验文件；包内失败看具体文件名，在新目录重新解压，只复制 `.env`，不要改校验清单绕过检查 |
| `CHANGE_ME` | 修改当前部署方式对应的数据库配置，不能沿用示例密码 |
| PyMySQL 报 `NoneType ... encoding` | 先检查 URL 的 `charset`；使用 `utf8mb4`，不要用排序规则名；确认正在读取正确配置文件并重启 |
| 数据库初始化失败 | 检查数据库地址、端口、账号来源限制、库是否存在和迁移权限，确认密码特殊字符已编码 |
| 后台启动提示没有超级管理员 | 先前台初始化；或先 `bash manage.sh migrate`，再 `bash manage.sh create-admin` |
| 8008 已占用 | 用 `ss -lntp` 找到原进程，按其部署方式停止；不要重复启动或随意结束其他进程 |
| 管理台登录后回到登录页 | HTTP 下确认 `COOKIE_SECURE=false`，HTTPS 下为 true；检查代理前缀和浏览器 Cookie，升级后重新登录 |
| HTTP 404 | 检查所有路径是否包含 `/cli-permission`，Nginx 是否误去除了前缀 |
| HTTP 422 | 请求字段缺失或类型错误；用第 9 节完整 JSON，并确认 CLI 版本及实际配置 |
| `ENVIRONMENT_DISABLED` | 在管理台启用对应环境 |
| `ENVIRONMENT_MISMATCH` | 核对平台源地址的协议、主机、端口与 CLI 当前环境一致 |
| 用户或授权被拒绝 | 检查人员启用、对应环境授权启用及到期时间；管理员身份不等于 CLI 业务授权 |
| curl 连接超时 | 从出错的客户端检查目标地址、端口、路由、防火墙；`curl -v` 确认是否连接了代理 |
| HTTP 504 | 请求链上的网关等待上游超时；结合实际响应头和网关日志定位，不能仅靠健康检查或 504 断定哪一段故障 |
| `server.log` 没有请求日志 | 当前关闭逐请求 access log，参考第 6 节；同时查看数据库调用记录和 Nginx 日志 |
| 管理员“一键复制”失败 | 普通 HTTP 的浏览器限制；按提示手动复制，或使用 HTTPS |

### 11.1 代理排查

`curl --noproxy '*'` 仅让这一次 curl 直连。正常 curl 与带此参数的结果不同，说明需要检查 curl 所在进程的代理环境。临时清除当前终端代理可执行：

```bash
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
```

此操作不会修改其他终端、已运行服务或永久配置。永久设置可能来自 shell 启动文件、系统环境或服务配置，应定位设置来源再修改。诊断输出可能含代理账号信息，分享前脱敏。

CLI 0.3.33 的权限请求默认直连；如果诊断仍显示沿用环境代理，检查实际版本、所用 config.json 及 `use_env_proxy`，不要仅凭终端 curl 推断 CLI 的连接路径。

### 11.2 定位 504 的地址链

对于同机 Nginx 部署，链路是：

```text
CLI 所在机器 → 权限域名/Nginx:443 → 127.0.0.1:8008 权限服务 → MySQL:3306
```

服务不再访问业务平台 `/ai/user/info`。先从权限服务器验证本机 8008，再从客户端验证域名和实际 API；结合 CLI `--diagnose` 的连接目标、响应头及 Nginx error log 中的上游地址，确定失败发生的位置。不要只延长超时时间掩盖无法连接的问题。

## 12. 日常运维速查

| 需求 | 直接运行 | systemd |
| --- | --- | --- |
| 配置文件 | 解压目录 `.env` | `/etc/cli-access/env` |
| 启动 | `bash start.sh` 或第 4.2 节后台命令 | `sudo systemctl start cli-access` |
| 暂停 | 前台 Ctrl+C；后台核对 PID 后 `kill -TERM PID` | `sudo systemctl stop cli-access` |
| 重启 | 确认停止后重新启动 | `sudo systemctl restart cli-access` |
| 看日志 | `tail -F server.log` | `sudo journalctl -u cli-access -f` |
| 健康检查 | 两种方式均为 `curl --noproxy '*' http://127.0.0.1:8008/cli-permission/healthz` | 同左 |
| 业务授权记录 | 管理台“CLI 调用日志” | 同左 |

相关资料：[服务说明](../access-service/README.md)、[包内快速开始](../access-service/QUICKSTART.md)、[CLI 参考使用指南](CLI参考使用指南.md)。本手册根据代码核对，目标 Linux、MySQL 与 Nginx 的实际可用性仍需按上述步骤在部署环境验收。

## 13. 完整命令日志与分页更新

所有列表默认每页 10 条，访问授权每页 10 个账号。CLI 调用日志的“完整命令”显示新版 CLI 上报的参数序列，保留普通选项和值，对已识别的敏感参数脱敏。最长 8192 字符，超长有截断标记；旧客户端及历史数据为“未上报”。升级服务数据库至版本 4 后，还需更新 CLI 才能收集该字段。该记录不包含 shell 管道、重定向及文件内容，也不代表业务执行成功。

列表默认按时间倒序：人员、环境和管理员优先按修改时间，缺失时使用创建时间；调用日志按调用时间，操作审计按操作时间。同一时间按编号倒序，未知时间排在最后。数据库结构版本 6 为管理员补充创建时间和修改时间，历史未知时间保持为空；管理员创建、启停和重置密码会记录修改时间。
