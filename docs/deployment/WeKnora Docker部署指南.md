# WeKnora v0.9.0 宿主机 `docker run` 完整部署指南

本文档记录在 **无 `docker compose`**（兼容老版本 Docker `18.09.0` 及以上）的 **Linux `amd64`** 宿主机上，使用纯 `docker run` 部署 **WeKnora `v0.9.0`** 的完整步骤。端口规划已默认避开同机常见的 `80` / `3000` / `5432` / `6379` 冲突。

---

## 1. 环境与端口规划

- **宿主机架构**：Linux `amd64`
- **Docker 版本**：兼容 Docker `18.09.0` 及以上，无需安装 `docker compose`
- **端口规划（宿主机 → 容器）**：

| 服务 | 容器名 | 网络别名 | 宿主机端口 → 容器端口 | 说明 |
| --- | --- | --- | --- | --- |
| 前端 Web UI | `weknora-ui` | - | `8090 → 80` | 浏览器访问入口（Nginx 静态资源 + API 反向代理） |
| Go 主后端 | `weknora-app` | `app` | `8089 → 8080` | 后端 REST API / 检索 / MCP 服务 |
| 文档解析 | `weknora-docreader` | `docreader` | 仅内网 `50051` | gRPC 文档解析微服务，不暴露宿主机 |
| 数据库 | `weknora-postgres` | `postgres` | 仅内网 `5432` | ParadeDB（PG17 + pgvector + BM25），不暴露宿主机 |
| 缓存队列 | `weknora-redis` | `redis` | 仅内网 `6379` | Redis 7，不暴露宿主机 |

---

## 2. 准备 5 个镜像

在宿主机拉取（或通过 `docker load` 离线导入）以下 5 个镜像：

```bash
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-app:v0.9.0
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-ui:v0.9.0
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-docreader:v0.9.0
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/paradedb/paradedb:v0.25.11-pg17
docker pull swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/redis:7-alpine

# 核对 5 个镜像均已就位
docker images | grep -E "weknora|paradedb|redis"
```

---

## 3. 创建目录、准备配置并修正权限

1. **创建宿主机配置目录**：
   ```bash
   mkdir -p /opt/weknora/config
   ```
2. **上传 `config.yaml`**：
   从官方仓库 `v0.9.0`（https://github.com/Tencent/WeKnora/tree/v0.9.0）获取 `config/config.yaml`，上传至 `/opt/weknora/config/config.yaml`。
3. **核对文件类型并设置可读权限**（避免容器内非 root 进程读取时报 `permission denied`）：
   ```bash
   # 确认输出第一列以 "-" 开头（普通文件），而非 "d"（目录）
   ls -ld /opt/weknora /opt/weknora/config /opt/weknora/config/config.yaml

   chmod 755 /opt/weknora /opt/weknora/config
   chmod 644 /opt/weknora/config/config.yaml
   ```
4. **检查 SELinux 状态**：
   ```bash
   getenforce 2>/dev/null || true
   ```
   - 若返回 `Disabled` 或 `Permissive`：按第 5 节直接挂载即可；
   - 若返回 `Enforcing`：在第 5 节启动 `weknora-app` 时，将配置文件挂载参数改为 `-v /opt/weknora/config/config.yaml:/app/config/config.yaml:Z`。

---

## 4. 创建专属网络、持久化卷与密码变量

```bash
# 创建容器互通网络与持久化卷
docker network create weknora-net
docker volume create weknora-pg-data
docker volume create weknora-redis-data
docker volume create weknora-files
docker volume create weknora-docreader-tmp

# 设置数据库与 Redis 密码（请替换为实际强密码并妥善保存）
export WK_DB_PASS='ChangeMe_Pg_2026'
export WK_REDIS_PASS='ChangeMe_Redis_2026'
```

---

## 5. 按依赖顺序拉起 5 个容器

> 说明：以下命令均附加 `--security-opt seccomp=unconfined`，用于解决老版本 Docker `18.09.0` 默认 seccomp 规则拦截新版容器系统调用的问题。

### 5.1 启动 PostgreSQL（ParadeDB）并等待就绪

```bash
docker run -d \
  --name weknora-postgres \
  --network weknora-net \
  --network-alias postgres \
  --restart unless-stopped \
  --security-opt seccomp=unconfined \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD="$WK_DB_PASS" \
  -e POSTGRES_DB=WeKnora \
  -v weknora-pg-data:/var/lib/postgresql/data \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/paradedb/paradedb:v0.25.11-pg17

# 确认数据库就绪（直到输出 accepting connections 再执行下一步）
docker exec weknora-postgres pg_isready -U postgres -d WeKnora
```

### 5.2 启动 Redis

```bash
docker run -d \
  --name weknora-redis \
  --network weknora-net \
  --network-alias redis \
  --restart unless-stopped \
  --security-opt seccomp=unconfined \
  -v weknora-redis-data:/data \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/redis:7-alpine \
  redis-server --appendonly yes --requirepass "$WK_REDIS_PASS"
```

### 5.3 启动文档解析服务（Docreader）

```bash
docker run -d \
  --name weknora-docreader \
  --network weknora-net \
  --network-alias docreader \
  --restart unless-stopped \
  --security-opt seccomp=unconfined \
  -e OCR_BACKEND=no_ocr \
  -v weknora-docreader-tmp:/tmp/docreader \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-docreader:v0.9.0
```

> 若服务器具备 OCR 模型或联网条件且需要 OCR，去掉 `-e OCR_BACKEND=no_ocr` 即可。

### 5.4 启动 Go 主后端服务（App）

```bash
docker run -d \
  --name weknora-app \
  --network weknora-net \
  --network-alias app \
  --restart unless-stopped \
  --security-opt seccomp=unconfined \
  -p 8089:8080 \
  -e GIN_MODE=release \
  -e DB_DRIVER=postgres \
  -e DB_HOST=postgres \
  -e DB_PORT=5432 \
  -e DB_USER=postgres \
  -e DB_PASSWORD="$WK_DB_PASS" \
  -e DB_NAME=WeKnora \
  -e RETRIEVE_DRIVER=postgres \
  -e REDIS_ADDRESS=redis:6379 \
  -e REDIS_PASSWORD="$WK_REDIS_PASS" \
  -e DOCREADER_ADDR=docreader:50051 \
  -e SSRF_WHITELIST_EXTRA="10.0.0.0/8" \
  -v weknora-files:/data/files \
  -v weknora-docreader-tmp:/tmp/docreader:ro \
  -v /opt/weknora/config/config.yaml:/app/config/config.yaml \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-app:v0.9.0
```

### 5.5 启动前端 Web UI（Nginx）

```bash
docker run -d \
  --name weknora-ui \
  --network weknora-net \
  --restart unless-stopped \
  --security-opt seccomp=unconfined \
  -p 8090:80 \
  -e APP_SCHEME=http \
  -e APP_HOST=app \
  -e APP_PORT=8080 \
  -e APP_BACKEND_PORT=8080 \
  swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/wechatopenai/weknora-ui:v0.9.0
```

---

## 6. 验收与初始化

1. **检查 5 个容器状态与日志**：
   ```bash
   docker ps --filter "name=weknora-" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
   docker logs --tail=50 weknora-app
   docker logs --tail=30 weknora-docreader
   ```
   确认 5 个容器均为 `Up` 且无报错。

2. **访问前端页面**（注意使用前端端口 **`8090`**，不要访问后端端口 `8089`）：
   ```text
   http://<宿主机IP>:8090
   ```
3. 按页面引导注册/创建首个管理员账号，并在后台「模型设置」中配置内网可用的 **LLM**、**Embedding**（以及可选 **Rerank**）模型，随后新建知识库并上传测试文档完成检索验证。

---

## 7. 日常运维命令

```bash
# 停止全部容器（不删除数据）
docker stop weknora-ui weknora-app weknora-docreader weknora-redis weknora-postgres

# 按顺序重新启动全部容器
docker start weknora-postgres weknora-redis weknora-docreader weknora-app weknora-ui

# 修改 config.yaml 后重启后端生效
docker restart weknora-app

# 仅删除容器（保留数据卷，用于修改启动参数后重建）
docker rm -f weknora-ui weknora-app weknora-docreader weknora-redis weknora-postgres

# 备份 PostgreSQL 数据库
docker exec weknora-postgres pg_dump -U postgres WeKnora > /opt/weknora/weknora_backup_$(date +%F).sql
```

---

## 8. 常见问题速查

| 现象 | 原因 | 解决方法 |
| --- | --- | --- |
| `open /app/config/config.yaml: permission denied` | 宿主机文件权限过严、挂载为 `:ro`、Docker `18.09.0` seccomp 拦截或文件被 Docker 误建为空目录 | 确认 `ls -ld` 开头为 `-`；执行 `chmod 755 /opt/weknora /opt/weknora/config && chmod 644 /opt/weknora/config/config.yaml`；去掉 `:ro` 并保留 `--security-opt seccomp=unconfined`（开启 SELinux 时加 `:Z`） |
| 浏览器访问报 `{"error":"Unauthorized: missing authentication"}` | 访问到了后端端口 `8089` | 改访问前端端口 `http://<宿主机IP>:8090` |
| 页面能打开但登录/接口返回 `502` | `weknora-ui` 缺少后端端口变量或 `weknora-app` 尚未就绪 | 确认 `weknora-app` 状态为 `Up`，并确认 `weknora-ui` 启动时同时传了 `APP_PORT=8080` 与 `APP_BACKEND_PORT=8080` |
| 离线环境 `docreader` 启动拉模型超时 | 默认尝试联网下载 OCR 模型 | 启动 `weknora-docreader` 时保留 `-e OCR_BACKEND=no_ocr` |
| 添加模型报 `SSRF validation failed: direct IP address access is not allowed` | 默认禁止模型 Base URL 直接填内网 IP | 在 `weknora-app` 中加入 `-e SSRF_WHITELIST_EXTRA="10.0.0.0/8"`（支持精确域名、`.example.com`、IP 或 CIDR）并重建容器 |
