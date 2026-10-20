# WiseRec CLI 与权限管理系统

面向 WiseRec 平台的命令行工具，以及配套的 Web 权限管理系统。

| 组件 | 谁使用 | 主要功能 |
| --- | --- | --- |
| **CLI（`ml`）** | 平台使用人员 | 登录和切换环境、选择业务、查询模型信息，以及查询与操作训练任务、算法仓、特征集等平台资源 |
| **权限管理系统** | 管理员 | 管理人员和环境、授予或撤销访问权限、设置有效期、查看调用记录和操作审计 |

启用权限校验后，CLI 在执行业务命令前向权限系统检查当前账号和环境的授权，通过后再调用平台接口。权限系统独立部署，数据保存在 MySQL；客户端校验不替代平台自身的权限控制。

当前 CLI 源码版本为 **1.0.7.10**，新增 `ml service host mock SERVICE_ID --pod-ip POD_IP`，使用样例报文测试指定主机，见 [发布说明](docs/RELEASE_NOTES_1.0.7.10.md)。

当前正式版本为 **1.0.7.10**，包括 CLI、权限管理系统及独立本地通知助手，见 [发布说明](docs/RELEASE_NOTES_1.0.7.10.md)。已发布为最新稳定版。本地开发参见 [Jupyter 本地开发指南](docs/Jupyter本地开发指南.md)。

新增本地命令历史：`ml history` 查看最近记录，`ml history clear` 清理。历史以文本保存在配置目录，最多保留 1000 条；`ml --no-history COMMAND` 可跳过本次记录。

## 下载 1.0.7.10

前往 [GitHub Release](https://github.com/mossexplore/platform-cli/releases/tag/v1.0.7.10)，按需要下载：

| 文件 | 用途 |
| --- | --- |
| `wiserec-cli-1.0.7.10-windows-py3-online.zip` | Windows 联网安装，支持企业 Python 包源 |
| `wiserec-cli-1.0.7.10-windows-x64-py312-offline.zip` | Windows x64、Python 3.12 离线安装 |
| `wiserec_cli-1.0.7.10-py3-none-any.whl` | 通过 pip 安装 CLI，依赖另行准备 |
| `cli-access-1.0.7.10-linux-amd64.tar.gz` | Linux x86_64 权限系统 Docker 镜像 |
| `permission-notifier-1.0.7.10-windows-source.zip` | 独立本地助手源码安装包，需要 Python 3.12 和依赖下载网络 |
| `Notifier-install.md` | 助手安装、Token 绑定、配置与退出说明 |

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

完整命令和参数见 [WiseRec CLI 使用手册](docs/WiseRec%20CLI%20使用手册.md)，企业包源与安装问题见 [Windows 安装说明](scripts/windows/INSTALL.md)。

## 部署权限管理系统

服务支持 Docker 部署，复用现有 MySQL 8.x。内网服务器无需拉取镜像，可下载 Release 中的离线镜像后导入：

```bash
docker load -i cli-access-1.0.7.10-linux-amd64.tar.gz
```

接着按 [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md) 完成配置和启动：

- 配置保存在宿主机 `/opt/cli-access-config/service.env`，只读挂载到容器 `/run/cli-access`。
- 使用镜像 `cli-access:1.0.7.10` 启动，默认端口 `8008`。
- 管理页面：`http://服务器IP:8008/cli-permission`。
- 管理员添加与平台登录账号一致的人员、配置对应环境并授予访问权限。
- 修改挂载配置后执行 `docker restart cli-access`；运行日志使用 `docker logs -f cli-access`。

新数据库需要初始化并创建管理员；从上一正式版本 1.0.7.7 升级结构仍为 12，无需迁移；先恢复演练、停写并完成最终备份，再切换镜像验收，不重新创建已有管理员。完整步骤与回滚限制见 [升级指南](docs/权限管理系统1.0.7.7升级至1.0.7.10指南.md)。

## CLI 接入权限系统

**CLI 默认开启权限校验。** 部署好服务后，在 CLI 使用的 `config.json` 中填写权限服务地址，保留其他配置：

```json
{
  "access_control": {
    "url": "http://服务器IP:8008/cli-permission",
    "timeout_seconds": 15
  }
}
```

替换为客户端实际可访问的地址。地址为空或未配置时，业务调用会报配置错误并停止。确需关闭时，在 `access_control` 中显式设置 `"enable": false`；默认配置无需写 `enable`。完成登录和业务选择后，执行 `ml access status` 验证授权。

升级或重装 CLI 会更新用户默认配置；自动保活开关和间隔会保留，其他自定义设置请先备份，安装后核对平台地址和权限服务配置。配置位置、覆盖规则和授权排查见 [WiseRec CLI 使用手册](docs/WiseRec%20CLI%20使用手册.md)。

## 更多文档

- [CLI 使用与维护说明](docs/CLI使用与维护说明.md)：核心概念、命令速查、配置、架构与故障排查。
- [Docker 部署速查](docs/权限管理系统Docker安装部署与调试指南.md)：安装、启停、日志和常见报错。
- [Docker 与 GitHub 发布流程](docs/权限管理系统Docker部署与发布指南.md)：镜像构建、Compose 和 HTTPS。
- [非 Docker 部署手册](docs/权限管理系统Linux部署与运维手册.md)：Linux 离线包部署与数据库准备。
- [问题反馈](https://github.com/mossexplore/platform-cli/issues)：请附版本、运行环境及复现步骤，避免上传密码或登录凭据。

## OpenCode 使用

OpenCode 集成分两个可见阶段执行：先安装并验证 CLI，再安装 `wiserec-platform` skill 和唯一的 `/ml` command。第二阶段失败会显示原因，CLI 仍可正常使用；排除文件占用或目录权限问题后，重新运行安装程序即可重试。

默认目标为当前用户的 `~/.config/opencode`，设置 `OPENCODE_CONFIG_DIR` 时使用该目录。每次安装都会删除旧 `skills/wiserec-platform` 目录和 `commands/ml.md`，完整写入随包的新资源，同版本重装也会更新。WiseRec skill 与 `/ml` command 由安装程序管理，请勿直接修改这些文件。其他 skill 和 command 不受影响。项目目录或兼容目录中的同名副本需自行移除，以免加载旧副本。

安装程序只执行 `opencode --version`。主版本号大于等于 2 时写入顶层 `permissions` 数组，受管理规则放在最后；能加载该数组的最低版本是 `@opencode/cli` 2.1.0。OpenCode 1.x（含 GitHub Release v1.19.3）会拒绝该数组：v1.18.35 与 v1.19.3 的 `packages/opencode/src/config/v2-compat.ts` 第 94–113 行报错 “V2 permissions are not supported by OpenCode V1… run opencode2”，更早的 1.x 报 Unrecognized key。1.1.1 至 1.x 改为写入 `permission.bash`。对象里还没有 `"*"` 时，把 `"*": "ask"` 放在第一项；用户已有的键保持原顺序；ask 与 deny 追加在最后。v1.19.3 `packages/opencode/src/permission/index.ts` 的 `evaluate` 用 `findLast`，`fromConfig` 按 `Object.entries` 的键顺序展开。低于 1.1.1，或 `opencode --version` 读不出版本时，安装停止，不改配置。写入后执行 `opencode debug config`，失败则从备份恢复原文件。带注释的 `opencode.jsonc` 会使安装失败。首次备份为 `opencode.json.bak` 或 `opencode.jsonc.bak`，已存在的这份备份不会被覆盖。用户的 `permission.bash`、`permission.shell` 和其他规则保留。`ml*` 放行会保留并警告；`"*": "allow"` 这类宽泛放行会单独警告。`shell` 的 `"*": "ask"` 作用于所有 shell 命令，不只是 `ml`。项目配置和 Agent 规则追加在全局规则之后，可以覆盖全局规则。OpenCode 2 里“始终允许”可以覆盖 ask，不能覆盖已配置的 deny（`@opencode/cli` 2.1.0 `packages/core/src/permission.ts` 的 `evaluateInput` 先检查配置规则）。OpenCode 1.x 的 `ask` 把已保存的允许接在规则集之后再 `findLast`，所以保存的允许可能覆盖更早的 deny。高风险 `ml` 命令、`--yes`、切换到 `product`、部署、训练启动、`ml jupyter exec` 和输出重定向需要在 OpenCode 中确认。只有完整写出的只读命令会被放行。`ml login --show-secrets`，以及用 `cat`、`type`、`gc`、`Get-Content`、`sls`、`findstr`、`Copy-Item` 读取 `credentials.json`，会被拒绝。`[IO.File]::ReadAllText` 和 `${路径}` 不是 shell 命令，规则无法拦截；凭据的 Windows DPAPI 加密存储另行处理，本次不实现。`python -m wiserec_cli.opencode_install --uninstall` 只删除带标记的规则。规则全文见 [skill/wiserec-platform/README.md](skill/wiserec-platform/README.md)。

完成后重新打开 OpenCode 会话，输入 `/ml 查询当前业务下的模型`；输入 `/ml` 可检查使用上下文并查看用法。直接通过 pip 安装 Wheel 不自动执行这一阶段，自动安装入口为官方 Windows 安装包。


## Windows 本地代码打包并安装

在仓库根目录的 CMD 中运行：

```bat
scripts\build-install.cmd
```

脚本使用当前本地工作区源码，依次调用现有的联网打包和安装脚本，不自动拉取远程代码。先更新本地代码再执行即可安装所需源码；未提交的本地修改也会参与打包。需要 Windows PowerShell、Python、联网包源及现有安装脚本要求的 Microsoft Edge。默认沿用当前用户的 CLI 安装目录，支持同版本重新安装，安装后重新打开终端使用 `ml`。

每次产物保存在 `release\local-builds` 下的独立目录，打包失败不会继续安装，不会选择旧包。构建包属于本地验证产物，不是 GitHub 正式发行版。安装过程同时沿用原安装器的 OpenCode 资源安装流程，具体结果见终端输出。

可选参数：

```bat
scripts\build-install.cmd -IndexUrl https://PACKAGE_HOST/simple
scripts\build-install.cmd -InstallDirectory "D:\Tools\WiseRecCLI"
scripts\build-install.cmd -OutputDirectory "D:\Builds\WiseRecCLI"
```

`-Force` 会按原安装器规则重建安装虚拟环境，日常同版本覆盖无需指定；`-SkipEdgeCheck` 仅跳过安装时的 Edge 检查。打包和安装阶段共用 `-IndexUrl`；企业证书等 pip 环境配置继续沿用现有脚本行为。执行失败时返回非零退出码。
