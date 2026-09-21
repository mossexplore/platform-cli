# 权限管理系统 Docker 部署速查

适用：Linux x86_64、已有 MySQL，通过离线镜像部署。以下使用 `1.0.3` 镜像；升级时替换为新附件中的镜像文件名和标签。

## 1. 检查 Docker

```bash
docker version
```

能看到 Client 和 Server 即可继续。未安装时，由运维人员按 [Docker 官方安装说明](https://docs.docker.com/engine/install/) 安装对应 Linux 版本；内网服务器需提前准备安装包和依赖。

已安装但服务未启动：

```bash
sudo systemctl enable --now docker
```

以下 docker 命令需要管理权限，权限不足时在前面加 sudo。

## 2. 下载并导入镜像

从 [GitHub v1.0.3 正式版本](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.3) 下载 Docker 镜像、`SHA256SUMS`、`manifest.json` 和 `service.env.example`，复制到 Linux 同一目录。

在解压目录执行：

```bash
sha256sum --ignore-missing -c SHA256SUMS
docker load -i cli-access-1.0.3-linux-amd64.tar.gz
```

SHA256SUMS 包含全部发布附件。只下载 Docker 文件时使用 `sha256sum --ignore-missing -c SHA256SUMS`，已下载文件应显示 OK。Release 附件不采用 Actions 的 30 天保留期。

## 3. 准备配置

首次部署执行以下命令；已有配置时不要用示例覆盖：

```bash
sudo install -d -o root -g 10001 -m 750 /opt/cli-access-config
sudo install -o root -g 10001 -m 640 service.env.example /opt/cli-access-config/service.env
sudo vi /opt/cli-access-config/service.env
```

内网 HTTP 部署填写：

```dotenv
DATABASE_URL=mysql+pymysql://账号:密码@数据库地址:3306/数据库名?charset=utf8mb4
COOKIE_SECURE=false
LISTEN_HOST=0.0.0.0
LISTEN_PORT=8008
TLS_CERT_FILE=
TLS_KEY_FILE=
FORWARDED_ALLOW_IPS=
```

- 数据库地址填写容器能访问的实际地址，不填 `127.0.0.1`。
- 密码含 `@`、`:`、`/`、`%` 等特殊字符时，需要 URL 百分号编码。
- 不把真实配置上传 GitHub；文件挂载不等于加密，Docker 管理员仍可读取。

本版要求数据库结构版本 8。仅当现有结构已为 8、数据和管理员正常时可跳过迁移。1.0.0 的结构版本 7 必须先备份、停写，再用新镜像迁移，不能直接启动新版。

只有新数据库才执行：

```bash
docker run --rm -v /opt/cli-access-config:/run/cli-access:ro \
  cli-access:1.0.3 python -m app.manage migrate

docker run --rm -it -v /opt/cli-access-config:/run/cli-access:ro \
  cli-access:1.0.3 python -m app.manage create-admin
```

管理员密码按提示输入，至少 12 个字符。旧数据库需要升级结构时，先备份再迁移。

## 4. 后台启动

确认没有同名旧容器，且端口 8008 未被占用后执行：

```bash
docker run -d \
  --name cli-access \
  --restart unless-stopped \
  -v /opt/cli-access-config:/run/cli-access:ro \
  -p 8008:8008 \
  --read-only \
  --tmpfs /tmp:size=64m,mode=1777 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=5 \
  cli-access:1.0.3
```

服务自动读取挂载配置，镜像名后面不用追加命令。这里不使用旧 Docker 不支持的 `--pull` 和缺少 docker-init 时无法使用的 `--init`。

`-p 8008:8008` 对宿主机所有网卡发布端口，请确保访问范围符合内网要求。

检查启动结果：

```bash
docker ps --filter name=cli-access
curl --max-time 5 http://127.0.0.1:8008/cli-permission/healthz
```

返回 `{"status":"ok"}` 后，浏览器打开 `http://服务器IP:8008/cli-permission`，登录并检查业务是否正常。

## 5. 日常操作

| 操作 | 命令 |
| --- | --- |
| 停止 | `docker stop --time 30 cli-access` |
| 启动已有容器 | `docker start cli-access` |
| 重启 | `docker restart cli-access` |
| 查看状态，包括已停止容器 | `docker ps -a --filter name=cli-access` |
| 查看最近 200 行日志 | `docker logs --tail=200 cli-access` |
| 实时跟踪日志 | `docker logs -f --tail=200 cli-access` |
| 查看最近一小时日志 | `docker logs --since=1h --timestamps cli-access` |
| 导出日志 | `docker logs --timestamps cli-access > cli-access.log 2>&1` |

实时日志按 Ctrl+C 退出，不会停止服务。导出时避免覆盖已有日志，分享前脱敏。

**修改配置：** 编辑 `/opt/cli-access-config/service.env`，然后执行 `docker restart cli-access`。改端口映射或镜像则需要重建容器。

**日志位置：** 启动和异常看 docker logs；CLI 调用及操作审计看管理台。应用默认不记录每个 HTTP 请求。容器日志会自动轮转，删除容器前按需导出。

## 6. 启动异常时查这里

先看状态和日志：

```bash
docker ps -a --filter name=cli-access
docker logs --tail=200 cli-access
docker inspect --format '{{json .State.Health}}' cli-access
```

| 问题 | 处理 |
| --- | --- |
| `unknown flag: --pull` | 去掉 --pull，使用第 4 节命令 |
| 找不到 `docker-init` | 去掉 --init，使用第 4 节命令 |
| 容器名已存在 | 已有容器用 start；升级按第 7 节重建 |
| 端口已占用 | 检查旧服务；或把 `-p 8008:8008` 改为 `-p 8009:8008`，访问时用 8009 |
| 配置文件不可读 | 按下面命令修正权限；仍失败则请运维检查 SELinux/用户映射 |
| 数据库连接失败 | 检查地址、账号、密码编码及 MySQL 网络和来源授权 |
| `schema_not_ready` | 核对连接的数据库，先备份再执行目标版本迁移 |
| running 但 unhealthy | 进程在运行不代表数据库正常；结合日志和健康接口排查，不要只反复重启 |
| 本机能访问，其他机器不能 | 检查服务器 IP、端口映射、防火墙和网络策略 |

配置权限修复：

```bash
sudo chown root:10001 /opt/cli-access-config /opt/cli-access-config/service.env
sudo chmod 750 /opt/cli-access-config
sudo chmod 640 /opt/cli-access-config/service.env
```

## 7. 从 1.0.0 升级到 1.0.3

本次数据库结构从 7 升至 8，必须执行迁移。完整备份、演练、核验和回滚见仓库的《权限管理系统1.0.0升级至1.0.3指南.md》；正式附件对应 Docker-upgrade-1.0.3.md。

1. 校验、导入新镜像，保留旧镜像和原配置；先在生产备份恢复出的隔离测试库演练。
2. 进入维护窗口，停止全部旧应用和其他写入来源，完成最终数据库备份并核实恢复能力。
3. 挂载原配置，运行新镜像迁移；成功退出后确认 schema_versions 只有一条记录且为 8：

```bash
docker stop --time 30 cli-access
```

完成最终数据库备份和配置备份、确认恢复方案后，才执行：

```bash
docker run --rm -v /opt/cli-access-config:/run/cli-access:ro \
  cli-access:1.0.3 python -m app.manage migrate
```

迁移容器需沿用实际数据库网络配置；仅允许单个迁移进程。失败时保持服务停止，先排查，不手工修改结构版本。

4. 迁移成功后保留已停止的旧容器：

```bash
docker rename cli-access cli-access-1.0.0-backup
```

若备份名称已存在，先确认归属并改用唯一名称，不删除未知容器。旧容器必须一直保持停止。

5. 重新执行第 4 节，以 cli-access:1.0.3 启动；不覆盖原 service.env，不执行 create-admin。
6. 核验旧数据、健康接口、原管理员登录和授权通过/拒绝，确认新日志可写后恢复业务访问。先观察版本分布，再单独启用强制限制。

迁移仅新增版本策略/例外表和日志字段，不清空业务数据。历史日志版本补为 1.0.0，来源 historical_default；升级后旧客户端未上报版本的新请求来源为 legacy_default。

**回滚：** 旧版健康检查要求结构 7，因此迁移后不能只换回 1.0.0 镜像。先停新服务、保留故障库，将升级前备份恢复至独立回滚库，再使用旧镜像和指向回滚库的独立配置启动。恢复旧备份会缺失备份后的写入，业务放行后的回滚必须先处理这段增量。禁止手工将版本号改回 7 冒充回滚。

HTTPS、Compose 和 GitHub 构建流程见 [Docker 部署与发布指南](权限管理系统Docker部署与发布指南.md)。
