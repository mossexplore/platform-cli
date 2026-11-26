# `kb-gateway` 共享 Wiki 只读网关配置、部署与使用指南

本文档严格依据仓库当前源码实现编写，覆盖 `kb-gateway`（`0.1.0`）、`access-service` 签票端（`1.1.2`）与 `cli-go` 客户端（`1.1.2`）的完整配置、部署、运维排障与使用方式。

---

## 1. 架构与上线顺序

### 1.1 请求链路与职责边界

```text
ml kb ... (Go CLI 1.1.2+)
   │
   ├── 1. POST /cli-permission/api/v1/access/check (HTTPS, 带真实 businessid)
   │      └─► access-service 1.1.2+
   │            • 校验账号授权、环境命令禁令、版本准入
   │            • 服务端对 full_command 脱敏限长并写 CallLog（沿用结构 15，零迁移）
   │            • 签发 300 秒动作绑定 HMAC-SHA256 票据（含服务端 UUIDv4 ticket_id）
   │
   └── 2. GET /v1/kb/{list|pages|search|page} (HTTPS, 仅带 X-KB-* 票据头，不带平台 Cookie)
          └─► 前置 HTTPS 反代 (Nginx / SLB，卸载 TLS 并覆写 X-Real-IP)
                └─► kb-gateway 0.1.0 (Linux amd64, nonroot UID 65532, :8087)
                      • 校验来源 CIDR、单 IP 限流、票据签名/有效期(±15s)、动作绑定
                      • 按正式库/灰度库白名单筛选 wiki_enabled 知识库并仅返回 published 页
                      • 写入 365 天独立 JSONL 审计卷（fail-closed）
                      └─► WeKnora v0.9.0 (容器内网 weknora-net 直连 http://weknora-app:8080)
```

### 1.2 严格上线顺序

必须按以下顺序依次交付，避免 CLI 先于服务端上线导致无法获取票据或连接失败：

1. **WeKnora 准备**：在 WeKnora 后台确认知识库已启用 Wiki、页面已发布，并签发最小权限只读 Scoped API Key。
2. **升级 `access-service`**：升级至 `1.1.2+`（沿用 MySQL 结构 15，从 `1.1.1` 升级无需结构迁移），在 `service.env` 中配置 `KB_TICKET_AK` 与 `KB_TICKET_SK` 并重启。
3. **部署 `kb-gateway` 与 HTTPS 反代**：构建镜像、授权日志目录给 UID `65532`、启动容器并配置前置 HTTPS 反向代理，完成健康检查与日志落盘验收。
4. **构建并分发 `cli-go`**：使用启用 `knowledge_base.enable: true` 且锁定真实 HTTPS 网关地址的配置文件打包 Windows x64 安装包（MSI / 便携 ZIP）并分发。

> [!IMPORTANT]
> `access-service` 与 `kb-gateway` 所在宿主机必须开启 **NTP 时钟同步**。网关验签执行严格时间窗 `now - 15 <= exp <= now + 315`（300 秒有效期 + `±15` 秒偏移宽限），时钟漂移过大会导致有效票据被拒（`401 INVALID_TICKET`）。

---

## 2. 前置配置：WeKnora 与 `access-service`

### 2.1 WeKnora `v0.9.0` 侧准备

1. **确认知识库状态**：
   - 目标共享知识库必须开启 Wiki 能力（上游接口返回 `indexing_strategy.wiki_enabled == true`），未启用的库会被网关自动过滤。
   - 待暴露的 Wiki 页面状态须为 `published`（草稿、未发布及已归档页不会被网关返回）。
   - 记录正式开放的知识库 ID（`kb_id`）及需内部调试的灰度库 ID（仅允许 `[A-Za-z0-9_-]+` 字符）。
2. **签发最小权限 Scoped API Key**：
   - 在 WeKnora 后台创建仅具 **`retrieve` 只读权限**、范围限定在所需共享库（含灰度调试库）内的 API Key，切勿使用全库管理员 Key。
3. **确认容器内网信息**：
   - 确认 WeKnora 后端容器所在网络（例如 `weknora-net`）以及容器内网访问地址（例如 `http://weknora-app:8080`）。

### 2.2 `access-service` 签票端配置

1. 生成高强度随机 `SK`（至少 32 字节，推荐 64 位十六进制）：

   ```bash
   openssl rand -hex 32
   ```

2. 编辑权限服务挂载的 `/opt/cli-access-config/service.env`（不要修改镜像内文件），追加以下两项（参考 [service.env.example](../../access-service/docker/service.env.example)）：

   ```dotenv
   # 共享 Wiki 短期票据签发配置（须与 kb-gateway 的 KB_TICKET_KEYS 保持一致）
   KB_TICKET_AK=kb-prod-v1
   KB_TICKET_SK=替换为至少32字节的随机密钥
   ```

   **配置约束（由 `access-service/app/settings.py` 启动强校验）**：
   - `KB_TICKET_AK` 与 `KB_TICKET_SK` 要么**同时留空**（关闭签票功能），要么**同时合法配置**；
   - `KB_TICKET_AK` 须匹配 `^[A-Za-z0-9_-]{1,64}$`；
   - `KB_TICKET_SK` 的 UTF-8 字节长度必须 `>= 32`；
   - 违反规则会在启动时抛出 `ValueError: 无效 KB 签票配置`。

3. 按权限服务部署指南使用 `1.1.2+` 镜像重启 `cli-access` 容器。

---

## 3. `kb-gateway` 环境变量配置详解

配置模板位于 [kb-gateway/kb-gateway.env.example](../../kb-gateway/kb-gateway.env.example)。以下是当前代码（`cmd/kb-gateway/main.go`、`internal/auth/ticket.go`、`internal/weknora/visibility.go`）支持的**全部 15 个环境变量**及校验规则：

| 环境变量 | 必填 | 默认值 | 格式与范围校验 | 说明 |
| --- | --- | --- | --- | --- |
| `KB_GATEWAY_LISTEN_ADDR` | 否 | `:8087` | Go `http.Server.Addr` | 网关容器内监听地址 |
| `WEKNORA_BASE_URL` | **是** | 无 | 须为 `http` 或 `https`，含主机名，**不得包含路径、末尾 `/`、用户信息、查询串或片段** | 上游 WeKnora 后端基地址，容器同网段建议填 `http://weknora-app:8080` |
| `WEKNORA_API_KEY` | **是** | 无 | 非空字符串 | WeKnora 最小权限 `retrieve` Scoped API Key |
| `WEKNORA_ALLOWED_KB_IDS` | 推荐必填 | 空 | 逗号分隔，每项匹配 `^[A-Za-z0-9_-]+$`；**禁止 `*`**，不得与自身或灰度库重复 | 对所有通过准入的员工可见的正式共享知识库 ID 列表 |
| `WEKNORA_PREVIEW_KB_IDS` | 否 | 空 | 同上，不得与 `WEKNORA_ALLOWED_KB_IDS` 有交集 | 仅对内部调试人员可见的灰度知识库 ID 列表；留空则关闭灰度 |
| `KB_PREVIEW_USERS` | 否 | 空 | 逗号分隔，严格为 **`环境:账号`**（如 `test:alice,prod:bob`），区分大小写，账号中不得含 `:` | 允许访问灰度库的调试身份名单；需与 `WEKNORA_PREVIEW_KB_IDS` 配合生效 |
| `KB_TICKET_KEYS` | **是** | 无 | 逗号分隔多组 `ak:sk`（如 `k1:sk1,k2:sk2`）；`ak` 匹配 `^[A-Za-z0-9_-]{1,64}$`、`sk` 长度 `>= 32`、不得重复 `ak` | 与 `access-service` 共享的验签密钥集，支持多组并存以实现平滑轮换 |
| `KB_GATEWAY_ALLOWED_CIDRS` | 否 | `127.0.0.0/8,::1/128` | 逗号分隔 CIDR 前缀 | 允许连接网关的直连来源网段（经反代接入时填反代 IP/网段）；未命中返回 `403 SOURCE_DENIED` |
| `KB_GATEWAY_TRUSTED_PROXY_CIDRS` | 否 | 空 | 逗号分隔 CIDR 前缀 | **仅填写会强制覆写 `X-Real-IP` 的可信反代网段**；留空时按 TCP 对端 IP 限流和审计，防止客户端伪造 `X-Real-IP` |
| `KB_GATEWAY_AUDIT_DIR` | 否 | `/var/log/kb-gateway` | 容器内可写目录路径 | 按北京时间自然日输出 `kb-audit-YYYY-MM-DD.jsonl` 的目录；不可写时请求返回 `503 AUDIT_UNAVAILABLE` |
| `KB_GATEWAY_TIMEOUT_SECONDS` | 否 | `10` | 整数 `1`–`60` | 单次请求上游 WeKnora 的超时秒数（服务端 `WriteTimeout` 自动设为 `2 * timeout + 5s`） |
| `KB_GATEWAY_MAX_UPSTREAM_BYTES` | 否 | `8388608`（8 MiB） | 整数 `1`–`67108864`（64 MiB） | 上游单次响应读取上限；超限返回 `502 UPSTREAM_RESPONSE_TOO_LARGE` |
| `KB_GATEWAY_MAX_PAGE_CONTENT_BYTES` | 否 | `65536`（64 KiB） | 整数 `1`–`1048576`（1 MiB） | 单篇 Wiki 页面正文的 UTF-8 安全边界预览上限；超长截断并置 `truncated: true` |
| `KB_GATEWAY_RATE_LIMIT_RPS` | 否 | `20` | 整数 `1`–`10000` | 单客户端 IP 令牌桶稳态速率（请求/秒） |
| `KB_GATEWAY_RATE_LIMIT_BURST` | 否 | `40` | 整数 `1`–`10000` | 单客户端 IP 令牌桶突发容量（内存最多追踪 4096 个活跃 IP 桶，每分钟清理过期桶） |

### 生产环境 `/opt/wiserec-kb-gateway/kb-gateway.env` 示例

```dotenv
KB_GATEWAY_LISTEN_ADDR=:8087

WEKNORA_BASE_URL=http://weknora-app:8080
WEKNORA_API_KEY=替换为WeKnora最小权限retrieve_API_Key

WEKNORA_ALLOWED_KB_IDS=kb_public_01
WEKNORA_PREVIEW_KB_IDS=
KB_PREVIEW_USERS=

KB_TICKET_KEYS=kb-prod-v1:替换为与access-service一致的32字节以上随机SK

# 若 Nginx 与网关在同一宿主机并通过 127.0.0.1:8087 转发：
KB_GATEWAY_ALLOWED_CIDRS=127.0.0.0/8,::1/128
KB_GATEWAY_TRUSTED_PROXY_CIDRS=127.0.0.1/32,::1/128

KB_GATEWAY_AUDIT_DIR=/var/log/kb-gateway

KB_GATEWAY_TIMEOUT_SECONDS=10
KB_GATEWAY_MAX_UPSTREAM_BYTES=8388608
KB_GATEWAY_MAX_PAGE_CONTENT_BYTES=65536
KB_GATEWAY_RATE_LIMIT_RPS=20
KB_GATEWAY_RATE_LIMIT_BURST=40
```

---

## 4. 镜像构建、Docker 部署与 HTTPS 反代

### 4.1 下载或构建 Linux `amd64` 镜像

打开 GitHub Actions 中的 [Build offline KB gateway image](https://github.com/mossexplore/platform-cli/actions/workflows/kb-gateway.yml)，选择目标提交的成功运行，从 Artifacts 下载离线包（保留 30 天）。如需重新构建，可在 main 上选择 Run workflow。解压下载的 ZIP，将其中的镜像归档、SHA256SUMS、配置模板及指南复制到主机同一目录，再执行：

```bash
sha256sum -c SHA256SUMS
docker load -i wiserec-kb-gateway-0.1.0-linux-amd64.tar.gz
docker run --rm wiserec-kb-gateway:0.1.0 --version
```

确认输出对应版本后继续 §4.2。使用离线包时，下文的 `kb-gateway/kb-gateway.env.example` 取自解压目录中的 `kb-gateway.env.example`。需要自行从源码构建时，使用以下方式。

`kb-gateway` 使用纯标准库 Go（无外部依赖、无 CGO），基于 `gcr.io/distroless/static:nonroot` 构建，镜像体积通常小于 20 MB。

```bash
cd kb-gateway
docker build --platform linux/amd64 -t wiserec-kb-gateway:0.1.0 .

# 验证镜像内二进制版本（应输出 0.1.0）
docker run --rm wiserec-kb-gateway:0.1.0 --version
```

如果生产宿主机无法访问外网镜像源，可在有网构建机导出后拷贝到生产机导入：

```bash
# 构建机导出
docker save wiserec-kb-gateway:0.1.0 | gzip > wiserec-kb-gateway-0.1.0-linux-amd64.tar.gz

# 生产机导入
gunzip -c wiserec-kb-gateway-0.1.0-linux-amd64.tar.gz | docker load
```

### 4.2 准备宿主机目录与非 root 审计权限

镜像以 `nonroot`（**UID `65532`、GID `65532`**）运行，且容器文件系统为 `--read-only`。宿主机日志目录**必须**将属主授予 `65532`，否则容器无法创建或追加当日 JSONL 文件，所有业务查询会因审计失败返回 `503 AUDIT_UNAVAILABLE`。

```bash
mkdir -p /opt/wiserec-kb-gateway/logs
cp kb-gateway/kb-gateway.env.example /opt/wiserec-kb-gateway/kb-gateway.env
chmod 600 /opt/wiserec-kb-gateway/kb-gateway.env

# 按实际部署值编辑配置文件
vi /opt/wiserec-kb-gateway/kb-gateway.env

# 关键：授予容器运行用户 UID 65532 写权限，并限制其他本地用户读取
chown 65532:65532 /opt/wiserec-kb-gateway/logs
chmod 750 /opt/wiserec-kb-gateway/logs
```

> [!TIP]
> 若宿主机有专门的运维只读组（如 `ops`），可将目录设为 `chown 65532:ops /opt/wiserec-kb-gateway/logs && chmod 750 /opt/wiserec-kb-gateway/logs`，以便运维组成员只读查看审计日志（文件默认创建权限 `0640`）。

### 4.3 启动 `kb-gateway` 容器（兼容 Docker `18.09.0`）

```bash
docker run -d \
  --name wiserec-kb-gateway \
  --network weknora-net \
  --restart unless-stopped \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --security-opt seccomp=unconfined \
  --env-file /opt/wiserec-kb-gateway/kb-gateway.env \
  -v /opt/wiserec-kb-gateway/logs:/var/log/kb-gateway \
  -p 8087:8087 \
  --log-driver json-file \
  --log-opt max-size=10m \
  --log-opt max-file=3 \
  wiserec-kb-gateway:0.1.0
```

参数要点说明：
- `--network weknora-net`：与 WeKnora 共享内网，直连 `http://weknora-app:8080`，不向公网暴露 WeKnora 端口；
- `-p 8087:8087`：发布宿主机 8087 端口供反代连接。在安全组或支持 Docker 转发流量过滤的防火墙中，仅允许反代来源访问此端口；
- `--security-opt seccomp=unconfined`：兼容 Linux 宿主机 Docker `18.09.0` 运行 Go 1.25 静态二进制。

### 4.4 前置 HTTPS 反向代理配置（Nginx 参考）

员工侧 CLI 强制要求 HTTPS 接入且拒绝任何 `3xx` 重定向。前置 Nginx / SLB 需注意四点：
1. 强制卸载 TLS 并对外提供有效 HTTPS 证书；
2. 强制覆盖 `X-Real-IP` 为 `$remote_addr`（与 `KB_GATEWAY_TRUSTED_PROXY_CIDRS` 配套），并在反代层增加员工 IP 限流；
3. 访问日志**不要记录原始查询串 `$args` 和 `X-KB-*` 请求头**（避免查询词与票据落入普通访问日志）；
4. 仅透传 `GET` 请求，且避免对 `/v1/kb/*` 产生 `301`/`302` 重定向。

```nginx
# 建议定义不含 $args 和请求头的精简日志格式
log_format kb_gw_safe '$remote_addr - [$time_local] "$request_method $uri" '
                      '$status $body_bytes_sent $request_time';

limit_req_zone $binary_remote_addr zone=kb_gw_ip:10m rate=20r/s;

server {
    listen 443 ssl http2;
    server_name kb-gateway.internal.example.com;

    ssl_certificate     /etc/nginx/certs/kb-gateway.fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/kb-gateway.key;
    ssl_protocols       TLSv1.2 TLSv1.3;

    access_log /var/log/nginx/kb-gateway-access.log kb_gw_safe;
    error_log  /var/log/nginx/kb-gateway-error.log warn;

    # 将示例地址 192.0.2.10 替换为网关宿主机的实际内网 IP（下方两处）。
    location = /health {
        proxy_pass http://192.0.2.10:8087/health;
    }

    location /v1/kb/ {
        limit_except GET {
            deny all;
        }
        limit_req zone=kb_gw_ip burst=40 nodelay;

        proxy_pass http://192.0.2.10:8087;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        # 强制覆写客户端真实 IP，防止伪造
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 30s;
        proxy_redirect off;
    }
}
```

> [!NOTE]
> **证书信任链提示**：根据 [cli-go/internal/platform/kb.go](../../cli-go/internal/platform/kb.go) 的实现，CLI 访问 `kb-gateway` 时与 `access-service` 共用 `access_control` 的 CA 配置（`ca_source`、`ca_file`、`use_env_proxy`）。若打包配置使用 `ca_source: "custom"`，请确保 `ca_file` 中的 PEM 证书合集同时包含两个 HTTPS 服务所需的根/中间证书链。

---

## 5. Go CLI 打包配置与客户端使用

### 5.1 打包期配置（锁定网关地址）

网关地址在编译打包期嵌入 `ml.exe`，运行期不允许本机文件改写。参考 [cli-go/config.example.json](../../cli-go/config.example.json) 准备正式打包配置：

```json
{
  "access_control": {
    "url": "https://permissions.internal.example.com/cli-permission",
    "timeout_seconds": 15,
    "use_env_proxy": false,
    "ca_source": "certifi",
    "enable": true
  },
  "knowledge_base": {
    "enable": true,
    "url": "https://kb-gateway.internal.example.com",
    "default_kb": "",
    "timeout_seconds": 15,
    "verify_ssl": true
  }
}
```

校验规则（由 `cli-go/internal/localstate/kb.go` 强制执行）：
- `enable: true` 时，`knowledge_base.url` 与 `access_control.url` 均须为合法 `https://` 地址，且不得包含用户名/密码、查询串或片段；
- `verify_ssl` 必须为 `true`（或省略，默认开启），设为 `false` 会直接校验失败；
- `timeout_seconds` 须在 `0`–`120` 之间（`0` 时默认 `15` 秒）。

使用同一份配置打包，Skill 文档（`references/kb.md` 及 `commands.md` 的共享 Wiki 段落）会自动跟随 `knowledge_base.enable` 装配或剔除：

```powershell
# Windows 构建便携 ZIP 与 MSI
./cli-go/scripts/build-release.ps1 -ConfigPath .\my-prod-config.json
```

### 5.2 本机可选覆盖（`kb.json`）

如需在单台员工电脑上指定个人默认库或临时关闭知识库命令，可编辑 `%APPDATA%\ml-go-preview\kb.json`：

```json
{
  "enable": true,
  "default_kb": "kb_public_01"
}
```

- 仅支持 `enable: false`（仅允许在已启用包上关闭，无法在未启用包上强行打开）与 `default_kb`；
- 即使写入 `url` 字段也会被客户端完全忽略，无法将票据重定向至其他主机；
- 若 `kb.json` 存在 JSON 语法错误，执行 `ml kb` 时会直接报配置解析错误，便于排查。

### 5.3 客户端使用前提与命令速查

**使用前提**：当前终端或 DSH 会话已绑定受支持环境、已完成 `ml login` 登录并选中业务，且账号权限、环境命令禁令及 CLI 版本均通过 `access-service` 校验。

| 命令 | 完整用法 | 说明 |
| --- | --- | --- |
| 列出可见库 | `ml kb list [-o table\|json]` | 首列 `知识库 ID` 固定 36 列不换行，含名称、更新时间（北京时间）、说明 |
| 浏览页面目录 | `ml kb page list [--kb NAME_OR_ID] [--page N] [--page-size N] [-o table\|json]` | 分页查看已发布页面目录；`--page` 从 `1` 起，`--page-size` 默认 `20`、上限 `50`；表格模式展示分页总数且 `Slug` 列不折行 |
| 关键词检索 | `ml kb search <QUERY> [--kb NAME_OR_ID] [--limit N] [-o table\|json]` | 按字面关键词检索已发布页（检索词 `1`–`512` 字符，自动转义正则标点）；`--limit` 默认 `5`、上限 `20`；若草稿占满超采候选窗口，`stderr` 提示缩小关键词并在 JSON 中返回 `candidate_window_exhausted: true` |
| 查看页面正文 | `ml kb page show <SLUG> [--kb NAME_OR_ID] [-o text\|json]` | 读取单篇已发布页预览（支持含 `/` 的 `slug` 如 `concept/rag`）；超过 `64 KiB` 按 UTF-8 安全边界截断并输出截断提示与来源 `source_refs` |

**`--kb NAME_OR_ID` 省略规则**：
- 若配置了 `default_kb`，未传 `--kb` 时优先使用默认库；
- 若未指定 `--kb` 且当前账号仅可见 **1 个**共享库，网关自动选中该库；
- 若可见 **多个**库（或传入的名称重名），网关返回 `400 AMBIGUOUS_KB_USE_ID` 并列出候选名称与 ID，按提示传入 `--kb <ID>` 即可。

---

## 6. 日常运维手册

### 6.1 管理员灰度库调试与一键开放

无需修改数据库、无需重启 `access-service`、无需重发 `ml.exe`，通过 `WEKNORA_PREVIEW_KB_IDS` + `KB_PREVIEW_USERS` 即可完成新知识库的内部调试与放行：

1. **开启灰度配置**：假设正式库为 `kb_public`，待调试新库为 `kb_preview`，调试账号为 `test` 环境的 `alice`。先在 WeKnora 发布待测页面，确认 Scoped API Key 已覆盖两个库，再编辑 `/opt/wiserec-kb-gateway/kb-gateway.env`：

   ```dotenv
   WEKNORA_ALLOWED_KB_IDS=kb_public
   WEKNORA_PREVIEW_KB_IDS=kb_preview
   KB_PREVIEW_USERS=test:alice
   ```

2. **使用更新后的 env 文件重建网关容器**（保留原日志卷与网络）：

   ```bash
   docker stop --time 30 wiserec-kb-gateway
   docker rm wiserec-kb-gateway
   # 再执行第 4.3 节的完整 docker run 命令启动新容器
   ```

3. **双身份验证**：
   - `test` 环境登录 `alice` 并选中业务后，直接用现有 `ml.exe` / DSH 执行调试：
     ```bash
     ml kb list
     ml kb search "训练超时" --kb kb_preview
     ml kb page show concept/rag --kb kb_preview
     ```
   - 用普通账号（或 `prod` 环境的 `alice`）验证：`ml kb list` 只看得到 `kb_public`，且省略 `--kb` 仍自动命中单正式库；显式传 `--kb kb_preview` 返回 `404 KB_NOT_FOUND`。

4. **调试通过一键开放（或回退）**：
   - 将 `kb_preview` 从 `WEKNORA_PREVIEW_KB_IDS` 移至 `WEKNORA_ALLOWED_KB_IDS`（逗号分隔：`kb_public,kb_preview`），重建网关容器；
   - 用普通账号复查同一条检索命令确认可见；若需回退，做相反变更并重建容器即可。

> [!WARNING]
> 首期票据中的 `username` 为客户端声明（服务端不校验平台 Cookie）。该灰度机制定位于**内网非涉密资料的防误见与调试隔离**；若待调试知识库包含**严格涉密内容**，请另起独立测试网关容器、独立 WeKnora Key 与管理员 IP 白名单，搭配独立测试包进行物理隔离调试。

### 6.2 票据密钥（`AK/SK`）零中断平滑轮换

`kb-gateway` 的 `KB_TICKET_KEYS` 支持同时配置多组密钥，按以下 4 步即可完成零中断轮换：

1. **网关侧先增新密钥**：在 `/opt/wiserec-kb-gateway/kb-gateway.env` 中追加新密钥并重建网关容器：
   ```dotenv
   KB_TICKET_KEYS=kb-prod-v1:旧SK,kb-prod-v2:新SK
   ```
2. **权限服务切换签发密钥**：修改 `/opt/cli-access-config/service.env` 中的 `KB_TICKET_AK=kb-prod-v2`、`KB_TICKET_SK=新SK` 并重启 `cli-access`。
3. **等待旧票据自然过期**：至少等待 **6 分钟**（覆盖 300 秒有效期 + 15 秒宽限）。
4. **网关侧清理旧密钥**：从 `KB_TICKET_KEYS` 中移除 `kb-prod-v1:旧SK` 并重建网关容器。

### 6.3 权限系统后台禁用命令

在权限管理台对应环境的「禁止命令」中按行填写完整命令路径即可管控：
- 禁用全部知识库命令：`ml kb`
- 单独禁用某一子命令：`ml kb list`、`ml kb page list`、`ml kb search`、`ml kb page show`

保存后立即阻止新签票（`COMMAND_DISABLED`）；因票据具备 300 秒有效期，已签发的有效票据最长在 300 秒内自然失效。

### 6.4 365 天审计日志关联与定时归档清理

1. **日志位置与格式**：`/opt/wiserec-kb-gateway/logs/kb-audit-YYYY-MM-DD.jsonl`（北京时间按日滚动，每行一条 JSON）。
   - 正常/上游错误请求记录：`timestamp`、`actor`、`env`、`ticket_id`、`action`、`kb_id`、`query`（脱敏限长）、`slug`（脱敏限长）、`status`、`duration_ms`、`hit_count`、`client_ip`、`candidate_window_exhausted`、`request_id`；
   - 拦截拒绝请求（`403 SOURCE_DENIED`、`401 INVALID_TICKET`、`403 ACTION_DENIED`）同样落盘；仅当验签通过（如 `403 ACTION_DENIED`）时才记录 `actor`、`env`、`ticket_id` 与 `ticket_action`。
2. **双端串联方式**：在权限管理系统调用记录详情页展开「查看追踪信息」复制「知识库票据 ID」，即可在网关 JSONL 中按 `ticket_id` 精确检索对应的 `0..N` 次数据查询：
   ```bash
   grep '"ticket_id":"<UUID>"' /opt/wiserec-kb-gateway/logs/kb-audit-2026-11-26.jsonl
   ```
3. **宿主机 365 天压缩与清理（参考 `cron`）**：每日凌晨压缩前一日及更早的 `.jsonl`，删除超过 365 天的 `.jsonl.gz` 归档（权限服务 MySQL `CallLog` 按同口径定期清理）：
   ```cron
   # /etc/cron.d/wiserec-kb-gateway-audit
   15 0 * * * root find /opt/wiserec-kb-gateway/logs -maxdepth 1 -name 'kb-audit-*.jsonl' -mtime +0 -exec gzip -q {} +
   30 0 * * * root find /opt/wiserec-kb-gateway/logs -maxdepth 1 -name 'kb-audit-*.jsonl.gz' -mtime +365 -delete
   ```

---

## 7. 部署验收与常见故障排查

### 7.1 部署验收清单

在生产/预发宿主机依次验证以下项目：

1. **健康检查**：
   ```bash
   curl -sS http://127.0.0.1:8087/health
   # 预期：{"status":"ok"}
   ```
2. **非 root 审计日志落盘验证（核心必测）**：
   ```bash
   # 故意不带票据访问，预期返回 HTTP 401 {"code":"INVALID_TICKET"}
   curl -i -sS http://127.0.0.1:8087/v1/kb/list

   # 核对宿主机已自动创建当天 JSONL 且写入了 INVALID_TICKET 记录
   ls -la /opt/wiserec-kb-gateway/logs/
   tail -n 3 /opt/wiserec-kb-gateway/logs/kb-audit-$(date +%F).jsonl
   ```
   > 若上一步返回 `503 AUDIT_UNAVAILABLE`，说明 `/opt/wiserec-kb-gateway/logs` 属主或权限不正确，请重新执行 `chown 65532:65532 /opt/wiserec-kb-gateway/logs && chmod 750 /opt/wiserec-kb-gateway/logs`。
3. **前置 HTTPS 与防重定向验证**：
   ```bash
   curl -i -sS https://kb-gateway.internal.example.com/health
   # 预期：HTTP/2 200（无 301/302 重定向、证书链有效）
   ```
4. **CLI 端到端功能验收**：
   - 已登录并选定业务后，依次执行 `ml kb list`、`ml kb page list`、`ml kb search "中文关键词"`、`ml kb page show <含/的slug>`；
   - 验证草稿页不泄露、搜索含正则标点（如 `[ERROR] (timeout)`）不报错、长正文超 64 KiB 正确截断并提示；
   - 验证灰度库配置下，调试账号与普通账号看到的结果隔离准确；
   - 在权限服务后台核对 `CallLog` 仅新增 1 条准入记录，且「知识库票据 ID」与网关 JSONL 的 `ticket_id` 一致。

### 7.2 常见错误码与排障对照

| 返回状态 / 错误信息 | 错误码 | 常见原因与排查方向 |
| --- | --- | --- |
| `HTTP 401` | `INVALID_TICKET` | 缺少票据头、`KB_TICKET_KEYS` 与 `access-service` 不一致、宿主机时钟偏差超 `±15` 秒或票据已超 300 秒过期 |
| `HTTP 403` | `ACTION_DENIED` | 有效票据携带的 `action` 与请求路径不匹配（如拿 `kb_list` 票据请求 `/v1/kb/page`） |
| `HTTP 403` | `SOURCE_DENIED` | 反代或直连来源 IP 未加入 `KB_GATEWAY_ALLOWED_CIDRS` |
| `HTTP 400` | `INVALID_CLIENT_IP` | 来自 `KB_GATEWAY_TRUSTED_PROXY_CIDRS` 的请求带有格式非法或多值 `X-Real-IP` |
| `HTTP 400` | `AMBIGUOUS_KB_USE_ID` | 未传 `--kb` 且可见多个库，或传入的名称存在重名；按提示改用 `--kb <ID>` |
| `HTTP 400` | `INVALID_PARAMETERS` | 分页越界、`limit` 超限（1–20）、检索词为空/超 512 字符、或 `slug` 含 `..`/`\`/`%`/空段/控制字符 |
| `HTTP 404` | `KB_NOT_FOUND` | 指定库不在当前账号可见白名单内，或上游该库未启用 `wiki_enabled` |
| `HTTP 404` | `NOT_FOUND` | 请求路径非法、页面不存在、或页面处于非 `published`（草稿/归档）状态 |
| `HTTP 405` | `METHOD_NOT_ALLOWED` | 使用了非 `GET` 方法（网关严格只读） |
| `HTTP 429` | `RATE_LIMITED` | 触发单 IP 令牌桶限流（检查 `KB_GATEWAY_TRUSTED_PROXY_CIDRS` 是否正确配置，避免所有员工共享反代单 IP 限流桶） |
| `HTTP 502` | `UPSTREAM_RESPONSE_TOO_LARGE` | WeKnora 单次响应超过 `KB_GATEWAY_MAX_UPSTREAM_BYTES`（默认 8 MiB），建议调小 `--page-size` 或缩小关键词范围 |
| `HTTP 502` | `UPSTREAM_FAILURE` | 网关无法连通 `WEKNORA_BASE_URL`、WeKnora 返回非 200/404 状态或非预期 JSON 结构；先检查容器网络 `weknora-net`、WeKnora Key 权限及上游真实响应格式 |
| `HTTP 503` | `BUSY` | 超过网关单实例最大并发上游槽位（16），稍后重试 |
| `HTTP 503` | `AUDIT_UNAVAILABLE` | 网关无法打开或写入 `KB_GATEWAY_AUDIT_DIR` 当日 JSONL 文件；检查宿主机日志卷权限（UID `65532`）与磁盘空间 |
| CLI 报错：权限服务未返回有效知识库票据 | — | `access-service` 尚未升级至 `1.1.2+`，或未在 `service.env` 中配置 `KB_TICKET_AK`/`KB_TICKET_SK` |
| CLI 报错：已拒绝重定向 | — | 打包配置的 `knowledge_base.url` 指向了发生 `3xx` 跳转的地址（如 HTTP 跳 HTTPS 或末尾路径重定向），请核对 URL 与 Nginx 配置 |
| CLI 报错：知识库 HTTPS 请求失败 | — | 检查网络连通性、反代证书有效性，以及 `access_control.ca_source` / `ca_file` 是否覆盖网关证书链 |
