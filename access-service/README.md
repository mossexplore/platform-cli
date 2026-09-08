# CLI 权限管理服务（内网离线部署）

独立 Python 服务，提供人员、环境、访问授权与操作审计页面，使用 MySQL 保存数据。管理员按环境授予账号访问权限，可停用、撤销或设置到期时间。无需 Docker、Node.js、Redis 或独立前端构建。

## 工作方式与边界

1. CLI 沿用现有平台登录，执行业务命令前向权限服务发送平台 Cookie、CSRF、当前环境和 `businessid`。
2. 服务只访问管理员登记的固定平台 HTTP 或 HTTPS 地址 `/ai/user/info`，验证身份；不信任 CLI 自报的账号，不存储平台凭据。
3. 实时检查账号、环境、授权状态和有效期。拒绝、网络错误、数据库错误均不放行业务操作。
4. CLI 检查通过后，仍直接访问业务平台，由平台执行原有权限校验。

这是受管理客户端的访问机制。用户若修改 CLI 源码、删除本地权限配置或直接调用平台接口，仍可能绕过 CLI 检查。若需要防止这种绕过，必须在业务后端或网关强制验证授权。当前版本提供账号 × 环境粒度，不含单条命令、租户或资源级授权。管理员账号只用于管理台，不替代平台账号。

## 离线包内容与兼容性

发布包 `cli-access-linux-x86_64-python312.tar.gz` 包含：

- 服务源代码、管理页面、安装脚本、systemd 配置。
- 独立 CPython 3.12.14，安装到 `/opt/cli-access/python`。
- 所有第三方依赖的 Linux wheels、固定版本和 SHA256 校验清单。
- HTTP / HTTPS 配置示例、操作说明。

服务器现有 Python 3.7.4 不参与运行，也不会被替换。当前整包要求 Linux x86_64、**glibc ≥ 2.28**、systemd、bash、tar、sha256sum、getconf、sort。独立 Python 自身支持更早的 glibc，但整包按所带二进制依赖取更高基线；安装时会检查。MySQL 8.x 需由内网已有数据库提供，不包含数据库服务安装包。

联网打包机可使用 macOS 或 Linux，须具备 Python 3.12 和 pip。包内依赖严格限定 Linux x86_64，不复制打包机的虚拟环境。

## 联网机器打包

已固定的官方运行时来源：[python-build-standalone 20260901](https://github.com/astral-sh/python-build-standalone/releases/tag/20260901)。首次下载：

```bash
curl -fL 'https://github.com/astral-sh/python-build-standalone/releases/download/20260901/cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz' -o python-runtime.tar.gz
python3.12 build_offline.py --runtime ./python-runtime.tar.gz --output ./dist
```

脚本先校验固定运行时哈希，再下载 `requirements.lock` 中的依赖，生成归档及 `.sha256` 文件。将这两个文件上传到服务器。源码中的 `requirements.txt` 仅用于维护版本约束，发布使用已验证的 `requirements.lock`；更换依赖需重新测试和打包。

## 内网服务器安装

**1. 准备 MySQL 数据库和专用账号。** 由数据库管理员创建 UTF-8 数据库，建议使用区分大小写的排序规则：

```sql
CREATE DATABASE cli_access CHARACTER SET utf8mb4 COLLATE utf8mb4_bin;
```

为专用账号授予该数据库的 SELECT、INSERT、UPDATE、DELETE、CREATE、ALTER、INDEX、REFERENCES 权限。限制账号来源地址，不使用 MySQL root 运行服务。数据库可位于另一台内网机器。

**2. 解压并初始化配置。**

```bash
sha256sum -c cli-access-linux-x86_64-python312.tar.gz.sha256
tar -xzf cli-access-linux-x86_64-python312.tar.gz
cd cli-access
sudo bash install.sh
```

首次执行创建 `/etc/cli-access/env` 后停止，这是正常配置步骤。填写 `DATABASE_URL` 和监听地址，再次执行安装。数据库密码中的 `@`、`:`、`/` 等特殊字符需要 URL 编码。

**3. 配置内网 HTTP（无需证书）。**

```dotenv
DATABASE_URL=mysql+pymysql://cli_access:URL_ENCODED_PASSWORD@mysql.internal:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8008
TLS_CERT_FILE=
TLS_KEY_FILE=
```

HTTP 模式必须设置 `COOKIE_SECURE=false`，否则浏览器无法正常使用管理登录会话。
仅用于已确认的可信内网；HTTP 会明文传输管理员密码和平台登录凭据。

若需要 HTTPS，设置 `COOKIE_SECURE=true`，同时填写 TLS_CERT_FILE 和 TLS_KEY_FILE；
证书与私钥需允许 cli-access 账户读取。已有 HTTPS Nginx 时，可参考 `nginx.conf.example`，
服务绑定 127.0.0.1 并清空两个 TLS 路径。管理页面不依赖任何公网 CDN。

**4. 完成离线安装并创建管理员。**

```bash
sudo bash install.sh
cd /opt/cli-access
sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env create-admin
sudo systemctl restart cli-access
sudo systemctl status cli-access
```

安装仅使用 `pip --no-index --find-links --require-hashes` 读取包内文件，不访问外网、不在线安装系统软件。管理员密码交互输入、不回显、不作为命令参数；至少 12 个字符，无默认管理员或默认密码。

浏览器打开 `http://你的权限服务器IP:8008`。先添加环境，再添加人员，最后配置访问授权。环境标识对应 CLI `profiles[].name`，平台地址对应该环境 `api_endpoint` 的源地址（不含 `/dashboard`）；人员账号对应平台 `/ai/user/info` 返回的 `result.username`。

## CLI 接入

在 CLI 使用的 `config.json` 顶层添加：

```json
"access_control": {
  "enabled": true,
  "url": "http://permissions.internal:8008",
  "timeout_seconds": 15
}
```

`url` 支持 HTTP 或 HTTPS 源地址。HTTPS 连接仍校验证书，不继承日志下载的 `verify_ssl: false`。需要企业 CA 时，通过客户端进程的 `SSL_CERT_FILE` 配置信任证书包。

```bash
ml login
ml business use
ml access status
ml train list
```

每次业务命令都会重新检查授权，不在磁盘缓存“允许访问”。停用后会阻止下一条业务命令，已经开始的请求/下载不会被追溯终止。`businessid` 从当前环境 `business.json` 的 `selected.businessId` 获取，未选择业务时先提示执行 `ml business use`。

登录、退出、帮助、版本、环境切换、本地业务上下文管理保留可用，以便用户完成登录及初始配置。业务数据查询、更新与获取下载地址都通过公共运行时检查权限；一次命令中的多个相关平台请求复用该次检查结果。

为允许先部署服务、再分批接入，未配置 `access_control` 时兼容现有行为；显式配置后默认启用，地址错误直接报错。正式分发必须由管理员设置正确地址与 `enabled: true`。升级默认配置会保留既有权限配置。此客户端设置不构成防篡改安全边界。

## 日常维护

```bash
sudo journalctl -u cli-access -n 100 --no-pager
sudo systemctl restart cli-access
cd /opt/cli-access
sudo .venv/bin/python -m app.manage --env-file /etc/cli-access/env reset-password
```

重置管理员密码会撤销其全部会话。管理会话默认 8 小时，停用管理员后原会话立即不可用。表单含 CSRF 校验；登录按来源地址限制 15 分钟内最多 10 次尝试。生产有高并发或暴力访问风险时，可在现有网关增加请求限流，示例 Nginx 已包含限流。

管理操作记录操作者、修改前后值、北京时间。所有数据库时间存 UTC，页面转换为 UTC+8；授权到期时间按北京时间输入。平台凭据和管理员密码不写入审计。定期备份 MySQL；审计长期增长需结合内部保留策略归档。

`GET /healthz` 检查数据库及结构版本，正常返回 `{"status":"ok"}`。当前结构版本为 2，升级会新增 cli_call_logs 表并保留原有数据，迁移可重复执行；后续数据库结构升级必须新增显式迁移。更新前备份数据库与 `/etc/cli-access/env`，上传新包并重新运行安装；配置保留，服务会短暂停止。

若目标 glibc 小于 2.28，安装会明确拒绝，请基于实际系统另行准备兼容依赖包，不要强制替换系统 glibc。若平台身份接口不可达、TLS 不受信任、会话失效或响应缺少账号，授权检查会失败，需检查权限服务到业务平台的网络和证书。

## 开发验证

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock pytest
.venv/bin/python -m pytest tests -q
```

自动化服务测试使用临时 SQLite 和模拟的平台身份响应，覆盖登录、CSRF、授权、立即撤销、时间转换、错误与审计；生产配置只接受 MySQL。发布前还需在目标 Linux 验证 MySQL 连接、HTTPS 证书及真实平台 `/ai/user/info` 响应。不要将模拟测试视为真实平台验收。

## 已部署版本升级到 HTTP

在新离线包解压目录运行 `sudo bash install.sh`。安装脚本保留已有 `/etc/cli-access/env`，
因此需手动将其调整为上述 HTTP 配置（保留实际 DATABASE_URL），然后重启：

```bash
sudo systemctl restart cli-access
curl http://127.0.0.1:8008/healthz
```

新安装脚本固定 umask 为 022，并修复旧安装中 Python、虚拟环境和程序目录对服务组不可读、
不可执行的问题，不修改数据库配置和证书文件权限。CLI 客户端也需要更新到支持 HTTP 的版本，
再将 access_control.url 改为 `http://服务器IP:8008`。

## 同一账号授权多个环境

人员只需创建一次。在「访问授权」页面输入账号，勾选多个环境，设置有效期、备注及允许访问状态，
点击「保存所选环境授权」。所选环境的授权统一新增或更新，未选环境的已有授权不变；重复提交不会产生重复记录。
下方列表仍按账号与环境分别展示，可单独撤销某个环境或调整其有效期。停用人员则阻止该账号访问所有环境。
本次变更无需修改已有数据库结构。CLI 切换环境后会检查该环境对应的授权。

## CLI 调用日志（MySQL）

每次权限检查写入 `cli_call_logs`，记录已验证用户名、命令名称、环境、当前业务 ID、来源 IP、
授权是否通过、原因及调用时间。页面「CLI 调用日志」支持按用户名、环境、命令、授权结果、
北京时间范围查询，按时间倒序分页，每页 20 条。需管理员登录才能查看。

记录的是业务命令的授权检查尝试，不能用授权通过推断业务执行成功。登录刷新导致重新检查时可能出现多条记录。
身份尚未验证时账号显示「未验证」，旧版 CLI 未提供命令名称时显示 `unknown`。
命令名由新版 CLI 上报，仅包含命令层级，不含 taskId、密码、自定义参数、Cookie 或 CSRF。
CLI 上报的命令名用于追踪，不是服务端验证过的执行证明。来源 IP 为服务端连接地址，使用代理时需正确设置可信代理。

未启用权限检查、帮助、登录退出、本地配置操作、网络请求未到达权限服务等情况不会产生此表记录。
数据库不可用时无法持久化日志，权限检查会失败并阻止业务操作。日志写入失败也不会放行业务请求。
现有管理员操作审计仍保留在「操作审计」页面，和用户调用记录分别查询。

上传新版离线包后重新运行安装脚本，即会从结构版本 1 升级至 2，无需手动建表。
CLI 也需更新到本次代码版本，才能显示具体命令名称。服务重启后可运行 `ml train list`，
再到管理台的「CLI 调用日志」查询对应记录。

环境中的「平台地址」填写业务平台地址，而非权限管理服务地址。支持 HTTP 或 HTTPS，
必须与 CLI 对应环境 api_endpoint 的协议、主机和端口一致；不包含 /dashboard 等路径。
例如 api_endpoint 为 http://platform.internal:8080/dashboard，页面填写 http://platform.internal:8080。
