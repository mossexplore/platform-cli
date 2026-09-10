# 权限管理系统 Docker 部署速查

适用：Linux x86_64、已有 MySQL，通过离线镜像部署。以下使用 `1.0.0` 镜像；升级时替换为新附件中的镜像文件名和标签。

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

从 [GitHub v1.0.0 正式版本](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.0) 下载 Docker 镜像、`SHA256SUMS`、`manifest.json` 和 `service.env.example`，复制到 Linux 同一目录。

在解压目录执行：

```bash
sha256sum --ignore-missing -c SHA256SUMS
docker load -i cli-access-1.0.0-linux-amd64.tar.gz
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

已有数据库结构版本为 7、数据和管理员正常时，直接进入下一步，无需初始化。

只有新数据库才执行：

```bash
docker run --rm -v /opt/cli-access-config:/run/cli-access:ro \
  cli-access:1.0.0 python -m app.manage migrate

docker run --rm -it -v /opt/cli-access-config:/run/cli-access:ro \
  cli-access:1.0.0 python -m app.manage create-admin
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
  cli-access:1.0.0
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

## 7. 升级与回滚

1. 下载新附件，校验并 docker load，记录旧镜像标签。
2. 备份数据库、配置及需要保留的日志。
3. 停止并删除旧应用容器：

```bash
docker stop --time 30 cli-access
docker rm cli-access
```

4. 重新执行第 4 节启动命令，末尾换成新镜像标签，继续挂载原配置目录。
5. 检查健康接口、管理员登录和一次实际业务调用。

删除应用容器不会删除外部 MySQL 数据。同数据库结构且配置兼容时，换回旧镜像标签重建即可回滚；涉及数据库结构升级时，需要单独评估迁移和恢复。

HTTPS、Compose 和 GitHub 构建流程见 [Docker 部署与发布指南](权限管理系统Docker部署与发布指南.md)。
