# v1.0.0 — CLI 与权限管理系统

首个统一正式版本，同时提供 Windows CLI 安装包、Python Wheel 和权限管理系统 Docker 镜像。全部附件来自同一 main 提交，具体提交和镜像摘要见 manifest.json。

## 下载哪个文件

| 文件 | 适用场景 |
| --- | --- |
| wiserec-cli-1.0.0-windows-py3-online.zip | Windows 联网安装，支持配置企业 Python 包源 |
| wiserec-cli-1.0.0-windows-x64-py312-offline.zip | Windows x64、Python 3.12 离线安装，已包含 Python 依赖 |
| wiserec_cli-1.0.0-py3-none-any.whl | 使用 pip 安装 CLI，依赖另行准备 |
| cli-access-1.0.0-linux-amd64.tar.gz | Linux x86_64 权限管理系统 Docker 离线镜像 |
| service.env.example、Docker部署速查.md | 服务配置模板和部署步骤 |
| CLI安装指南.md、CLI参考使用指南.md | CLI 安装与使用说明 |
| SHA256SUMS、manifest.json | 文件校验、源提交、平台和镜像摘要 |

Windows CLI 需要预装 Python 和 Microsoft Edge；离线包不包含这两个软件。通用 CLI 要求 Python 3.9+，此次 Windows 安装与升级验证使用 Python 3.12 x64。Docker 镜像仅提供 linux/amd64，复用现有 MySQL 8.x，不包含数据库。

## 本版内容

- CLI 多环境登录、业务上下文切换与平台命令，支持权限服务校验。
- 人员、环境、授权和操作审计管理页面，以及北京时间展示与时间筛选。
- 权限服务支持固定目录只读挂载配置，修改配置后重启即可生效。
- GitHub 自动测试、构建镜像、校验离线导入，并提供统一下载附件。

## 快速安装

CLI：下载对应 ZIP，完整解压后运行 install.cmd。联网包需能访问 Python 包源，离线包需使用匹配的 Python 3.12 x64。

Docker：下载镜像、配置示例、校验文件和部署速查，在 Linux 执行：

```bash
sha256sum --ignore-missing -c SHA256SUMS
docker load -i cli-access-1.0.0-linux-amd64.tar.gz
```

随后按 Docker部署速查.md 设置 `/opt/cli-access-config/service.env`，只读挂载到 `/run/cli-access` 后启动 `cli-access:1.0.0`。联网用户可使用 `ghcr.io/mossexplore/cli-access:1.0.0`，私有包需授权；生产建议记录 manifest.json 中的精确摘要。

## 升级须知

- CLI 默认关闭权限校验，服务地址为空。部署人员需配置真实权限服务 URL 并启用校验；安装 CLI 不会自动部署权限系统。
- 安装器会用包内 config.json 覆盖用户默认配置，升级前备份自定义配置，升级后核对平台地址和权限服务设置。登录缓存和 Edge Profile 不因升级虚拟环境而删除。
- 数据库结构仍为版本 7。现有结构和管理员正常时无需重新初始化；旧结构迁移前先备份。
- Docker 镜像只适用于 linux/amd64；未承诺 ARM 或所有旧 Linux/Docker 组合兼容。
- 正式镜像和附件不覆盖，修复以新版本发布。生产服务器不会因本次发布自动升级。

## 验证范围

CLI/服务测试、浏览器时区测试、MySQL 真实容器授权及重启验证、挂载配置更新、Docker save/load、Windows 联网/离线安装及从 0.3.42 升级。真实业务平台登录和生产环境验收由部署方使用自己的账号完成。
