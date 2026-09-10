# WiseRec CLI 与权限管理系统

面向 WiseRec 平台的命令行工具，以及配套的 Web 权限管理系统。

| 组件 | 谁使用 | 主要功能 |
| --- | --- | --- |
| **CLI（`ml`）** | 平台使用人员 | 登录和切换环境、选择业务、查询与操作训练任务、特征集等平台资源 |
| **权限管理系统** | 管理员 | 管理人员和环境、授予或撤销访问权限、设置有效期、查看调用记录和操作审计 |

启用权限校验后，CLI 在执行业务命令前向权限系统检查当前账号和环境的授权，通过后再调用平台接口。权限系统独立部署，数据保存在 MySQL；客户端校验不替代平台自身的权限控制。

## 下载 1.0.0

前往 [GitHub 正式版本](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.0)，按需要下载：

| 文件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.0-windows-py3-online.zip` | Windows 联网安装，支持企业 Python 包源 |
| `wiserec-cli-1.0.0-windows-x64-py312-offline.zip` | Windows x64、Python 3.12 离线安装 |
| `wiserec_cli-1.0.0-py3-none-any.whl` | 通过 pip 安装 CLI，依赖另行准备 |
| `cli-access-1.0.0-linux-amd64.tar.gz` | Linux x86_64 权限系统 Docker 镜像 |

Release 同时提供配置示例、安装指南和 `SHA256SUMS` 校验文件。

## CLI 快速使用

1. 预装 Python 和 Microsoft Edge。联网包要求 Python 3.9+；离线包要求 Python 3.12 x64。
2. 解压 Windows 安装包，运行 `install.cmd`。
3. 重新打开终端，选择已配置的环境并登录：

```bash
ml --version
ml env list
ml env use dev
ml login
ml business use
ml --help
```

将 `dev` 替换为实际环境名称。安装器使用独立虚拟环境，无需管理员权限；离线包包含 Python 依赖，不包含 Python 和 Edge 本体。

完整命令和参数见 [CLI 使用指南](docs/CLI参考使用指南.md)，企业包源与安装问题见 [Windows 安装说明](scripts/windows/INSTALL.md)。

## 部署权限管理系统

服务支持 Docker 部署，复用现有 MySQL 8.x。内网服务器无需拉取镜像，可下载 Release 中的离线镜像后导入：

```bash
docker load -i cli-access-1.0.0-linux-amd64.tar.gz
```

接着按 [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md) 完成配置和启动：

- 配置保存在宿主机 `/opt/cli-access-config/service.env`，只读挂载到容器 `/run/cli-access`。
- 使用镜像 `cli-access:1.0.0` 启动，默认端口 `8008`。
- 管理页面：`http://服务器IP:8008/cli-permission`。
- 管理员添加与平台登录账号一致的人员、配置对应环境并授予访问权限。
- 修改挂载配置后执行 `docker restart cli-access`；运行日志使用 `docker logs -f cli-access`。

新数据库需要初始化并创建管理员；已有结构版本 7 且管理员正常的数据库无需重新初始化。

## CLI 接入权限系统

**CLI 默认关闭权限校验。** 部署好服务后，在 CLI 使用的 `config.json` 中修改以下字段，保留其他配置：

```json
{
  "access_control": {
    "enabled": true,
    "url": "http://服务器IP:8008/cli-permission",
    "timeout_seconds": 15
  }
}
```

替换为客户端实际可访问的地址。完成登录和业务选择后，执行 `ml access status` 验证授权。

升级或重装 CLI 会覆盖用户默认配置，请先备份自定义设置，安装后核对平台地址和权限服务配置。配置位置、覆盖规则和授权排查见 [CLI 使用指南](docs/CLI参考使用指南.md)。

## 更多文档

- [CLI 使用与维护说明](docs/CLI使用与维护说明.md)：核心概念、命令速查、配置、架构与故障排查。
- [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md)：安装、启停、日志和常见报错。
- [Docker 与 GitHub 发布流程](docs/权限管理系统Docker部署与发布指南.md)：镜像构建、Compose 和 HTTPS。
- [非 Docker 部署手册](docs/权限管理系统Linux部署与运维手册.md)：Linux 离线包部署与数据库准备。
- [问题反馈](https://github.com/mossexplore/platform-cli/issues)：请附版本、运行环境及复现步骤，避免上传密码或登录凭据。
