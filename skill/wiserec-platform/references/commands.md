# `ml` 命令速查

本表列出全部命令，用于定位命令和判断风险；参数以 `ml <子命令> --help` 为准。`--config PATH` 是全局选项，放在子命令之前。只在帮助中列出 `--output`/`-o` 时才加 `-o json`。

“确认”列为“是”的命令默认会询问确认，在 shell 工具中必须在用户授权后加 `--yes`。“副作用”列标出会改变平台、远端或本地状态的命令，执行前核对目标和授权，执行后核验。

## 会话、业务与本地记录

| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml --version` | 查看实际调用的 CLI 版本 | | |
| `ml context [--json]` | 查看运行模式、平台环境与实际配置路径，无需登录 | | |
| `ml tree` | 当前安装版本的命令树，无需登录 | | |
| `ml env list` / `ml env show` | 列出环境 / 查看当前环境 | | |
| `ml env use NAME` | 切换当前环境 | | 本地配置 |
| `ml login` | 打开 Edge 登录，需用户操作；禁止 `--show-secrets` | | 本地凭据 |
| `ml logout [--all] [--forget-browser]` | 清除当前或全部环境的认证 | | 本地凭据 |
| `ml auth status` | 本地认证状态 | | |
| `ml auth ping start` / `stop` / `status` | 终端保活；shell 工具中 start 不生效 | | 本地进程 |
| `ml access status [--diagnose]` | 检查 CLI 访问授权 | | |
| `ml business list` / `ml business show` | 业务候选 / 当前业务 | | |
| `ml business use --tenant ID [--team ID] [--department ID]` | 选择业务；必须传 `--tenant` | | 本地配置 |
| `ml business refresh` | 打开 Edge 刷新业务目录 | | 本地配置 |
| `ml user info` | 当前账号 | | |
| `ml mep config get [KEY]` | 查询一个 MEP 配置项 | | |
| `ml history list -o json` | 本地调用记录，不证明远端结果 | | |
| `ml history clear [--env NAME] [--before TIME] --yes` | 删除本地调用记录 | 是 | 本地记录 |

## 训练与实验

详见 [training.md](training.md)。

| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml mtp swanboard project list` | 训练看板项目 | | |
| `ml mtp swanboard project namespace list PROJECT_ID` | 项目空间 | | |
| `ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID` | 空间下的实验 | | |
| `ml mtp swanboard experiment feature list EXPERIMENT_ID` | 实验特性 | | |
| `ml mtp swanboard experiment environment get EXPERIMENT_ID` | 实验环境 | | |
| `ml mtp swanboard experiment metrics EXPERIMENT_ID` | 指标统计 | | |
| `ml mtp swanboard experiment config list EXPERIMENT_ID` | 实验配置 | | |
| `ml mtp swanboard experiment inspect EXPERIMENT_ID` | 一次查询特性、环境、指标和配置 | | |
| `ml offline experiment list` | 离线实验 | | |
| `ml offline experiment trial list PROJECT_ID` | 实验下的 trial | | |
| `ml offline experiment clone PROJECT_ID --name NAME` | 克隆实验，可先 `--dry-run` | 是 | 创建实验 |
| `ml train list` | 训练任务 | | |
| `ml sample-task list` | 样本任务列表，默认旧任务管理；`--source new` 查询新版，支持分页、名称、创建者、修改者和重复 `--type` 筛选，`--status` 仅旧版可用 | | |
| `ml sample-task period list TASK_ID` | 新旧样本任务共用执行周期查询，无需 `--source`，四列网格；支持分页、北京时间范围及重复 `--state` | | |
| `ml sample-task execution list TASK_ID` | 新旧样本任务共用执行记录查询，无需 `--source`，支持分页、`--include-history` 和 `-o json` | | |
| `ml train instance list TASK_ID` | 执行实例 | | |
| `ml train history list TASK_ID` | 执行记录 | | |
| `ml train history logs download TASK_ID JOB_ID [--file PATH]` | 下载执行日志 | | 本地文件 |
| `ml train start TASK_ID` | 立即启动任务 | | 启动作业 |
| `ml train cancel TASK_ID` | 逐个取消全部执行实例 | 是 | 取消作业 |
| `ml train delete TASK_ID` | 软删除任务 | 是 | 删除任务 |
| `ml train clone TASK_ID --name NAME` | 复制任务 | 是 | 创建任务 |
| `ml train config export TASK_ID [--file PATH]` | 导出 YAML 配置 | | 本地文件 |
| `ml train config update TASK_ID --customize-config VALUE` | 更新自定义参数 | | 修改任务 |
| `ml algorithm list` | 算法仓 | | |
| `ml algorithm download ALGORITHM_ID [--file PATH]` | 下载算法仓 ZIP | | 本地文件 |
| `ml algorithm clone ALGORITHM_ID --name NAME --version VERSION` | 克隆算法仓 | 是 | 创建算法仓 |

## 模型、模板与服务

详见 [deployment.md](deployment.md) 和 [services.md](services.md)。

| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml model list` | 当前业务的模型 | | |
| `ml model detail MODEL_ID` | 模型详情 | | |
| `ml model source MODEL_ID [--train-task]` | 模型溯源，或关联训练任务 | | |
| `ml model deploy MODEL_ID --template DEPLOY_TEMPLATE_ID` | 部署为服务，先 `--dry-run` 预览 | 是 | 创建服务 |
| `ml resource template list` / `detail RESOURCE_TEMPLATE_ID` | 资源模板 | | |
| `ml deployment template list` / `detail DEPLOY_TEMPLATE_ID` | 部署模板 | | |
| `ml service list` | 服务 | | |
| `ml service mock SERVICE_ID [--transmission-tag 0\|1]` | 使用文档样例测试服务响应，默认不调用透传接口 | | 调用一次服务 |
| `ml service logs SERVICE_ID --no-input` | 日志文件列表或正文 | | |
| `ml service host list SERVICE_ID` | 主机视图 | | |
| `ml service host mock SERVICE_ID --host-address IP:PORT` | 使用文档样例测试指定主机，可选 `--transmission-tag 0\|1` | | 调用一次服务 |
| `ml service deployment list SERVICE_ID` | 部署视图 | | |

## 数据集与特征集

详见 [data.md](data.md)。

| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml dataset list` / `ml dataset detail DATASET_ID` | 数据集列表 / 详情 | | |
| `ml dataset files list DATASET_ID` | 数据集内部目录 | | |
| `ml dataset files upload DATASET_ID LOCAL_FILE` | 追加单个文件 | | 上传文件 |
| `ml feature-task list` | 特征任务列表，支持 `--name`、`--category`、`--create-user`、`--page`、`--page-size` 和 `-o json` | | |
| `ml feature-task execution list TASK_ID` | 分页查询执行记录，支持 `--include-history` | | |
| `ml feature-task execution logs search JOB_ID` | 日志搜索，默认原样文本，可选 `-o json` | | |
| `ml featureset wide list` / `ml featureset model list` | 宽表 / 模型特征集 | | |
| `ml featureset wide config SET_ID` / `ml featureset model config SET_ID` | 特征集配置 | | |
| `ml featureset wide export SET_ID` / `ml featureset model export SET_ID` | 导出特征 CSV，重名自动编号；支持 `--lang zh_cn\|en_us`、`--file PATH`、`--output text\|json` | | 本地文件 |

## Web Studio 与 Jupyter

详见 [jupyter.md](jupyter.md)。

| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml webstudio list` | 实例列表 | | |
| `ml webstudio show` | 默认实例绑定与缓存，不代表实时状态 | | |
| `ml webstudio login ENV_ID [--refresh]` | 建立连接并设为默认实例 | | 本地缓存 |
| `ml webstudio start ENV_ID` | 启动实例 | | 启动实例 |
| `ml webstudio stop ENV_ID` | 停止实例，可能中断运行中的任务 | | 停止实例 |
| `ml jupyter doctor` | 检查 Kernel 与终端管理接口 | | |
| `ml jupyter files list` / `stat` / `read` | 列目录 / 元数据 / 读文本 | | |
| `ml jupyter files write` / `mkdir` / `upload` / `move` / `copy` | 写入、建目录、上传、移动、复制 | | 远端文件 |
| `ml jupyter files delete PATH` | 立即删除，无确认 | | 删除远端文件 |
| `ml jupyter files download REMOTE LOCAL` | 下载单文件 | | 本地文件 |
| `ml jupyter exec --cwd PATH -- PROGRAM [ARGS...]` | 非交互执行远端程序 | | 远端进程 |
| `ml jupyter notebook run SOURCE` | 执行本地 Notebook | | 远端执行、本地结果 |
| `ml jupyter terminal list` | 列出远程终端 | | |
| `ml jupyter terminal close NAME` | 关闭远程终端及其中进程，无确认 | | 结束远端进程 |
| `ml jupyter terminal open` / `attach NAME` | 交互终端，**禁止使用** | | |
