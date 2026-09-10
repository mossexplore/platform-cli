# 权限管理系统 Docker 部署与 GitHub 镜像发布

适用项目版本：0.3.41；数据库结构版本：7。Docker 仅部署 access-service，终端 ml 客户端仍按原方式安装。

## 1. 架构与前提

GitHub 托管 Ubuntu 构建镜像，GHCR 保存镜像，Linux 服务器通过 Docker Compose 运行应用，复用现有 MySQL 8.x。运行时无需公网、系统 Python、Node.js 或独立前端构建；首次拉取镜像需能访问 GHCR，离线环境可导入镜像。Linux 服务器需安装受其发行版支持的 Docker Engine 和 Compose v2（支持 `up --wait`），当前镜像只验证 linux/amd64。容器使用自己的用户态库，不沿用旧离线包的宿主机 glibc 检查，但不能由此推断老内核或所有发行版都受支持。

镜像内置 Python 和依赖，进程使用 UID/GID 10001，根文件系统只读，/tmp 使用临时内存文件系统。人员、授权、管理员会话和审计均在外部 MySQL。容器删除不会删除外部数据库；容器运行日志则由 Docker 管理，重建前按需导出。

## 2. GitHub 自动制作镜像

工作流：`.github/workflows/access-image.yml`，名称 **Build and publish access image**。

- 推送 main 且涉及服务、CLI、测试、项目版本或工作流时运行；纯 docs 修改不触发。
- Pull Request 运行测试和本地候选镜像验证，不登录、不发布 GHCR。
- Actions → 对应工作流 → Run workflow → 选择 main，可手动构建。
- 在 main 上已存在的提交创建 `v<项目版本>` 标签并发布 GitHub Release，生成正式版本镜像。标签必须与 pyproject.toml 和 CLI 版本一致；现有版本标签不覆盖。不要为了发布镜像推送其他代码分支。

流程：版本校验 → CLI/服务/时区测试 → Buildx 构建候选镜像 → 按摘要拉取 → 临时 MySQL 8.4 迁移两次 → 健康检查、静态资源、管理员登录、授权允许/拒绝、日志和重启检查 → 来源证明 → 提升标签。测试使用临时数据和测试专用密码，不访问业务平台或生产 MySQL。

发布使用短期 GITHUB_TOKEN，工作流只授予 contents:read、packages:write、attestations:write、id-token:write；无需向仓库上传个人 Docker 密码。官方 Actions 固定提交 SHA，基础 Python 镜像固定摘要，依赖固定版本。BuildKit 使用 GitHub 缓存复用依赖层；发布镜像附带 SBOM 和 provenance，GitHub attestation 关联已测试摘要。

镜像名：`ghcr.io/mossexplore/cli-access`（fork 后使用 fork 所有者的小写名称）。标签：

| 标签 | 含义 |
| --- | --- |
| candidate-运行ID-尝试次数 | 构建候选，可能测试失败，不用于部署 |
| sha-完整提交SHA | 测试通过的提交构建；同提交重新构建可能更新该标签 |
| main | main 最近一次通过的构建，便于体验，不推荐固定生产版本时使用 |
| 0.3.41 等版本 | GitHub Release 通过后发布，不覆盖已有版本 |
| @sha256:… | 精确不可变镜像摘要，生产首选 |

候选先推送，是为了保留 SBOM/provenance 并测试最终分发的同一份镜像；验证后用 imagetools 添加标签，不重新构建。失败候选不会更新 main 或版本标签。不同事件的构建可能并行，main 标签按构建完成顺序更新，生产应固定摘要。保留生产和回滚版本；候选缓存清理需避免删除仍被部署摘要引用的镜像。

公开仓库可用标准 GitHub 托管 runner 免费额度政策；GHCR 包首次创建通常为 private。若希望匿名拉取，在包设置中明确调整可见性，流水线不自动公开包。私有包登录时使用只具 read:packages 的凭据，凭据经标准输入传入 docker login，不写入代码或示例配置。组织如有 SSO/Packages 策略，还需管理员授权。

Actions 成功后的 Summary 提供完整镜像摘要。可使用 `gh attestation verify oci://ghcr.io/mossexplore/cli-access@sha256:实际摘要 -R mossexplore/platform-cli` 验证来源。GitHub attestation 的可用性受仓库可见性和套餐限制；本仓库为公开仓库。

## 3. 初次部署

在服务器建立独立部署目录，例如 `/opt/cli-access-docker`，复制：

- `access-service/compose.yaml` → 部署目录 `compose.yaml`
- `access-service/docker/compose.env.example` → 部署目录 `.env`
- `access-service/docker/service.env.example` → 部署目录 `docker/service.env`

以下命令均在部署目录执行。修改 .env：

```dotenv
CLI_ACCESS_IMAGE=ghcr.io/mossexplore/cli-access@sha256:从成功流水线复制的实际摘要
BIND_IP=127.0.0.1
HTTP_PORT=8008
```

摘要行是占位说明，必须替换。镜像首次尚未发布时不能执行拉取。要直接通过内网 IP 访问，把 BIND_IP 改为宿主机实际内网地址；使用宿主机 Nginx 时保留 127.0.0.1。

修改 docker/service.env：

```dotenv
DATABASE_URL=mysql+pymysql://cli_access:URL_ENCODED_PASSWORD@mysql.internal:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
TLS_CERT_FILE=
TLS_KEY_FILE=
FORWARDED_ALLOW_IPS=
```

数据库需预先创建，字符集 utf8mb4，推荐 utf8mb4_bin；权限要求见原 Linux 手册。URL 密码中的 @、:、/、$ 等特殊字符应百分号编码，避免 URL 解析和 Compose 插值问题。数据库地址不能填容器自身 127.0.0.1；MySQL 位于宿主机时使用容器可达的宿主机地址，确保数据库监听、防火墙及 MySQL 账号来源授权正确。不要把生产密码放入 shell 命令历史或截图。

```bash
chmod 600 .env docker/service.env
docker compose config --quiet
docker compose pull cli-access
docker compose run --rm cli-access python -m app.manage migrate
docker compose run --rm cli-access python -m app.manage create-admin
docker compose up -d --wait --wait-timeout 120 cli-access
docker compose ps
curl -f http://127.0.0.1:8008/cli-permission/healthz
```

最后检查地址应与 BIND_IP/HTTP_PORT 相匹配。已有管理员则跳过 create-admin；密码交互输入，至少 12 字符。启动不自动迁移、不交互创建管理员。浏览器打开 `http://服务器地址:端口/cli-permission`。只打印 `docker compose config --quiet`，完整 config 输出可能暴露密码。

## 4. HTTPS 和代理

推荐由已有宿主机 Nginx 提供 HTTPS，映射保持 127.0.0.1:8008，容器内部始终监听 0.0.0.0:8008。COOKIE_SECURE=true，两个 TLS 路径留空。按 `access-service/nginx.conf.example` 保留 /cli-permission 前缀，proxy_pass 不加尾斜杠。不要直接复制旧指南中的容器内 LISTEN_HOST=127.0.0.1。

Docker 网桥可能使容器看到的代理来源不再是 127.0.0.1。FORWARDED_ALLOW_IPS 默认空，忽略代理头；确认实际代理连接来源后，填具体 IP 或受控网段，禁止不加限制使用 `*`。宿主机端口只开放给该代理。代理正确传入并覆盖 X-Forwarded-For 和 X-Forwarded-Proto 后，日志来源 IP 和 HTTPS 重定向才能正确识别。Nginx 容器部署需共享受控网络并转发到 cli-access:8008，而不是 Nginx 自己的 127.0.0.1。

现有服务也支持直接 TLS，但需自行增加证书只读挂载，确保 UID 10001 可读，并将 HEALTHCHECK_URL 设置为容器可访问、与证书主机名匹配的 HTTPS 地址；企业 CA 用 SSL_CERT_FILE 配置信任，健康检查不关闭证书验证。建议第一版使用 Nginx 终止 TLS。

容器时区不影响业务时间：数据库 UTC，页面和快捷筛选按 UTC+8。无需挂载宿主机 /etc/localtime。

## 5. 配置、启停、日志

| 操作 | 命令 |
| --- | --- |
| 启动/更新 | `docker compose up -d --wait cli-access` |
| 停止 | `docker compose stop cli-access` |
| 启动已停止容器 | `docker compose start cli-access` |
| 普通重启 | `docker compose restart cli-access` |
| 修改环境配置后重建 | `docker compose up -d --force-recreate --wait cli-access` |
| 状态 | `docker compose ps` |
| 最近日志 | `docker compose logs --tail=200 cli-access` |
| 实时日志 | `docker compose logs -f --tail=200 cli-access` |
| 一小时日志 | `docker compose logs --since=1h --timestamps cli-access` |
| 导出当前运行日志 | `docker compose logs --no-color cli-access > cli-access.log` |
| 重置管理员密码 | `docker compose run --rm cli-access python -m app.manage reset-password` |

修改代码需要新镜像；修改 service.env、镜像、端口需要重建容器，普通 restart 不重读环境变量。环境变量只在运行时注入，不进入镜像。对 Docker 管理员可见，不构成专门的秘密存储；当前不支持 DATABASE_URL_FILE，不能仅设置该字段代替连接配置。

Docker `local` 日志驱动单文件 10MB，最多 5 个文件，自动轮转。启动/异常输出看容器日志；CLI 调用和管理员审计保存在 MySQL 管理台。Uvicorn 访问日志默认关闭，部分数据库错误仅返回通用错误，不保证在容器日志中有完整堆栈。HTTP 访问日志由 Nginx 记录，保留示例中对包含查询凭证的回执路径排除规则。

restart:unless-stopped 在进程退出后恢复，Docker 服务需开机启动。healthcheck 检查 HTTP、数据库和结构版本；unhealthy 本身不会触发 Docker 自动重启，应告警并排查数据库，避免用重启循环掩盖故障。健康检查默认访问容器内 http://127.0.0.1:8008/cli-permission/healthz。

## 6. 升级、回滚与旧部署迁移

1. 查看成功流水线的摘要，预先 pull 新镜像。
2. 备份 MySQL、.env、service.env，记录旧镜像摘要。
3. 修改 CLI_ACCESS_IMAGE。有结构迁移时先停止旧应用，用新镜像执行一次 migrate；不要并发迁移。
4. `docker compose up -d --wait --wait-timeout 120 cli-access`，检查登录、授权、实际 CLI 与日志。
5. 同结构兼容回滚：改回旧摘要并重建；数据库迁移不自动回退，恢复备份会丢失备份后的写入，必须单独规划。

0.3.41 仍为结构版本 7，本次 Docker 改造没有新增数据库迁移。迁移旧 systemd 部署时先备份，在临时端口完成验证，维护窗口停止旧服务，再接管原端口或 Nginx 上游。保留 MySQL、域名和 /cli-permission 地址即可保留 CLI 配置；避免两个实例同时跑迁移，第一版只部署单实例。

## 7. 本地构建与离线分发

在项目根目录运行（需安装 Docker/Buildx）：

```bash
docker buildx build --platform linux/amd64 --load \
  --build-arg VERSION=0.3.41 \
  -t cli-access:local access-service
```

本地构建不会自动具备 GitHub 构建来源证明。修改 .env 指向 cli-access:local 即可部署。代码复制放在依赖安装之后，代码变更可复用依赖层；首次下载较慢。不要把 .venv 或旧离线运行时复制进镜像。

离线分发：联网机器拉取已验证镜像并赋予明确本地标签后执行 docker save，传到服务器 docker load；部署配置使用导入的标签，不执行 pull。通过 Docker daemon save/load 不应视为保留全部 registry 附件的方式；SBOM 和 provenance 应在联网镜像仓库验证、另行保存。生产正式升级仍推荐固定仓库摘要。

## 8. 维护与验证

- 更新基础镜像摘要和 requirements.lock 应经过相同流水线；用 PR 审查依赖升级。
- 官方 Actions 固定 SHA，定期人工更新并通过相同测试；遵守本项目仅推送 main 的规则。
- 测试入口：项目根目录 pytest；access-service 内 pytest；`node --test access-service/tests/test_time_presets.cjs`。
- 本地真实容器测试：干净 checkout、Docker、Python httpx，设置 CLI_ACCESS_IMAGE 后运行 `bash access-service/ci/smoke.sh`。它会拒绝覆盖已有 docker/service.env，并在退出时删除测试配置和临时数据库。不要在生产部署目录运行 compose.ci.yaml。
- GitHub 镜像失败时检查失败步骤和 access-smoke 附件。GHCR 403 检查 Packages 权限/仓库关联；镜像无法运行检查 amd64 架构；unhealthy 检查数据库和迁移；页面不可达检查 BIND_IP、端口和防火墙。

官方参考：
- https://docs.github.com/en/actions/tutorials/publish-packages/publish-docker-images
- https://docs.docker.com/build/ci/github-actions/attestations/
- https://docs.docker.com/build/ci/github-actions/cache/
- https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry

## 9. 只能访问 GitHub 的内网

成功镜像流水线会额外生成 offline-image 附件（保留 30 天），包含可用 docker load 导入的镜像、校验文件、配置示例和完整 docker run 操作指南。无需服务器 docker pull、Compose 或重新制作镜像。已有 GHCR 镜像可通过 Export existing access image for offline Docker 手动工作流输入精确 sha256 摘要导出，保持原镜像和源代码版本。下载者需登录 GitHub，附件下载域名需可达。参考 [离线导入与运行模板](权限管理系统Docker离线导入与运行.md)，下载附件内 README 已填入实际标签和文件名。
