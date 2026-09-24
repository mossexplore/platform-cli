# 权限管理镜像：从 GitHub 下载后离线运行

本文件随离线附件生成时会替换下列占位符；仓库中的模板不能直接复制占位符运行。

- 版本：{{image_version}}
- 平台：linux/amd64（服务器 uname -m 应为 x86_64）
- 源镜像：{{image_reference}}
- 源代码提交：{{image_revision}}
- 导入后的镜像标签：{{image_tag}}
- 镜像配置 ID：{{image_id}}

镜像包含 Python、应用及依赖，不包含 MySQL 服务和生产配置。Linux 服务器仍需预先安装 Docker Engine，并能访问现有 MySQL 8.x。不需要 Compose，不需要访问 GHCR 或在线安装 Python。

## 1. 从 GitHub 下载

打开成功工作流运行页面，在 Artifacts 下载 `offline-image-运行编号`。需登录 GitHub 并具有仓库读取权限。浏览器下载通常为 ZIP，先解压，将其中全部文件复制到 Linux 服务器的同一目录。无需在服务器安装 unzip，可在电脑上先解压。

附件包含镜像 tar.gz、SHA256SUMS、manifest.json、service.env.example 和本指南。不要下载仓库的 Source code.zip 代替镜像。附件保留 30 天，过期后可运行 Export existing access image for offline Docker，填入上面的源镜像摘要重新导出，前提是 GHCR 中镜像仍保留。GitHub 附件下载会跳转到 GitHub 的附件存储域名，内网需允许该下载链路。

## 2. 校验和导入

在存放附件的目录执行：

```bash
sha256sum -c SHA256SUMS
docker load -i {{image_file}}
docker image inspect --format '{{.Id}}' {{image_tag}}
```

最后输出应与上方镜像配置 ID 一致。tar.gz 的 SHA256、镜像配置 ID 和 GHCR 索引摘要是不同对象，不能互相比较。这里必须使用 docker load，而不是 docker import；后者无法还原本镜像的完整配置。

离线归档用于运行，不保证携带所有 GHCR 附件。构建来源证明和 SBOM 保留在源镜像仓库；SHA256SUMS 用于检查下载/复制完整性，不替代来源证明。

## 3. 修改配置

以下复制命令仅用于首次配置；已有真实 service.env 时保留该文件，不要用示例覆盖。

```bash
sudo install -d -o root -g 10001 -m 750 /opt/cli-access-config
sudo install -o root -g 10001 -m 640 service.env.example /opt/cli-access-config/service.env
```

用 sudo 编辑 /opt/cli-access-config/service.env，将 DATABASE_URL 中的地址、数据库名、账号和密码改为实际值：

```dotenv
DATABASE_URL=mysql+pymysql://cli_access:URL_ENCODED_PASSWORD@mysql.internal:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
TLS_CERT_FILE=
TLS_KEY_FILE=
FORWARDED_ALLOW_IPS=
```

这是 HTTP 内网示例；通过 HTTPS Nginx 访问时 COOKIE_SECURE=true。密码中的 @、:、/ 等特殊字符要做 URL 百分号编码。docker --env-file 与 Compose 的解析规则不同，这份示例每行直接填写 KEY=value，不添加 shell 的 export 或包裹引号。

不要将 MySQL 地址设置为 127.0.0.1：容器里该地址指容器本身。MySQL 位于宿主机时填写容器可达的宿主机地址，确认监听、防火墙和 MySQL 账号来源权限。MySQL 数据库需要预先创建（utf8mb4，推荐 utf8mb4_bin），专用账号需要 SELECT、INSERT、UPDATE、DELETE、CREATE、ALTER、INDEX、REFERENCES 权限。

## 4. 初始化数据库与管理员

首次连接新数据库需要运行迁移，再交互创建管理员。已有数据库结构为版本 10 且管理员正常时，无需执行本节命令。1.0.3.1 → 1.0.3.2 结构仍为 10，不运行迁移；更早结构版本须先按历史升级指南停写、备份并迁移，不能直接启动新版。

```bash
docker run --rm -v /opt/cli-access-config:/run/cli-access:ro \
  {{image_tag}} python -m app.manage migrate

docker run --rm -it -v /opt/cli-access-config:/run/cli-access:ro \
  {{image_tag}} python -m app.manage create-admin
```

管理员密码交互输入（至少 12 字符），不写在命令行。默认启动命令不会自动迁移或创建管理员。1.0.3.2 的数据库结构为 10。

## 5. 使用 docker run 后台启动

可信内网直接 HTTP 访问示例（宿主机发布端口 8008）：

```bash
docker run -d \
  --name cli-access \
  --restart unless-stopped \
  -v /opt/cli-access-config:/run/cli-access:ro \
  -p 8008:8008 \
  --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m,mode=1777 \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --log-driver local \
  --log-opt max-size=10m \
  --log-opt max-file=5 \
  {{image_tag}}
```

`-p 8008:8008` 会绑定宿主机所有地址；需要限制到内网网卡时改为 `-p 实际内网IP:8008:8008` 并核实网络访问控制。宿主机 Nginx 代理时改为 `-p 127.0.0.1:8008:8008`，参考完整 Docker 指南设置可信代理来源。容器内保持 LISTEN_HOST=0.0.0.0、LISTEN_PORT=8008。

为兼容旧 Docker，此示例不使用 `--pull` 或 `--init`；运行前务必完成 docker load 并核对镜像标签。镜像使用非 root UID/GID 10001，因此配置目录和文件必须允许 GID 10001 读取。先确认旧 systemd/容器没有占用端口，生产切换前完成数据库备份。

```bash
docker ps --filter name=cli-access
docker inspect --format '{{.State.Health.Status}}' cli-access
curl -f http://127.0.0.1:8008/cli-permission/healthz
```

等待健康状态从 starting 变为 healthy。浏览器打开 `http://服务器IP:8008/cli-permission`。如发布到指定内网IP，则相应调整 curl 地址。

## 6. 日志、启停和修改配置

```bash
docker logs --tail=200 cli-access
docker logs -f --tail=200 cli-access
docker logs --since=1h --timestamps cli-access
docker stop --time 30 cli-access
docker start cli-access
docker restart cli-access
```

CLI 调用日志和操作审计在 MySQL/管理台；docker logs 查看服务进程输出。镜像默认不记录全部 HTTP 访问日志。unhealthy 本身不会触发自动重启，进程退出才由 restart 策略处理。

修改 `/opt/cli-access-config/service.env` 后执行 `docker restart cli-access` 即可重新读取。配置不会热加载；更改端口映射、挂载目录或镜像标签需要停止并删除旧容器，再重新执行 docker run。外部 MySQL 数据不受删除应用容器影响。

镜像自动读取 `/run/cli-access/service.env`，文件中的值优先于环境变量（包括镜像默认值）。不支持 `${VAR}` 变量插值，直接填写实际值。自定义路径可使用 `-e SERVICE_ENV_FILE=/其他容器路径/service.env`；显式指定的文件缺失或不可读会报错。默认文件不存在时兼容原 `--env-file` 用法，但原方式修改后仍需要重建容器。

只读挂载不把数据库密码写入 Docker 的 Config.Env，但宿主机 root、Docker 管理员和容器服务进程仍可读取配置；它不是加密。不要将真实配置提交到 GitHub 或打包到镜像。若宿主机启用 SELinux，需要按本机策略为挂载目录设置容器可读标签。

重置管理员密码：

```bash
docker run --rm -it -v /opt/cli-access-config:/run/cli-access:ro \
  {{image_tag}} python -m app.manage reset-password
```

## 7. 升级和回滚

1.0.3.1 → 1.0.3.2：下载新附件并校验 → docker load → 在独立库演练备份恢复及新镜像验收 → 停止旧应用和写入 → 完成最终数据库与配置备份 → 保留旧容器并以新标签启动 → 验证健康、登录、授权、日志和有数据的数据看板。结构仍为 10，**不运行 migrate**。详细分步操作见 `Docker-upgrade-1.0.3.2.md`。

保留旧镜像标签和对应配置便于回滚。1.0.3.1 → 1.0.3.2 没有结构迁移，可将旧镜像连接原结构 10 数据库并验收；若数据受损需恢复最终备份，应先评估备份后新增日志、审计和配置变更的损失。更早的 1.0.3 → 1.0.3.1 曾涉及结构 8 → 10，不能把该路径的旧镜像直接连接结构 10 库，也不能手改结构版本。最终备份应在停止全部写入后完成。不要清理仍用于生产或回滚的镜像。
