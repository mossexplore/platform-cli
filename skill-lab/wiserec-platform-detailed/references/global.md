# 全局选项与命令组

## 根命令

```text
ml [GLOBAL_OPTIONS] COMMAND [ARGS]
```

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `--config` | FILE | 否 | 未指定（None） | 路径须存在；不允许目录；检查可读；解析为绝对路径；config.json 路径，也可使用 ML_CONFIG 环境变量 |
| `--no-history` | BOOLEAN | 否 | `false` | 开关，无需参数值；不保存本次命令历史 |
| `--version` | BOOLEAN | 否 | `false` | 开关，无需参数值；显示版本 |
| `--install-completion` | BOOLEAN | 否 | 未指定（None） | 开关，无需参数值；Install completion for the current shell. |
| `--show-completion` | BOOLEAN | 否 | 未指定（None） | 开关，无需参数值；Show completion for the current shell, to copy it or customize the installation. |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

`--config` 优先于 ML_CONFIG 环境变量，路径必须存在且为可读文件。`--version` 是立即退出的全局选项，输出 ml 与版本文本；`algorithm clone --version VERSION` 则是算法仓参数。`--no-history` 禁止本次历史保存。shell 补全选项由 Typer 提供，安装补全会修改本地 shell 配置，测试 skill 不为业务任务自动安装。

## 组入口行为

单独 `ml` 和大多数命令组用于显示帮助，帮助输出不代表业务操作成功。`ml history` 无子命令时有实际行为：交互浏览历史；非交互显示最近 20 条。Agent 应使用 `ml history list -o json`。

| 命令组 | 说明 | 入口行为 |
| --- | --- | --- |
| `ml` | WiseRec平台命令行客户端 | 命令分组/帮助 |
| `ml access` | 检查 CLI 在线访问授权 | 命令分组/帮助 |
| `ml algorithm` | 算法仓查询、下载与克隆 | 命令分组/帮助 |
| `ml auth` | 查看认证状态 | 命令分组/帮助 |
| `ml auth ping` | 管理终端会话自动保活 | 命令分组/帮助 |
| `ml business` | 管理部门、租户和团队 | 命令分组/帮助 |
| `ml dataset` | 数据集管理 | 命令分组/帮助 |
| `ml dataset files` | 管理数据集目录和文件 | 命令分组/帮助 |
| `ml deployment` | 部署管理 | 命令分组/帮助 |
| `ml deployment template` | 部署模板查询 | 命令分组/帮助 |
| `ml env` | 管理运行环境 | 命令分组/帮助 |
| `ml feature-task` | 特征任务 | 命令分组/帮助 |
| `ml feature-task execution` | 特征任务执行记录 | 命令分组/帮助 |
| `ml feature-task execution logs` | 执行记录日志 | 命令分组/帮助 |
| `ml featureset` | 特征集 | 命令分组/帮助 |
| `ml featureset model` | 模型特征集查询 | 命令分组/帮助 |
| `ml featureset wide` | 宽表特征集查询 | 命令分组/帮助 |
| `ml history` | 查看和管理本地命令历史 | 浏览历史 |
| `ml jupyter` | Jupyter 文件、非交互执行、Notebook 与 Terminal | 命令分组/帮助 |
| `ml jupyter files` | 远端单文件与目录操作（非交互） | 命令分组/帮助 |
| `ml jupyter notebook` | 执行完整 Notebook | 命令分组/帮助 |
| `ml jupyter terminal` | 远程交互终端；Ctrl+] 断开连接 | 命令分组/帮助 |
| `ml mep` | MEP 管理 | 命令分组/帮助 |
| `ml mep config` | MEP 配置 | 命令分组/帮助 |
| `ml model` | 模型查询与部署 | 命令分组/帮助 |
| `ml mtp` | MTP 管理 | 命令分组/帮助 |
| `ml mtp swanboard` | 训练看板管理 | 命令分组/帮助 |
| `ml mtp swanboard experiment` | 训练看板实验数据查询 | 命令分组/帮助 |
| `ml mtp swanboard experiment config` | 训练看板实验配置 | 命令分组/帮助 |
| `ml mtp swanboard experiment environment` | 训练看板实验环境 | 命令分组/帮助 |
| `ml mtp swanboard experiment feature` | 训练看板实验特性 | 命令分组/帮助 |
| `ml mtp swanboard project` | 训练看板项目管理 | 命令分组/帮助 |
| `ml mtp swanboard project experiment` | 训练看板项目实验管理 | 命令分组/帮助 |
| `ml mtp swanboard project namespace` | 训练看板项目空间管理 | 命令分组/帮助 |
| `ml offline` | 离线业务管理 | 命令分组/帮助 |
| `ml offline experiment` | 离线实验管理 | 命令分组/帮助 |
| `ml offline experiment trial` | 离线实验 trial 管理 | 命令分组/帮助 |
| `ml resource` | 资源管理 | 命令分组/帮助 |
| `ml resource template` | 资源模板查询 | 命令分组/帮助 |
| `ml sample-task` | 样本任务 | 命令分组/帮助 |
| `ml sample-task execution` | 新版样本任务执行记录 | 命令分组/帮助 |
| `ml sample-task period` | 新版样本任务执行周期 | 命令分组/帮助 |
| `ml service` | 服务查询、模拟调用与日志查看 | 命令分组/帮助 |
| `ml service deployment` | 服务部署视图查询 | 命令分组/帮助 |
| `ml service host` | 服务主机查询与测试 | 命令分组/帮助 |
| `ml train` | 训练任务查询与执行管理 | 命令分组/帮助 |
| `ml train config` | 训练任务自定义参数管理 | 命令分组/帮助 |
| `ml train history` | 训练任务执行记录查询 | 命令分组/帮助 |
| `ml train history logs` | 执行记录日志下载 | 命令分组/帮助 |
| `ml train instance` | 训练任务执行实例查询 | 命令分组/帮助 |
| `ml user` | 用户信息 | 命令分组/帮助 |
| `ml webstudio` | Web Studio 查询、启动、停止与 Jupyter 动态登录 | 命令分组/帮助 |
