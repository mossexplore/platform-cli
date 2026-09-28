# WiseRec CLI 使用手册

`ml` 用于管理 WiseRec 平台的环境、业务、训练任务、算法仓、特征集和开发工作空间。本手册面向命令使用者。示例中的 `TASK_ID`、`JOB_ID`、`PROJECT_ID`、`EXPERIMENT_ID`、`SET_ID` 等占位符，需要替换成列表查询得到的实际 ID。

## 1. 安装与首次使用

### 1.1 命令格式

取得管理员提供的 Windows 安装包后，完整解压并运行 `install.cmd`。安装完成后重新打开终端。

### 1.2 说明

使用 CLI 前，需要安装包所要求的 Python 环境和 Microsoft Edge。首次使用建议依次检查版本、选择环境、登录、选择业务，再执行查询命令。切换环境后，重新确认登录和业务选择。

### 1.3 示例

```bash
ml --version
ml env list
ml env use dev
ml login
ml business use
ml business show
ml train list
```

## 2. 全局用法

### 2.1 命令格式

```text
ml [OPTIONS] COMMAND [ARGS]...
```

### 2.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--version` | 显示当前安装版本 |
| `--help` | 显示命令帮助；可放在各级命令后 |
| `--output` / `-o` | 部分查询命令支持 `table` 或 `json`，以对应命令帮助为准 |

### 2.3 说明

不传命令时显示总帮助。需要查看某个命令的最新参数时，在该命令后加 `--help`。下文未列出的通用补全选项可通过总帮助查看。

### 2.4 示例

```bash
ml --help
ml train --help
ml train list --help
ml train list -o json
```

## 3. 登录与退出

### 3.1 命令格式

```text
ml login [OPTIONS]
ml logout [OPTIONS]
ml auth status
```

### 3.2 参数与选项

| 命令或选项 | 用途 |
| --- | --- |
| `ml login` | 打开 Edge 完成登录 |
| `ml login --show-secrets` | 登录后显示敏感认证信息，仅在确需排查时使用 |
| `ml logout` | 清除当前环境的登录状态 |
| `ml logout --all` | 清除所有环境的登录状态 |
| `ml logout --forget-browser` | 同时清除浏览器登录会话 |
| `ml auth status` | 查看当前账号和登录状态，不显示敏感信息 |

### 3.3 说明

登录状态失效时，业务命令可能提示重新登录。`ml auth status` 只检查现有状态，不会打开浏览器。`--forget-browser` 后再次登录可能需要重新验证身份。

### 3.4 示例

```bash
ml login
ml auth status
ml logout
```

## 4. 环境管理

### 4.1 命令格式

```text
ml env list
ml env show
ml env use NAME
```

### 4.2 参数与选项

| 参数 | 用途 |
| --- | --- |
| `NAME` | 要切换到的环境名称，从 `ml env list` 获取 |

### 4.3 说明

`list` 显示可用环境及访问状态，`show` 显示当前环境，`use` 切换环境。切换后请核对账号和业务选择。

### 4.4 示例

```bash
ml env list
ml env use dev
ml env show
ml auth status
```

## 5. 业务选择

### 5.1 命令格式

```text
ml business list
ml business show
ml business use [OPTIONS]
ml business refresh
```

### 5.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--tenant ID` | 选择租户 |
| `--team ID` | 在指定租户内选择团队，需同时提供 `--tenant` |
| `--department ID` | 同名租户有歧义时指定部门，需同时提供 `--tenant` |

### 5.3 说明

不带选项的 `ml business use` 会引导选择部门、租户和团队。业务命令至少需要选中租户；团队必须处于可用状态。`show` 可核对当前选择，目录发生变化时运行 `refresh`。

### 5.4 示例

```bash
ml business list
ml business use
ml business use --tenant mep --team team-a
ml business show
ml business refresh
```

## 6. 访问授权

### 6.1 命令格式

```text
ml access status [--diagnose]
```

### 6.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--diagnose` | 显示授权连接的排查信息 |

### 6.3 说明

先登录并选择业务。授权通过时显示成功提示；未授权、账号停用、版本不符合要求或连接失败时显示原因，业务命令会停止。需要排查连接问题时使用 `--diagnose`；分享诊断输出前请隐藏账号与内部地址。版本可用 `ml --version` 查看。

### 6.4 示例

```bash
ml access status
ml access status --diagnose
```

## 7. 当前用户

### 7.1 命令格式

```text
ml user info [--output table|json]
```

### 7.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 7.3 说明

显示当前登录用户的信息。需要将结果交给其他工具处理时可选 JSON 输出。

### 7.4 示例

```bash
ml user info
ml user info -o json
```

## 8. MEP 配置查询

### 8.1 命令格式

```text
ml mep config get [KEY] [--output table|json]
```

### 8.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `KEY` | 要查询的配置项名称；不填时查询默认项 |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 8.3 说明

此命令查询平台上的一个 MEP 配置项。若不确定配置项名称，请向管理员确认。

### 8.4 示例

```bash
ml mep config get
ml mep config get mep_service_access_type -o json
```

## 9. 训练看板

### 9.1 命令格式

```text
ml mtp swanboard project list
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard experiment feature list EXPERIMENT_ID
ml mtp swanboard experiment environment get EXPERIMENT_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID
ml mtp swanboard experiment config list EXPERIMENT_ID
ml mtp swanboard experiment inspect EXPERIMENT_ID
```

### 9.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `project list` | `--page`、`--page-size`、`--team-id`、`--creator` |
| `project namespace list` | `--team-id` |
| `project experiment list` | `--team-id` |
| `experiment feature list` | `--page`、`--page-size` |
| `experiment metrics` | 可重复使用 `--tag` 指定指标；不传时查询 `loss` 和 `accuracy` |
| 以上查询命令 | 均可使用 `--output` / `-o` 选择表格或 JSON |

### 9.3 说明

建议按“项目 → 项目空间 → 实验”的顺序取得所需 ID，再查询特性、环境、指标和配置。`inspect` 汇总实验信息，其中特性只展示第一页；需要更多特性时使用 `feature list` 翻页。各类 ID 不可混用。

### 9.4 示例

```bash
ml mtp swanboard project list --page 1
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss
ml mtp swanboard experiment inspect EXPERIMENT_ID -o json
```

## 10. 离线实验

### 10.1 命令格式

```text
ml offline experiment list [OPTIONS]
ml offline experiment trial list PROJECT_ID [OPTIONS]
ml offline experiment clone PROJECT_ID --name NAME [OPTIONS]
```

### 10.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `experiment list` | `--page`、`--page-size`、`--name` / `--project-name`、`--description`、`--create-user`、`--update-user`、`--team-id` |
| `experiment trial list` | `--page`、`--page-size`、`--name`、`--type`、`--creator`、`--updater`、`--ai-module` |
| `experiment clone` | 必填 `--name`；可选 `--dry-run` 预览、`--yes` / `-y` 跳过确认 |
| 以上命令 | `--output` / `-o` 选择表格或 JSON |

### 10.3 说明

`list` 查询当前业务的离线实验，`trial list` 查询某个实验下的 trial。克隆会创建新实验，不复制 trial；默认先预览并询问确认。仅想核对创建内容时使用 `--dry-run`。

### 10.4 示例

```bash
ml offline experiment list --name 训练 --page 1
ml offline experiment trial list PROJECT_ID --type batch
ml offline experiment clone PROJECT_ID --name 训练副本 --dry-run
ml offline experiment clone PROJECT_ID --name 训练副本
```

## 11. 训练任务

### 11.1 命令格式

```text
ml train list [OPTIONS]
ml train instance list TASK_ID
ml train history list TASK_ID
ml train start TASK_ID
ml train config export TASK_ID [--file PATH]
ml train history logs download TASK_ID JOB_ID [--file PATH]
ml train cancel TASK_ID [--yes]
ml train delete TASK_ID [--yes]
ml train clone TASK_ID --name NAME [OPTIONS]
ml train config update TASK_ID --customize-config VALUE
```

### 11.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--name`、`--page`、`--page-size`、`--output` / `-o` |
| `instance list`、`history list` | 必填 `TASK_ID`；可选 `--output` / `-o` |
| `start` | 必填 `TASK_ID`；执行后显示作业 ID |
| `config export` | 必填 `TASK_ID`；可选 `--file PATH` 指定保存位置 |
| `history logs download` | 必填 `TASK_ID`、`JOB_ID`；可选 `--file PATH`、`--output` / `-o` |
| `cancel`、`delete` | 必填 `TASK_ID`；可选 `--yes` / `-y` 跳过确认 |
| `clone` | 必填 `TASK_ID`、`--name NAME`；可选 `--customize-config VALUE`、`--yes` / `-y` |
| `config update` | 必填 `TASK_ID`、`--customize-config VALUE`；参数按字符串原样传递 |

### 11.3 说明

先用 `list` 找到任务 ID；`instance list` 查看执行实例，`history list` 查看执行记录及作业 ID。执行实例和执行记录默认只展示第一页 10 条。`start` 提交任务后返回作业 ID，表示平台接受了执行请求，不代表训练完成。

`cancel` 会逐个取消查询到的执行实例，并逐条显示结果；没有可取消的实例时会提示。`delete` 为软删除，`clone` 会按源任务创建副本，`config update` 更新自定义参数。操作结果不明时，先查询任务或执行记录状态，再决定是否重试。

配置导出保存为 YAML；日志下载默认保存为 ZIP。下载时显示进度，已有同名文件会自动编号，不覆盖。`--file PATH` 的父目录需已存在。

### 11.4 示例

```bash
ml train list --name demo
ml train instance list TASK_ID
ml train history list TASK_ID
ml train start TASK_ID
ml train config export TASK_ID --file ./task.yaml
ml train history logs download TASK_ID JOB_ID --file ./logs.zip
ml train cancel TASK_ID
ml train delete TASK_ID
ml train clone TASK_ID --name 新任务 --customize-config 0096999
ml train config update TASK_ID --customize-config 0096999
```

## 12. 算法仓

### 12.1 命令格式

```text
ml algorithm list [OPTIONS]
ml algorithm download ALGORITHM_ID [--file PATH]
ml algorithm clone SOURCE_ID --name NAME --version VERSION [--yes]
```

### 12.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name` / `--algorithm-name`、`--bucket-name`、`--output` / `-o` |
| `download` | 必填 `ALGORITHM_ID`；可选 `--file PATH` |
| `clone` | 必填 `SOURCE_ID`、`--name NAME`、`--version VERSION`；可选 `--yes` / `-y` |

### 12.3 说明

列表展示算法仓 ID、名称、版本、区域、修改者、修改时间、大小、描述、禁用状态和归档状态。修改时间按北京时间显示，大小自动换算为 M 或 G。空结果显示“暂无算法仓记录”。

下载命令会先显示下载地址，再保存文件并展示进度。文件名统一以 `.zip` 结尾；若已存在同名文件，会自动编号而不覆盖。`--file PATH` 的父目录需已存在。下载地址可能包含临时签名，请勿随意分享终端记录。

克隆默认先展示源 ID、新名称和版本并询问确认；成功后显示结果和新 ID（如果返回）。

### 12.4 示例

```bash
ml algorithm list --name mnist --page 1
ml algorithm download ALGORITHM_ID --file ./mnist.zip
ml algorithm clone SOURCE_ID --name mnist_copy --version latest
```

## 13. 特征集

### 13.1 命令格式

```text
ml featureset wide list [OPTIONS]
ml featureset model list [OPTIONS]
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

### 13.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `wide list`、`model list` | `--name`、`--page`、`--page-size`、`--output` / `-o` |
| `wide config`、`model config` | 必填 `SET_ID`；直接输出 JSON |

### 13.3 说明

`wide` 查询宽表特征集，`model` 查询模型特征集。列表展示 ID、名称、类型、场景和创建、修改信息；时间按北京时间显示。先从列表取得 `SET_ID`，再查看配置。配置查询固定输出 JSON，不提供 `--output` 选项。

### 13.4 示例

```bash
ml featureset wide list --name demo
ml featureset model list --page 2 -o json
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

## 14. Jupyter Notebook 与远程终端

### 14.1 命令格式

```text
ml jupyter doctor [--studio-id ENV_ID]
ml jupyter notebook run SOURCE [OPTIONS]
ml jupyter terminal list [--studio-id ENV_ID]
ml jupyter terminal open [--studio-id ENV_ID]
ml jupyter terminal attach NAME [--studio-id ENV_ID]
ml jupyter terminal close NAME [--studio-id ENV_ID]
```

### 14.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `SOURCE` | 要执行的本地 Notebook 文件 |
| `--download DIR` | Notebook 结果保存位置，默认 `results` |
| `--kernel NAME` | 指定 Kernel |
| `--cwd DIR` | 指定远程工作目录 |
| `--timeout SECONDS` | 代码执行时限，默认 600 秒 |
| `--startup-timeout SECONDS` | Kernel 启动等待时限，默认 60 秒 |
| `--output` / `-o` | Notebook 摘要使用 `text` 或 `json` |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，不改变默认选择 |

### 14.3 说明

使用前需由管理员开通 Jupyter 能力。`doctor` 检查连接；`notebook run` 在前台执行并保存结果，执行失败时也会尽可能保存已有输出。远程终端需服务端启用，`open` 创建终端，`attach` 连接现有终端，`close` 关闭终端。按 `Ctrl+]` 可断开当前连接而保留远程终端。

### 14.4 示例

```bash
ml jupyter doctor
ml jupyter notebook run analysis.ipynb --download results
ml jupyter terminal list
ml jupyter terminal open
ml jupyter terminal attach NAME
ml jupyter terminal close NAME
```

## 15. Web Studio

### 15.1 命令格式

```text
ml webstudio list [OPTIONS]
ml webstudio login ENV_ID
ml webstudio show
ml webstudio start ENV_ID
ml webstudio stop ENV_ID
```

### 15.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name`、`--status`、`--relator`、`--env-id`、`--business-id`、`--output` / `-o` |
| `login`、`start`、`stop` | 必填 Web Studio 实例 ID `ENV_ID` |
| `show` | 无参数 |

### 15.3 说明

先登录平台并选择业务，再使用 `list` 找到实例。`login` 选择默认实例并建立 Jupyter 连接；`show` 查看当前默认实例。`start` 和 `stop` 改变远程实例状态，不会改变默认选择。启动超时或中断时，先用 `list --env-id ENV_ID` 核对状态，再决定是否重试。

在 Jupyter 命令中使用 `--studio-id ENV_ID` 可临时操作其他实例。连接信息可能含临时凭据，请勿公开分享终端输出。

### 15.4 示例

```bash
ml webstudio list --status online
ml webstudio start ENV_ID
ml webstudio login ENV_ID
ml webstudio show
ml jupyter doctor --studio-id ENV_ID
ml webstudio stop ENV_ID
```

## 16. 输出与常见问题

### 16.1 输出格式

带 `--output` / `-o` 的命令可选择表格或 JSON，具体支持范围以该命令的帮助为准。查询结果为空时会显示相应提示。列表中需要完整复制 ID 时，可使用 JSON 输出；训练任务、算法仓和特征集表格中的时间按北京时间显示。

### 16.2 退出状态

| 状态 | 含义 |
| --- | --- |
| `0` | 命令成功；部分确认操作中回答“否”也返回 0 |
| `1` | 登录、授权、业务、网络或执行失败 |
| `2` | 命令参数错误，例如缺少必填项或页码无效 |

### 16.3 常见问题

- 提示未登录：执行 `ml login`，再用 `ml auth status` 核对。
- 提示未选择业务：执行 `ml business use`，再用 `ml business show` 核对。
- 看不到目标任务或实例：确认当前环境、业务和页码；需要时用名称筛选或继续翻页。
- 创建、删除或启动操作超时：先查询远程状态，再决定是否重试。
- 需要参数详情：在对应命令后使用 `--help`。
