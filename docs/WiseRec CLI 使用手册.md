# WiseRec CLI 使用手册

`ml` 用于管理 WiseRec 平台的环境、业务、训练任务、算法仓、服务、数据集、特征集和开发工作空间。本手册面向命令使用者。示例中的 `TASK_ID`、`JOB_ID`、`PROJECT_ID`、`EXPERIMENT_ID`、`SET_ID`、`SERVICE_ID`、`DATASET_ID` 等占位符，需要替换成列表查询得到的实际 ID。

## 1. 命令树

### 1.1 命令格式

```text
ml                                              WiseRec 命令行工具
├── login                                       登录平台
├── logout                                      退出登录
├── tree                                        查看完整命令树
├── auth                                        登录状态
│   ├── status                                  查看当前登录状态
│   └── ping                                    管理终端会话自动保活
│       ├── start                               启动当前终端的保活
│       ├── status                              查看保活状态和最近请求
│       └── stop                                停止当前环境的保活
├── env                                         环境管理
│   ├── list                                    查看可用环境
│   ├── show                                    查看当前环境
│   └── use                                     切换环境
├── business                                    业务选择
│   ├── list                                    查看可选租户和团队
│   ├── show                                    查看当前业务选择
│   ├── use                                     选择租户或团队，可逐级返回或取消
│   └── refresh                                 刷新业务目录
├── access                                      访问授权
│   └── status                                  检查当前账号的访问权限
├── user                                        用户信息
│   └── info                                    查看当前用户信息
├── mep                                         MEP 管理
│   └── config                                  配置项查询
│       └── get                                 查看指定配置项
├── mtp                                         训练看板
│   └── swanboard                               项目和实验信息
│       ├── project                             项目
│       │   ├── list                            查看项目列表
│       │   ├── namespace                       项目空间
│       │   │   └── list                        查看项目空间列表
│       │   └── experiment                      项目中的实验
│       │       └── list                        查看实验列表
│       └── experiment                          实验详情
│           ├── feature                         实验特性
│           │   └── list                        查看特性列表
│           ├── environment                     实验环境
│           │   └── get                         查看运行环境
│           ├── metrics                         查看指标统计
│           ├── config                          实验配置
│           │   └── list                        查看配置项
│           └── inspect                         汇总查看实验信息
├── offline                                     离线业务
│   └── experiment                              离线实验
│       ├── list                                查看实验列表
│       ├── trial                               实验 Trial
│       │   └── list                            查看 Trial 列表
│       └── clone                               克隆实验
├── train                                       训练任务
│   ├── list                                    查看任务列表
│   ├── instance                                执行实例
│   │   └── list                                查看实例列表
│   ├── history                                 执行记录
│   │   ├── list                                查看执行记录
│   │   └── logs                                执行日志
│   │       └── download                        下载日志
│   ├── start                                   执行任务
│   ├── config                                  任务配置
│   │   ├── export                              导出配置
│   │   └── update                              更新自定义参数
│   ├── cancel                                  取消执行
│   ├── delete                                  删除任务
│   └── clone                                   克隆任务
├── model                                       模型信息查询
│   ├── list                                    查询当前业务的模型列表
│   ├── detail                                  查询模型详情
│   └── source                                  查询模型溯源或关联训练任务信息
├── algorithm                                   算法仓
│   ├── list                                    查看算法仓列表
│   ├── download                                下载算法仓文件
│   └── clone                                   克隆算法仓
├── service                                     服务管理
│   ├── list                                    查看服务列表
│   ├── logs                                    选择服务主机和文件并查看日志
│   ├── host                                    服务主机视图
│   │   └── list                                查看指定服务的主机列表
│   └── deployment                              服务部署视图
│       └── list                                查看指定服务的部署列表
├── dataset                                     数据集管理
│   ├── list                                    分页查询数据集
│   ├── detail                                  查看数据集详情
│   └── files                                   管理数据集目录和文件
│       ├── list                                查看指定目录内容
│       └── upload                              向指定目录追加文件
├── featureset                                  特征集
│   ├── wide                                    宽表特征集
│   │   ├── list                                查看列表
│   │   └── config                              查看配置
│   └── model                                   模型特征集
│       ├── list                                查看列表
│       └── config                              查看配置
├── jupyter                                     文件、非交互执行、Notebook 与终端
│   ├── doctor                                  检查连接状态
│   ├── exec                                    非交互执行远端程序
│   ├── files                                   远端文件与目录
│   │   ├── list                                列出目录
│   │   ├── stat                                查询文件信息
│   │   ├── read                                读取文本
│   │   ├── write                               写入文本
│   │   ├── mkdir                               创建目录
│   │   ├── upload                              上传单文件
│   │   ├── download                            下载单文件
│   │   ├── move                                移动或重命名
│   │   ├── copy                                复制文件至目录
│   │   └── delete                              删除文件或空目录
│   ├── notebook                                Notebook
│   │   └── run                                 执行 Notebook
│   └── terminal                                远程终端
│       ├── list                                查看终端列表
│       ├── open                                创建并连接终端
│       ├── attach                              连接已有终端
│       └── close                               关闭终端
└── webstudio                                   Web Studio 实例
    ├── list                                    查看实例列表
    ├── login                                   选择默认实例并刷新连接缓存
    ├── show                                    查看默认实例
    ├── start                                   启动实例
    └── stop                                    停止实例
```

### 1.2 参数与选项

`ml tree` 无需参数。各命令的参数与选项见对应章节。

### 1.3 说明

从上到下按顺序输入命令层级；使用 `--help` 查看具体用法。`ml tree` 中各命令的说明结尾不显示标点符号。

### 1.4 示例

```bash
ml tree
ml train history logs download --help
```

## 2. 安装与首次使用

### 2.1 命令格式

```text
install.cmd
ml env use NAME
ml login
ml business use
```

### 2.2 参数与选项

`NAME` 为 `ml env list` 中的环境名称。

### 2.3 说明

完整解压管理员提供的安装包，运行 `install.cmd` 后重新打开终端。使用前准备好所需 Python 环境和 Microsoft Edge，依次选择环境、登录、选择业务。

### 2.4 示例

```bash
ml env list
ml env use dev
ml login
ml business use
ml business show
ml train list
```

## 3. 全局用法

### 3.1 命令格式

```text
ml [OPTIONS] COMMAND [ARGS]...
ml tree
```

### 3.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--help` | 显示命令帮助；可放在各级命令后 |
| `ml tree` | 显示完整命令树及简短用途，无需登录或选择业务 |
| `--output` / `-o` | 部分查询命令支持 `table` 或 `json`，以对应命令帮助为准 |

### 3.3 说明

不传命令时显示帮助。`ml tree` 无需登录；参数详情使用对应命令的 `--help`。带 `--output` 的命令可切换输出格式，以命令帮助为准。

表格中的时间按北京时间显示，格式为 `YYYY-MM-DD HH:mm:ss`，不额外打印时区提示行。

提示未登录或未选择业务时，分别执行 `ml login`、`ml business use`。查询不到目标时核对环境、业务和页码；操作超时后先查询远程状态，再决定是否重试。

### 3.4 示例

```bash
ml --help
ml tree
ml train --help
ml train list --help
ml train list -o json
```

## 4. 登录与退出

### 4.1 命令格式

```text
ml login [OPTIONS]
ml logout [OPTIONS]
ml auth status
ml auth ping start
ml auth ping status
ml auth ping stop
```

### 4.2 参数与选项

| 命令或选项 | 用途 |
| --- | --- |
| `ml login` | 打开 Edge 完成登录 |
| `ml login --show-secrets` | 登录后显示敏感认证信息，仅在确需排查时使用 |
| `ml logout` | 清除当前环境的登录状态 |
| `ml logout --all` | 清除所有环境的登录状态 |
| `ml logout --forget-browser` | 同时清除浏览器登录会话 |
| `ml auth status` | 查看当前账号和登录状态，不显示敏感信息 |
| `ml auth ping start` | 为当前终端启动自动保活 |
| `ml auth ping status` | 查看保活进程和最近请求结果，不发送请求 |
| `ml auth ping stop` | 停止当前环境的自动保活 |

### 4.3 说明

登录后用 `auth status` 查看账号、剩余空闲时间及当前业务。默认空闲 30 分钟后校验登录，持续使用会延长会话；`--forget-browser` 会清除浏览器登录状态。

交互终端登录并选择业务后默认自动保活，空闲 10 分钟时请求平台。`ping status` 查看当前环境仍在运行的保活终端数及最近结果；`ping stop` 停止，`ping start` 恢复。关闭最后一个登记终端或退出登录后停止保活，休眠或断网时无法保活。

### 4.4 示例

```bash
ml login
ml auth status
ml auth ping status
ml logout
```

## 5. 环境管理

### 5.1 命令格式

```text
ml env list
ml env show
ml env use NAME
```

### 5.2 参数与选项

| 参数 | 用途 |
| --- | --- |
| `NAME` | 要切换到的环境名称，从 `ml env list` 获取 |

### 5.3 说明

`list` 显示可用环境及访问状态，`show` 显示当前环境，`use` 切换环境。切换后请核对账号和业务选择。

### 5.4 示例

```bash
ml env list
ml env use dev
ml env show
ml auth status
```

## 6. 业务选择

### 6.1 命令格式

```text
ml business list
ml business show
ml business use [OPTIONS]
ml business refresh
```

### 6.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--tenant ID` | 选择租户 |
| `--team ID` | 在指定租户内选择团队，需同时提供 `--tenant` |
| `--department ID` | 同名租户有歧义时指定部门，需同时提供 `--tenant` |
| `--search 关键词` | 按部门名称或 ID 的部分内容筛选交互列表，不能与 `--tenant` 同时使用 |

### 6.3 说明

`business use` 引导选择部门、租户和团队：输入序号选择，`b` 返回，`q` 取消，核对后输入 `y` 保存。`--search` 筛选部门；直接指定 `--tenant` 无需交互确认。取消时保留原选择。使用 `show` 核对选择，`refresh` 刷新目录。

### 6.4 示例

```bash
ml business list
ml business use
ml business use --search 云平台
ml business use --tenant mep --team team-a
ml business show
ml business refresh
```

## 7. 访问授权

### 7.1 命令格式

```text
ml access status [--diagnose]
```

### 7.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--diagnose` | 显示授权连接的排查信息 |

### 7.3 说明

先登录并选择业务。授权失败时按提示处理；需要排查连接时使用 `--diagnose`。分享诊断输出前隐藏账号与内部地址。

### 7.4 示例

```bash
ml access status
ml access status --diagnose
```

## 8. 当前用户

### 8.1 命令格式

```text
ml user info [--output table|json]
```

### 8.2 参数与选项

| 选项 | 用途 |
| --- | --- |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 8.3 说明

显示当前登录用户的信息。需要将结果交给其他工具处理时可选 JSON 输出。

### 8.4 示例

```bash
ml user info
ml user info -o json
```

## 9. MEP 配置查询

### 9.1 命令格式

```text
ml mep config get [KEY] [--output table|json]
```

### 9.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `KEY` | 要查询的配置项名称；不填时查询默认项 |
| `--output` / `-o` | 选择表格或 JSON 输出 |

### 9.3 说明

此命令查询平台上的一个 MEP 配置项。若不确定配置项名称，请向管理员确认。

### 9.4 示例

```bash
ml mep config get
ml mep config get mep_service_access_type -o json
```

## 10. 训练看板

### 10.1 命令格式

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

### 10.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `project list` | `--page`、`--page-size`、`--team-id`、`--creator` |
| `project namespace list` | `--team-id` |
| `project experiment list` | `--team-id` |
| `experiment feature list` | `--page`、`--page-size` |
| `experiment metrics` | 可重复使用 `--tag` 指定指标；不传时查询 `loss` 和 `accuracy` |
| 以上查询命令 | 均可使用 `--output` / `-o` 选择表格或 JSON |

### 10.3 说明

建议按“项目 → 项目空间 → 实验”的顺序取得所需 ID，再查询特性、环境、指标和配置。`inspect` 汇总实验信息，其中特性只展示第一页；需要更多特性时使用 `feature list` 翻页。各类 ID 不可混用。

### 10.4 示例

```bash
ml mtp swanboard project list --page 1
ml mtp swanboard project namespace list PROJECT_ID
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss
ml mtp swanboard experiment inspect EXPERIMENT_ID -o json
```

## 11. 离线实验

### 11.1 命令格式

```text
ml offline experiment list [OPTIONS]
ml offline experiment trial list PROJECT_ID [OPTIONS]
ml offline experiment clone PROJECT_ID --name NAME [OPTIONS]
```

### 11.2 参数与选项

| 命令 | 主要选项 |
| --- | --- |
| `experiment list` | `--page`、`--page-size`、`--name` / `--project-name`、`--description`、`--create-user`、`--update-user`、`--team-id` |
| `experiment trial list` | `--page`、`--page-size`、`--name`、`--type`、`--creator`、`--updater`、`--ai-module` |
| `experiment clone` | 必填 `--name`；可选 `--dry-run` 预览、`--yes` / `-y` 跳过确认 |
| 以上命令 | `--output` / `-o` 选择表格或 JSON |

### 11.3 说明

`list` 查询当前业务的离线实验，`trial list` 查询某个实验下的 trial。克隆会创建新实验，不复制 trial；默认先预览并询问确认。仅想核对创建内容时使用 `--dry-run`。

### 11.4 示例

```bash
ml offline experiment list --name 训练 --page 1
ml offline experiment trial list PROJECT_ID --type batch
ml offline experiment clone PROJECT_ID --name 训练副本 --dry-run
ml offline experiment clone PROJECT_ID --name 训练副本
```

## 12. 训练任务

### 12.1 命令格式

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

### 12.2 参数与选项

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

### 12.3 说明

先用 `list` 获取任务 ID，`history list` 获取作业 ID。实例和执行记录默认展示第一页 10 条；`start` 返回作业 ID，不代表训练完成。

`cancel` 取消查询到的执行实例；`delete` 软删除任务；`clone` 创建副本；`config update` 更新自定义参数。操作结果不明时先查询状态。

配置导出为 YAML，日志默认下载为 ZIP；同名文件自动编号，`--file` 的父目录须存在。

### 12.4 示例

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

## 13. 算法仓

### 13.1 命令格式

```text
ml algorithm list [OPTIONS]
ml algorithm download ALGORITHM_ID [--file PATH]
ml algorithm clone SOURCE_ID --name NAME --version VERSION [--yes]
```

### 13.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name` / `--algorithm-name`、`--bucket-name`、`--output` / `-o` |
| `download` | 必填 `ALGORITHM_ID`；可选 `--file PATH` |
| `clone` | 必填 `SOURCE_ID`、`--name NAME`、`--version VERSION`；可选 `--yes` / `-y` |

### 13.3 说明

先从列表获取算法仓 ID。下载保存为 ZIP，同名文件自动编号；`--file` 的父目录须存在。下载地址可能含临时签名，请勿公开分享。

克隆默认预览创建内容并询问确认，成功后显示结果及返回的新 ID。

### 13.4 示例

```bash
ml algorithm list --name mnist --page 1
ml algorithm download ALGORITHM_ID --file ./mnist.zip
ml algorithm clone SOURCE_ID --name mnist_copy --version VERSION
```

## 14. 服务管理

### 14.1 命令格式

```text
ml service list [OPTIONS]
ml service logs SERVICE_ID [--pod POD_NAME --cluster-name CLUSTER_NAME] [--type TYPE] [--file FILE_NAME] [-k TEXT] [-n N] [--list] [--no-input]
ml service host list SERVICE_ID [-o table|json]
ml service deployment list SERVICE_ID [-o table|json]
```

### 14.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`；可用 `--name` / `--service-name`、`--model-name`、`--model-version` 筛选；可选 `--output` / `-o` |
| `logs` | 必填 `SERVICE_ID`；可选成对的 `--pod` 与 `--cluster-name`，以及 `--type`、`--file`；`--keyword` / `-k` 可重复，`--lines` / `-n` 默认 200；`--list` 只列文件，`--no-input` 禁止交互；高级选项 `--search-order` 默认 tail、`--grep-scope` 默认 C、`--grep-line` 默认 0 |
| `host list`、`deployment list` | 必填 `SERVICE_ID`；可选 `--output` / `-o` |

### 14.3 说明

先登录并选择业务，从 `list` 获取服务 ID。服务列表默认每页 10 条；主机和部署详情显示第一页 10 条，时间按北京时间显示。

推荐使用 `ml service logs SERVICE_ID`。主机以表格展示编号、集群、pod名称、podIP、主机IP、状态、创建时间和更新时间，时间按北京时间显示；每页 10 条，先显示第一页，输入 n/p 按需翻页，输入 q 退出；选中后立即继续，不扫描剩余页。整个服务仅一台主机或仅一个文件时自动选择；类别无默认值，交互时以“编号、日志类别”表格展示，在“请选择日志类别”提示后输入编号，也可通过 `--type` 指定。文件选择仅展示一次文件表格，再输入编号，不重复列出文件名称。自动获取集群，Python 主机自动设置对应请求类型。`infer-python` 支持 run、interface、metrics、engine、ascend、mslite、alarm；`rtc` 支持 rtc、run、interface、dcs、metrics、gc、interface_manager、interface_extend、engine、monitor、catalina、dmq。文件列表和正文使用相同类别。

指定 `--pod` 时必须同时提供 `--cluster-name`；仅查询第一页，使用第一条主机的类型，直接查询指定 Pod 和集群，不验证其归属。请确保该服务主机类型一致且 Pod、集群填写正确。

非交互环境或指定 `--no-input` 时，选择不唯一会报错并提示补充参数；不默认选择第一台主机。未知主机类型、无匹配主机或文件会报错，文件列表为空时提示暂无日志文件。`--list` 不可与 `--file`、关键词、行数及正文检索选项混用。默认读取末尾 200 行，不持续刷新；日志正文写入标准输出，选择提示和上下文写入标准错误，可将正文重定向保存。


### 14.4 示例

```bash
ml service list --name demo --model-name model --model-version MODEL_VERSION
ml service list --page 2 --page-size 20 -o json
ml service logs SERVICE_ID
ml service logs SERVICE_ID -k error -n 500
ml service logs SERVICE_ID --list
ml service logs SERVICE_ID --pod POD_NAME --cluster-name CLUSTER_NAME --type interface --file FILE_NAME --no-input
ml service host list SERVICE_ID
ml service deployment list SERVICE_ID -o json
```

## 15. 数据集

### 15.1 命令格式

```text
ml dataset list [OPTIONS]
ml dataset detail DATASET_ID [-o table|json]
ml dataset files list DATASET_ID [--dir REMOTE_DIR] [-o table|json]
ml dataset files upload DATASET_ID LOCAL_FILE [--dir REMOTE_DIR] [--timeout SECONDS] [-o table|json]
```

### 15.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`；可用 `--name` / `--dataset-name`、`--create-user`、`--update-user`、`--bucket-name` 筛选；可选 `--output` / `-o` |
| `detail` | 必填 `DATASET_ID`；可选 `--output` / `-o` |
| `files list` | 必填 `DATASET_ID`；`--dir` 默认 `/`；可选 `--output` / `-o` |
| `files upload` | 必填 `DATASET_ID`、`LOCAL_FILE`；`--dir` 默认 `/`；`--timeout` 默认 1800 秒，限制单次网络操作等待时间；可选 `--output` / `-o` |

### 15.3 说明

先登录并选择业务。`list` 默认显示第一页 10 条，`detail` 查看指定数据集。大小自动换算，时间按北京时间显示；JSON 保留平台返回的其他字段。

`files list` 查看当前目录，在表格上方显示“当前位置：完整路径”。支持颜色的终端中，文件夹整行显示为黄色，文件行保持默认颜色。完整路径列可用于下一次查询，例如 `/event/20240815`。空目录也显示当前位置；提示结果不完整时，不代表已列出所有文件。JSON 输出包含 `currentDir` 和保留原字段的 `response`。

`files upload` 向已有数据集追加单个文件，自动查询数据集名称。仅支持 `.txt`、`.csv`、`.zip`、`.tar`、`.gz`、`.json`，扩展名大小写均可。文件名以英文字母或数字开头，仅可包含英文字母、数字、下划线、连字符和点。本地路径可包含中文，但文件名不可包含中文。当前保守限制为 2,000,000,000 字节。终端显示发送进度；发送完成不等于服务端处理完成。超时或断连后先查询目录核实，不自动重传。同名文件与压缩包处理规则由平台决定，当前不提供覆盖、解压或断点续传选项。上传结果 JSON 保留平台响应；请求成功后可查询目录确认处理结果。

### 15.4 示例

```bash
ml dataset list --name dog_cat --create-user l00123456
ml dataset list --bucket-name sfs-turbo-mep-guian2 --page 2 --page-size 20
ml dataset detail DATASET_ID
ml dataset detail DATASET_ID -o json
ml dataset files list DATASET_ID
ml dataset files list DATASET_ID --dir /event
ml dataset files list DATASET_ID --dir /event/20240815 -o json
ml dataset files upload DATASET_ID ./sample.csv
ml dataset files upload DATASET_ID ./sample.csv --dir /logs --timeout 1800
```

## 16. 特征集

### 16.1 命令格式

```text
ml featureset wide list [OPTIONS]
ml featureset model list [OPTIONS]
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

### 16.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `wide list`、`model list` | `--name`、`--page`、`--page-size`、`--output` / `-o` |
| `wide config`、`model config` | 必填 `SET_ID`；直接输出 JSON |

### 16.3 说明

`wide` 查询宽表特征集，`model` 查询模型特征集。列表展示 ID、名称、类型、场景和创建、修改信息；时间按北京时间显示。先从列表取得 `SET_ID`，再查看配置。配置查询固定输出 JSON，不提供 `--output` 选项。

### 16.4 示例

```bash
ml featureset wide list --name demo
ml featureset model list --page 2 -o json
ml featureset wide config SET_ID
ml featureset model config SET_ID
```

## 17. Jupyter Notebook 与远程终端

### 17.1 命令格式

```text
ml jupyter doctor [--studio-id ENV_ID]
ml jupyter notebook run SOURCE [OPTIONS]
ml jupyter terminal list [--studio-id ENV_ID]
ml jupyter terminal open [--studio-id ENV_ID]
ml jupyter terminal attach NAME [--studio-id ENV_ID]
ml jupyter terminal close NAME [--studio-id ENV_ID]
```

### 17.2 参数与选项

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

### 17.3 说明

使用前需由管理员开通 Jupyter 能力。`doctor` 检查连接；`notebook run` 在前台执行并保存结果，执行失败时也会尽可能保存已有输出。远程终端需服务端启用，`open` 创建终端，`attach` 连接现有终端，`close` 关闭终端。按 `Ctrl+]` 可断开当前连接而保留远程终端。

### 17.4 示例

```bash
ml jupyter doctor
ml jupyter notebook run analysis.ipynb --download results
ml jupyter terminal list
ml jupyter terminal open
ml jupyter terminal attach NAME
ml jupyter terminal close NAME
```

## 18. Web Studio

### 18.1 命令格式

```text
ml webstudio list [OPTIONS]
ml webstudio login ENV_ID [--refresh]
ml webstudio show
ml webstudio start ENV_ID
ml webstudio stop ENV_ID
```

### 18.2 参数与选项

| 命令 | 主要参数与选项 |
| --- | --- |
| `list` | `--page`、`--page-size`、`--name`、`--status`、`--relator`、`--env-id`、`--business-id`、`--output` / `-o` |
| `login` | 必填实例 ID `ENV_ID`；`--refresh` 显式强制重新建立连接，普通登录同样获取新凭据 |
| `start`、`stop` | 必填实例 ID `ENV_ID` |
| `show` | 无参数 |

### 18.3 说明

先登录平台并选择业务，再使用 `list` 找到实例。`login` 选择默认实例并建立 Jupyter 连接；`show` 查看当前默认实例。`start` 和 `stop` 改变远程实例状态，并清除当前环境的连接缓存，不会改变默认选择。启动超时或中断时，先用 `list --env-id ENV_ID` 核对状态，再决定是否重试。

执行 Jupyter 命令时，标准错误输出显示目标提示：`目标Web Studio名称：STUDIO_NAME，envId：ENV_ID`，方便核对实例；`--output json` 的标准输出仍为 JSON 结果。

在 Jupyter 命令中使用 `--studio-id ENV_ID` 可临时操作其他实例，并复用该实例的有效连接缓存。连接按配置、环境、账号、业务和实例隔离；平台登录凭据变化后自动重新获取连接。

当前环境的 `jupyter.connection_cache_ttl_seconds` 默认 `3600` 秒（1 小时），可设为 `0` 禁用，最大 `3600` 秒。缓存保存临时 Token 和会话 Cookie，请勿分享用户配置目录中的 `webstudio-connections` 文件。到期后自动重新连接，`ml logout` 清除当前环境缓存，`ml logout --all` 清除全部缓存。每条命令仍按配置执行在线权限检查。

只读请求明确返回 HTTP 401 时最多刷新重试一次；HTTP 403 不自动重试。写操作、已提交的执行以及结果不明确的请求不自动重放。实例重启或连接失效后，可运行 `ml webstudio login ENV_ID --refresh`。

### 18.4 示例

```bash
ml webstudio list --status online
ml webstudio start ENV_ID
ml webstudio login ENV_ID
ml webstudio show
ml jupyter doctor --studio-id ENV_ID
ml webstudio login ENV_ID --refresh
ml webstudio stop ENV_ID
```

## 19. Jupyter 文件操作

### 19.1 命令格式

```text
ml jupyter files list [PATH] [OPTIONS]
ml jupyter files stat PATH [OPTIONS]
ml jupyter files read PATH [OPTIONS]
ml jupyter files write PATH (--from-file LOCAL | --stdin) [OPTIONS]
ml jupyter files mkdir PATH [OPTIONS]
ml jupyter files upload LOCAL REMOTE [OPTIONS]
ml jupyter files download REMOTE LOCAL [OPTIONS]
ml jupyter files move SOURCE TARGET [OPTIONS]
ml jupyter files copy SOURCE TARGET_DIR [OPTIONS]
ml jupyter files delete PATH [OPTIONS]
```

### 19.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `PATH`、`REMOTE`、`SOURCE`、`TARGET` | 远端路径，相对 Jupyter 根目录；`list` 省略 PATH 时查看根目录 |
| `LOCAL` | 本地文件路径；下载目标须含文件名且父目录存在 |
| `TARGET_DIR` | 已有远端目录；复制后的文件名以输出的 path 为准 |
| `--from-file LOCAL` / `--stdin` | 写入 UTF-8 文本，二选一；stdin 从标准输入读取至 EOF |
| `--overwrite` | write、upload、download 允许覆盖已有文件，默认不覆盖 |
| `--start-line N` / `--end-line N` | read 的行范围，含首尾；起始行默认 1 |
| `--output text\|json` / `-o` | 默认 text；Agent 使用 json |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，默认使用已选实例 |

### 19.3 说明

先选择环境、登录并选择业务。Web Studio 模式下执行 `ml webstudio login ENV_ID`；直连模式使用管理员提供的 Jupyter 配置。文件操作无需先打开远程终端。

远端路径从 Jupyter 文件浏览器最顶层开始，不是本机目录或服务器 `/`。先用 `files list` 查看根目录，再使用返回的 path；`projects` 仅为示例，不一定存在。路径不得以 `/` 开头或包含 `..`，终端中的 `cd` 不影响文件命令。

`list/stat/read` 分别查看目录、信息和正文。mkdir 的父目录须存在；move 不覆盖目标；delete 立即删除文件或空目录，不再确认。上传、下载、复制与删除不递归处理目录。避免与浏览器同时修改同一文件；行范围读取仍会下载完整文件，不宜用于超大文件。

JSON 结果位于 `result`，外层标明服务器、实例和业务。read 的正文在 `result.content`，时间按北京时间显示。成功退出 0，操作失败退出 1，参数错误退出 2。

### 19.4 示例

```bash
ml webstudio list --status online
ml webstudio login ENV_ID
ml jupyter files list --output json
ml jupyter files list projects --output json
ml jupyter files mkdir projects/demo
ml jupyter files write projects/demo/main.py --from-file ./main.py --output json
ml jupyter files stat projects/demo/main.py --output json
ml jupyter files read projects/demo/main.py --start-line 1 --end-line 80
ml jupyter files write projects/demo/main.py --from-file ./main.py --overwrite
ml jupyter files upload ./data.csv projects/demo/data.csv
ml jupyter files download projects/demo/data.csv ./downloaded.csv
ml jupyter files copy projects/demo/main.py projects
ml jupyter files move projects/demo/data.csv projects/demo/input.csv
ml jupyter files delete projects/demo/input.csv
```

## 20. Jupyter 非交互执行

### 20.1 命令格式

```text
ml jupyter exec [OPTIONS] -- PROGRAM [ARGS...]
```

### 20.2 参数与选项

| 参数或选项 | 用途 |
| --- | --- |
| `PROGRAM [ARGS...]` | 远端程序及参数；放在 `--` 后，不隐式解释 Shell |
| `--cwd PATH` | 已有远端目录，相对 Jupyter 根目录；默认根目录 |
| `--timeout SECONDS` | 程序运行时限，默认 60 秒，最小 0.1 秒 |
| `--startup-timeout SECONDS` | Kernel 就绪等待时限，默认 60 秒 |
| `--kernel NAME` | Python Kernel 名称，默认使用当前环境配置 |
| `--max-output BYTES` | stdout/stderr 各自保留的字节上限，默认 1048576，最大 10485760 |
| `--output text\|json` / `-o` | 默认 text 为缩进 JSON；json 为单行结构化结果 |
| `--studio-id ENV_ID` | 临时指定 Web Studio 实例，默认使用已选实例 |

### 20.3 说明

连接准备同文件操作。远端须为 Linux/macOS 等 POSIX 系统并提供 Python Kernel，本机可使用 Windows。每次执行使用独立 Kernel，不继承已有 Notebook 变量；程序通过远端 PATH 查找，也可指定程序绝对路径。

不支持交互输入；管道和重定向须显式使用 `sh -c`。执行完成后返回 stdout、stderr 和退出码，超过输出上限会标记 `truncated`。不用于启动后台常驻服务，完成或超时时会清理同组子进程，主动脱离进程组的进程不保证清理。

JSON 的 `result` 包含执行 ID、状态、原始退出码和输出。断线或 Ctrl+C 后先检查远端状态，不自动重跑；`cleanup_errors` 非空时按 kernel_id 检查遗留资源。

| 状态 | CLI 退出码 | 含义 |
| --- | --- | --- |
| `SUCCEEDED` | 0 | 执行成功 |
| `FAILED` | 原始退出码 1–123，其余为 1 | 执行或启动失败 |
| `TIMED_OUT` | 124 | 远端确认超时并终止进程组 |
| `LOST` | 2 | 连接中断或结果不完整，远端状态未知 |
| `INTERRUPTED` | 130 | 本地中断，远端不一定已停止 |

### 20.4 示例

```bash
ml jupyter exec --cwd projects/demo --output json -- python main.py
ml jupyter exec --cwd projects/demo --timeout 120 --output json -- python -m pytest -q
ml jupyter exec --cwd projects/demo --output json -- sh -c 'pwd && ls -la'
```


## 21. 模型查询

### 21.1 命令格式

```text
ml model list [--page PAGE] [--page-size SIZE] [--name NAME] [--type TYPE] [--owner OWNER] [--team-id TEAM_ID] [--output table|json]
ml model detail MODEL_ID [--output table|json]
ml model source MODEL_ID [--train-task] [--output table|json]
```

### 21.2 参数与选项

| 命令 | 参数或选项 | 用途 |
| --- | --- | --- |
| `list` | `--page PAGE` | 页码，默认 1，最小 1 |
| `list` | `--page-size SIZE` | 每页条数，默认 10，最小 1 |
| `list` | `--name NAME` | 模型名称条件，默认空字符串 |
| `list` | `--type TYPE` | 模型类型条件，未指定时不限制 |
| `list` | `--owner OWNER` | 归属者条件，未指定时不限制 |
| `list` | `--team-id TEAM_ID` | 团队条件，默认空字符串 |
| `detail`、`source` | `MODEL_ID` | 必填模型 ID，可从模型列表复制 |
| `source` | `--train-task` | 查询关联训练任务，默认不启用 |
| 三个命令 | `--output table\|json` / `-o` | 默认沿用当前环境输出配置，table 为面向人工的展示，json 为完整接口响应 |

### 21.3 说明

先选择环境、登录并选择业务。查询使用当前环境的业务编码；四个列表条件可以组合使用，匹配规则由平台决定。每次查询指定的一页，不自动获取全部模型；列表固定查询云侧模型，其他查询条件暂不开放修改。

列表展示模型 ID、名称、模型版本、业务编码、类型、创建时间、更新时间、归属者和团队，并显示分页信息。首列 ID 完整展示；长字段换行，缺失或空值显示 `-`，空列表显示“暂无模型”。带时区的时间转换为北京时间；不含时区的已格式化时间保持原值。

详情按“字段：值”展示算法类型、标签、大小、存储、来源等信息。模型大小取自模型包大小（`pkgSize`），按 1024 进制转换为 B、KB、MB、GB 等单位；KB 及以上保留两位小数，0 显示 `0 B`。JSON 输出保留接口中的原始字节数、时间及扩展字段，便于程序处理。

溯源先读取模型详情中的来源标识，再查询来源模型信息，展示输出名称、模型版本、敏感、业务编码、状态、创建时间、描述、来源和存储桶。敏感值为 1 显示“是”，否则“否”；状态值为 1 显示“已发布”，否则“未发布”。创建时间按北京时间展示。详情与溯源响应须明确返回成功状态，来源标识缺失时停止溯源；溯源 JSON 输出保留来源接口的完整原始响应。

指定 `--train-task` 时，根据溯源信息中的训练执行标识继续查询训练任务，依次展示 jobId、任务Id、任务名称、业务编码、任务类型、镜像、资源规格和历史记录数目。训练执行标识缺失或任一步查询失败时停止并报错。此模式的 JSON 输出为训练任务接口完整原始响应，不混入模型详情或溯源结果；不指定此选项时仍只查询和输出模型溯源信息。

### 21.4 示例

```bash
ml model list
ml model list --page 2 --page-size 20
ml model list --name MODEL_NAME --type MODEL_TYPE
ml model list --owner OWNER --team-id TEAM_ID
ml model list -o json
ml model detail MODEL_ID
ml model detail MODEL_ID -o json
ml model source MODEL_ID
ml model source MODEL_ID -o json
ml model source MODEL_ID --train-task
ml model source MODEL_ID --train-task -o json
```
