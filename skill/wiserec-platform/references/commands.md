# `ml` 命令索引

本索引用于定位命令，不代替已安装版本的 `ml <子命令> --help`。`--config PATH` 是**全局**选项，应放在子命令前。下列 `ID`、`TASK_ID`、`JOB_ID`、`PROJECT_ID`、`NAMESPACE_ID`、`EXPERIMENT_ID`、`SET_ID`、`ENV_ID` 是不同类型的真实对象 ID 占位符。只在命令明确支持时加 `-o json` 或 `--output json`。

## 环境、认证、业务、权限

| 命令 | 作用与核验点 |
| --- | --- |
| `ml --version` | 确认安装和实际调用版本 |
| `ml env list` / `ml env show` | 列环境 / 看当前环境；固定表格 |
| `ml env use NAME` | 切换当前环境；`NAME` 为 `dev`、`mirror`、`explore`、`product` 中的实际目标 |
| `ml auth status` | 本地认证状态；必须检查 `status` 与 `remaining_seconds`，过期也可能退出 0 |
| `ml login` | 打开 Edge 登录；需图形界面和用户交互；不使用 `--show-secrets` |
| `ml business list` / `ml business show` | 列当前环境候选 / 看已选业务；固定人类可读输出 |
| `ml business use --tenant ID [--team ID] [--department ID]` | 选择当前环境业务；显式传 ID，避免无人值守时进入交互选择 |
| `ml business refresh` | 浏览器刷新业务目录，之后核对选择 |
| `ml access status` | 查 CLI 访问授权；拒绝时停止业务调用 |

`ml logout` 会清除认证缓存，只有用户要求退出或相应故障处理时使用。不要读写 `credentials.json`、`business.json` 来替代上述命令。

## 用户、MEP、训练看板

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml user info -o json` | 查询当前账号 |
| `ml mep config get KEY -o json` | 查询一个 MEP 配置键；省略 `KEY` 时使用 CLI 默认值 |
| `ml mtp swanboard project list -o json` | 项目列表；可用 `--page`、`--page-size`、`--team-id`、`--creator` |
| `ml mtp swanboard project namespace list PROJECT_ID -o json` | 项目空间；可用 `--team-id` |
| `ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID -o json` | 空间下实验；可用 `--team-id` |
| `ml mtp swanboard experiment feature list EXPERIMENT_ID -o json` | 实验特性；可用 `--page`、`--page-size` |
| `ml mtp swanboard experiment environment get EXPERIMENT_ID -o json` | 实验环境 |
| `ml mtp swanboard experiment metrics EXPERIMENT_ID --tag TAG -o json` | 指标统计；`--tag` 可重复，返回统计值不等于完整时间序列 |
| `ml mtp swanboard experiment config list EXPERIMENT_ID -o json` | 实验配置 |
| `ml mtp swanboard experiment inspect EXPERIMENT_ID -o json` | 汇总画像；特性只含第一页，需完整列表时另行翻页 |

按“项目 → 项目空间 → 实验 → 实验数据”定位。空间列表中的项目 ID 不等于实验 ID。`inspect` 会发起多次平台请求；只需单项信息时直接使用对应子命令更快。团队筛选不切换当前业务上下文。

## 离线实验与训练任务

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml offline experiment list -o json` | 实验列表；可用 `--page`、`--page-size`、`--name`/`--project-name` 等筛选 |
| `ml offline experiment trial list PROJECT_ID -o json` | 指定实验的 trial；可用 `--page`、`--page-size`、`--name`、`--type` 等筛选 |
| `ml offline experiment clone PROJECT_ID --name NAME --dry-run -o json` | 预览真实创建请求，不创建资源 |
| `ml offline experiment clone PROJECT_ID --name NAME --yes -o json` | 创建新实验；先核对源 ID、目标名称与 dry-run |
| `ml train list --name NAME -o json` | 搜索训练任务；可用 `--page`、`--page-size` |
| `ml train instance list TASK_ID -o json` | 执行实例；目前固定第一页 10 条，可能扫描任务列表而较慢 |
| `ml train history list TASK_ID -o json` | 执行记录；目前固定第一页 10 条，用 `jobId` 查后续日志 |
| `ml train history logs download TASK_ID JOB_ID --file PATH -o json` | 下载日志；确认本地路径、返回文件路径和字节数 |
| `ml train config update TASK_ID --customize-config VALUE` | 更新任务自定义参数；固定文本，不加 `-o` |
| `ml train start TASK_ID` | 立即启动任务；返回 `jobId` 仅表示请求获接受，再查执行记录确认状态 |

写请求超时或连接中断时先查目标状态再决定是否重试。日志下载是本地文件写入；执行前确认目标目录和文件位置。分页字段、响应字段应以实际返回和当前 CLI 版本为准，不能把文档示例视为完整响应。

## 特征集

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml featureset wide list -o json` | 宽表特征集；可用 `--name`、`--page`、`--page-size` |
| `ml featureset model list -o json` | 模型特征集；同上 |
| `ml featureset wide config SET_ID` | 宽表配置；固定 JSON，不加 `-o` |
| `ml featureset model config SET_ID` | 模型配置；固定 JSON，不加 `-o` |

## Web Studio 与 Jupyter

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml webstudio list -o json` | 实例列表；可用 `--page`、`--page-size`、`--name`、`--status`、`--relator`、`--env-id` |
| `ml webstudio show` | 查看当前默认实例；保存的名称可能不是实时状态 |
| `ml webstudio login ENV_ID` | 连接 online 实例并保存默认目标；可能打印含 Token 的访问 URL |
| `ml jupyter doctor [--studio-id ENV_ID]` | 检查 HTTP、Kernel、Terminal 接口；不验证 WebSocket |
| `ml jupyter notebook run SOURCE -o json [--studio-id ENV_ID]` | 执行本地 `.ipynb`，可用 `--download`、`--kernel`、`--cwd`、`--timeout`、`--startup-timeout` |
| `ml jupyter terminal list [--studio-id ENV_ID]` | 当前实例终端列表 |
| `ml jupyter terminal open [--studio-id ENV_ID]` | 创建并连接；必须使用真实 TTY |
| `ml jupyter terminal attach NAME [--studio-id ENV_ID]` | 重连该实例内的终端；必须使用真实 TTY |
| `ml jupyter terminal close NAME [--studio-id ENV_ID]` | 删除远端终端，可能中止远端进程 |

终端的具体 agent 操作见 [交互终端](terminal.md)。Notebook 默认前台执行，结果写入本地独立目录；失败或超时时检查摘要和远端状态，不自动重跑。Web Studio 动态连接使用当前环境业务选择，终端名称不能跨实例复用。
