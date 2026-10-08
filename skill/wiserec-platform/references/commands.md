# `ml` 命令索引

本索引按当前项目命令树整理，用于定位命令；已安装版本的 `ml <子命令> --help` 是参数依据。`--config PATH` 是**全局**选项，应放在子命令前。`TASK_ID`、`JOB_ID`、`PROJECT_ID`、`NAMESPACE_ID`、`EXPERIMENT_ID`、`ALGORITHM_ID`、`MODEL_ID`、`SERVICE_ID`、`POD_NAME`、`DATASET_ID`、`SET_ID`、`ENV_ID` 等占位符表示不同对象，不能互换。只在命令明确支持时加 `-o json`。

## 环境、认证、业务、权限

| 命令 | 作用与核验点 |
| --- | --- |
| `ml --version` | 确认安装和实际调用版本 |
| `ml tree` | 无需登录，显示当前安装版本全部命令的层级与简短用途；不展示参数 |
| `ml --help` / `ml <子命令> --help` | 查当前安装版本的命令与参数 |
| `ml env list` / `ml env show` | 列环境 / 看当前环境；固定表格 |
| `ml env use NAME` | 切换当前环境；`NAME` 为 `dev`、`mirror`、`explore`、`product` 中的实际目标 |
| `ml auth ping start` / `ml auth ping status` / `ml auth ping stop` | 启动当前终端保活 / 查看当前环境保活终端数及最近结果 / 停止当前环境保活 |
| `ml auth status` | 本地认证状态；必须检查 `status` 与 `remaining_seconds`，过期也可能退出 0 |
| `ml login` | 打开 Edge 登录；需图形界面和用户交互；不使用 `--show-secrets` |
| `ml logout [--all] [--forget-browser]` | 清除当前环境或全部环境的认证信息；`--forget-browser` 同时清除浏览器会话 |
| `ml business list` / `ml business show` | 列当前环境候选 / 看已选业务；固定人类可读输出 |
| `ml business use --tenant ID [--team ID] [--department ID]` | 选择当前环境业务；显式传 ID，避免无人值守时进入交互选择 |
| `ml business refresh` | 浏览器刷新业务目录，之后核对选择 |
| `ml access status [--diagnose]` | 查 CLI 访问授权；诊断输出可能包含内部地址，只在排障时使用 |

`ml logout` 仅在用户要求退出或相应故障处理时使用。不要读写 `credentials.json`、`business.json` 来替代上述命令。

## 用户、MEP、训练看板

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml user info -o json` | 查询当前账号 |
| `ml mep config get [KEY] -o json` | 查询一个 MEP 配置键；省略 `KEY` 时使用 CLI 默认值 |
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
| `ml train start TASK_ID` | 立即启动任务；返回 `jobId` 仅表示请求获接受，再查执行记录确认状态 |
| `ml train config export TASK_ID [--file PATH]` | 导出 YAML 配置并显示下载进度；默认按任务 ID 命名 |
| `ml train config update TASK_ID --customize-config VALUE` | 更新任务自定义参数；固定文本，不加 `-o` |
| `ml train cancel TASK_ID [--yes]` | 查询全部执行实例并逐个取消；每个实例单独报告结果，无实例时退出 1 |
| `ml train delete TASK_ID [--yes]` | 软删除当前业务中的任务；默认询问确认 |
| `ml train clone TASK_ID --name NAME [--customize-config VALUE] [--yes]` | 读取源任务详情并创建副本；成功后可能返回新任务 ID |

写请求超时或连接中断时先查目标状态再决定是否重试。配置导出与日志下载写入本地文件；执行前确认目标目录和文件位置，CLI 不覆盖已有同名文件。`cancel` 的部分实例可能失败，需看逐条结果及退出码。分页字段、响应字段应以实际返回和当前 CLI 版本为准，不能把文档示例视为完整响应。

## 算法仓

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml algorithm list -o json` | 分页查询；可用 `--page`、`--page-size`、`--name`/`--algorithm-name`、`--bucket-name` |
| `ml algorithm download ALGORITHM_ID [--file PATH]` | 先获取下载链接再保存 ZIP，显示进度；链接可能含临时签名 |
| `ml algorithm clone ALGORITHM_ID --name NAME --version VERSION [--yes]` | 按指定名称和版本创建副本；默认询问确认，可能返回新 ID |

下载前确认本地目录；不要把签名下载链接复制到回答或共享日志。克隆结果不明时先查询目标名称与版本，再决定是否重试。

## 模型详情与溯源

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml model list -o json` | 当前业务云侧模型；可用 `--page`、`--page-size`、`--name`、`--type`、`--owner`、`--team-id` |
| `ml model detail MODEL_ID -o json` | 模型详情；人工展示的模型大小读取 `pkgSize`，按 1024 换算单位 |
| `ml model source MODEL_ID -o json` | 查询模型来源；内部从详情取得 `sourceId`，JSON 为来源接口完整响应 |
| `ml model source MODEL_ID --train-task -o json` | 从来源取得 `jobId` 再查询关联训练任务；JSON 仅为训练任务接口完整响应 |

三个命令均支持 `--output table|json` / `-o`，默认沿用环境配置。模型列表项位于 `result.models`。模型详情和来源字段位于 `result`；训练任务字段位于 `result.jobHistoryDetail`，其中 `jobId` 为执行标识，`taskId` 为任务标识。人工展示依次包括 jobId、任务Id、任务名称、业务编码、任务类型、镜像、资源规格、历史记录数目。

溯源的模型版本读取 `modelVersion`，不是详情中的 `modelTag`。敏感值 1 显示“是”，其他值“否”；状态值 1 显示“已发布”，其他值“未发布”；时间换算为北京时间。普通字段缺失显示 `-`，0 保留。详情、溯源和关联训练任务均要求 `result.code` 为整数 0；必要的 sourceId/jobId 缺失或响应结构无效时停止，不猜测关联关系。

## 服务与主机日志

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml service list -o json` | 分页查询服务；可用 `--page`、`--page-size`、`--name`/`--service-name`、`--model-name`、`--model-version` |
| `ml service logs SERVICE_ID` | 推荐入口；按需分页选择主机，自动取得集群，选择类别和文件后读取正文 |
| `ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type TYPE --list --no-input` | 只列日志文件，固定表格；不能与 --file、关键词、行数或正文检索选项混用 |
| `ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type TYPE --file FILE_NAME -k TEXT -n 200 --no-input` | 非交互检索；--keyword/-k 可重复，--lines/-n 默认 200，正文为原始文本 |
| `ml service host list SERVICE_ID -o json` | 主机视图固定第 1 页 10 条；nodeName 是 Pod 名称，不能当作完整主机集合 |
| `ml service deployment list SERVICE_ID -o json` | 部署视图固定第 1 页 10 条，首列为 blockId |

不接受 `--cluster` 或 `-o json`；指定 Pod 时使用 `--cluster-name`。主机和文件只有一个候选时自动选择；多项时仅在交互终端提示。agent 使用 `--no-input`，无法唯一确定时补充参数；指定 Pod 时必须同时提供其集群名。日志类别无默认值，自动化必须明确传入 `--type`。未指定 Pod 时也可在唯一主机情况下自动选择，文件同理。

| 主机 infraType | 可用 --type 值 |
| --- | --- |
| `infer-python` | run、interface、metrics、engine、ascend、mslite、alarm |
| `rtc` | rtc、run、interface、dcs、metrics、gc、interface_manager、interface_extend、engine、monitor、catalina、dmq |

文件列表和正文都使用同一个 `data.serviceLogSearch.type`。CLI 对 `infer-python` 自动设置外层 `data.type=rtc_python`；`rtc` 不携带外层类型。不要把 `rtc_python` 当作主机 infraType 或传给 `--type`。未知主机类型报错，不绕过识别。

高级选项为 `--search-order`（默认 tail）、`--grep-scope`（默认 C）、`--grep-line`（默认 0）。行数选项是 `--lines/-n`。日志不持续刷新；正文 stdout 可重定向到文件，选择提示和上下文在 stderr。空文件列表会提示暂无日志文件且不检索正文；指定的主机或文件不存在会失败。交互取消退出 130。注意日志内容可能包含敏感信息。

主机交互浏览每页 10 条，n/p 翻页，q 取消；返回已浏览页使用本次缓存。`--pod` 和 `--cluster-name` 必须成对提供，此模式只读取主机第一页第一条的 infraType，直接使用指定 Pod 和集群，不验证归属；使用前确认服务主机类型一致。非交互且多主机时第一页后立即报错，不扫描全量。

## 数据集

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml dataset list -o json` | 可用 `--page`、`--page-size`、`--name`/`--dataset-name`、`--create-user`、`--update-user`、`--bucket-name` |
| `ml dataset detail DATASET_ID -o json` | 查询指定数据集详情 |

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
| `ml webstudio list -o json` | 实例列表；可用 `--page`、`--page-size`、`--name`、`--status`、`--relator`、`--env-id`、`--business-id` |
| `ml webstudio show` | 查看当前默认实例；保存的名称可能不是实时状态 |
| `ml webstudio login ENV_ID` | 连接 online 实例并保存默认目标；可能打印含 Token 的访问 URL |
| `ml webstudio start ENV_ID` | 启动实例；完成提示后用列表核对实际状态 |
| `ml webstudio stop ENV_ID` | 停止实例；可能中断正在运行的 Notebook 或终端，先核对目标 |
| `ml jupyter doctor [--studio-id ENV_ID]` | 检查 HTTP、Kernel、Terminal 接口；不验证 WebSocket |
| `ml jupyter notebook run SOURCE -o json [--studio-id ENV_ID]` | 执行本地 `.ipynb`，可用 `--download`、`--kernel`、`--cwd`、`--timeout`、`--startup-timeout` |
| `ml jupyter terminal list [--studio-id ENV_ID]` | 当前实例终端列表 |
| `ml jupyter terminal open [--studio-id ENV_ID]` | 本 skill 禁止调用；程序执行改用 `ml jupyter exec` |
| `ml jupyter terminal attach NAME [--studio-id ENV_ID]` | 本 skill 禁止调用；程序执行改用 `ml jupyter exec` |
| `ml jupyter terminal close NAME [--studio-id ENV_ID]` | 删除远端终端，可能中止远端进程 |

文件与执行命令均支持 `--studio-id ENV_ID`、`--output text|json`；操作前读 [Jupyter 文件与非交互执行](jupyter.md)。

| 命令 | 用途与关键选项 |
| --- | --- |
| `ml jupyter files list [PATH] -o json` | 列一层目录，默认根目录 |
| `ml jupyter files stat PATH -o json` | 查询文件或目录元数据 |
| `ml jupyter files read PATH -o json` | 读取文本；`--start-line`、`--end-line` |
| `ml jupyter files write PATH --from-file LOCAL -o json` | 写入文本；可改用 `--stdin`，覆盖用 `--overwrite` |
| `ml jupyter files mkdir PATH -o json` | 创建单层目录 |
| `ml jupyter files upload LOCAL REMOTE -o json` | 上传单文件，支持 `--overwrite` |
| `ml jupyter files download REMOTE LOCAL -o json` | 下载单文件，支持 `--overwrite` |
| `ml jupyter files move SOURCE TARGET -o json` | 移动或重命名，不覆盖 |
| `ml jupyter files copy SOURCE TARGET_DIR -o json` | 复制单文件到已有目录 |
| `ml jupyter files delete PATH -o json` | 立即删除文件或空目录，无确认、不递归 |
| `ml jupyter exec --cwd PATH -o json -- PROGRAM [ARGS...]` | 非交互执行；支持 `--timeout`、`--startup-timeout`、`--max-output`、`--kernel` |

禁止使用交互式 TTY/PTY，见 [非交互执行约束](terminal.md)。terminal list/close 仅在用户要求检查或关闭既有终端时使用，不用于建立交互执行流程。Notebook 默认前台执行，结果写入本地独立目录；失败或超时时检查摘要和远端状态，不自动重跑。Web Studio 动态连接使用当前环境业务选择，终端名称不能跨实例复用。`ml webstudio start` 和 `stop` 不改变默认实例选择。
