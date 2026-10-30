# 命令索引

共 98 个叶子命令。全局选项及命令组入口见 [全局与命令组](global.md)。

| 命令 | 用途 | 详解 |
| --- | --- | --- |
| `ml access status` | 实时检查当前平台账号及环境的访问授权。 | [详情](commands/access/status.md) |
| `ml algorithm clone` | 按指定名称和版本克隆算法仓。 | [详情](commands/algorithm/clone.md) |
| `ml algorithm download` | 获取下载地址并保存算法仓文件。 | [详情](commands/algorithm/download.md) |
| `ml algorithm list` | 分页查询当前业务的算法仓。 | [详情](commands/algorithm/list.md) |
| `ml auth ping start` | 为当前终端启动自动保活。 | [详情](commands/auth/ping/start.md) |
| `ml auth ping status` | 只读查看自动保活状态。 | [详情](commands/auth/ping/status.md) |
| `ml auth ping stop` | 停止当前环境的自动保活。 | [详情](commands/auth/ping/stop.md) |
| `ml auth status` | 显示当前环境的认证有效期，不显示敏感值。 | [详情](commands/auth/status.md) |
| `ml business list` | 显示当前环境可见的部门、租户和团队目录。 | [详情](commands/business/list.md) |
| `ml business refresh` | 打开 Edge 刷新当前环境的业务目录。 | [详情](commands/business/refresh.md) |
| `ml business show` | 显示当前租户或团队上下文。 | [详情](commands/business/show.md) |
| `ml business use` | 交互式或通过 ID 选择租户/团队。 | [详情](commands/business/use.md) |
| `ml context` | 查看当前运行模式及生效配置路径 | [详情](commands/context.md) |
| `ml dataset detail` | 查询指定数据集的详情。 | [详情](commands/dataset/detail.md) |
| `ml dataset files list` | 查看指定目录内容 | [详情](commands/dataset/files/list.md) |
| `ml dataset files upload` | 向指定目录追加文件 | [详情](commands/dataset/files/upload.md) |
| `ml dataset list` | 分页查询当前业务的数据集。 | [详情](commands/dataset/list.md) |
| `ml deployment template detail` | 查询部署模板详情 | [详情](commands/deployment/template/detail.md) |
| `ml deployment template list` | 查询部署模板列表 | [详情](commands/deployment/template/list.md) |
| `ml env list` | 列出全部环境。 | [详情](commands/env/list.md) |
| `ml env show` | 显示当前环境。 | [详情](commands/env/show.md) |
| `ml env use` | 切换当前环境。 | [详情](commands/env/use.md) |
| `ml feature-task execution list` | 分页查询特征任务的执行记录 | [详情](commands/feature-task/execution/list.md) |
| `ml feature-task execution logs search` | 查询和搜索训练日志 | [详情](commands/feature-task/execution/logs/search.md) |
| `ml feature-task list` | 分页查询当前业务下的特征任务 | [详情](commands/feature-task/list.md) |
| `ml featureset model config` | 查询特征集配置，固定输出解析后的 JSON 对象。 | [详情](commands/featureset/model/config.md) |
| `ml featureset model export` | 导出特征集中的特征为 CSV 文件 | [详情](commands/featureset/model/export.md) |
| `ml featureset model list` | 分页查询当前业务下的特征集。 | [详情](commands/featureset/model/list.md) |
| `ml featureset wide config` | 查询特征集配置，固定输出解析后的 JSON 对象。 | [详情](commands/featureset/wide/config.md) |
| `ml featureset wide export` | 导出特征集中的特征为 CSV 文件 | [详情](commands/featureset/wide/export.md) |
| `ml featureset wide list` | 分页查询当前业务下的特征集。 | [详情](commands/featureset/wide/list.md) |
| `ml history clear` | 清理历史记录 | [详情](commands/history/clear.md) |
| `ml history list` | 查询历史执行记录 | [详情](commands/history/list.md) |
| `ml jupyter doctor` | 验证 Token、业务上下文、Kernel 与终端管理接口（不创建资源）。 | [详情](commands/jupyter/doctor.md) |
| `ml jupyter exec` | 独立 Python Kernel 启动 POSIX 子进程，收集结果后释放 Kernel；不重试。 | [详情](commands/jupyter/exec.md) |
| `ml jupyter files copy` | 复制单文件至已有目录；新文件名由 Jupyter 决定。 | [详情](commands/jupyter/files/copy.md) |
| `ml jupyter files delete` | 显式删除文件或空目录，不递归、不交互确认。 | [详情](commands/jupyter/files/delete.md) |
| `ml jupyter files download` | 下载单文件，LOCAL 必须含目标文件名，父目录必须存在。 | [详情](commands/jupyter/files/download.md) |
| `ml jupyter files list` | 列出目录的一层内容。 | [详情](commands/jupyter/files/list.md) |
| `ml jupyter files mkdir` | 创建一个目录，父目录必须存在。 | [详情](commands/jupyter/files/mkdir.md) |
| `ml jupyter files move` | 移动或重命名，不覆盖目标。 | [详情](commands/jupyter/files/move.md) |
| `ml jupyter files read` | 读取 UTF-8 文本；行范围含首尾，底层下载完整文件。 | [详情](commands/jupyter/files/read.md) |
| `ml jupyter files stat` | 查询类型、大小、时间和可写性，不下载内容。 | [详情](commands/jupyter/files/stat.md) |
| `ml jupyter files upload` | 上传单文件（含二进制），REMOTE 必须含目标文件名。 | [详情](commands/jupyter/files/upload.md) |
| `ml jupyter files write` | 从本地 UTF-8 文件或标准输入写入远端文件。 | [详情](commands/jupyter/files/write.md) |
| `ml jupyter notebook run` | 上传并按顺序执行 Notebook；失败也保存部分结果，不自动重试。 | [详情](commands/jupyter/notebook/run.md) |
| `ml jupyter terminal attach` | 连接已有终端，不保证补取完整历史输出。 | [详情](commands/jupyter/terminal/attach.md) |
| `ml jupyter terminal close` | 关闭指定远程终端及其 Shell，会影响在其中运行的进程。 | [详情](commands/jupyter/terminal/close.md) |
| `ml jupyter terminal list` | 列出当前 Jupyter 身份可见的终端。 | [详情](commands/jupyter/terminal/list.md) |
| `ml jupyter terminal open` | 创建终端并连接，Ctrl+] 仅断开本地连接。 | [详情](commands/jupyter/terminal/open.md) |
| `ml login` | 打开 Edge 登录并刷新当前环境的本地认证信息。 | [详情](commands/login.md) |
| `ml logout` | 清除当前环境的本地认证信息。 | [详情](commands/logout.md) |
| `ml mep config get` | 查询一个 MEP 配置项。 | [详情](commands/mep/config/get.md) |
| `ml model deploy` | 使用部署模板将模型部署为服务 | [详情](commands/model/deploy.md) |
| `ml model detail` | 查询模型详情 | [详情](commands/model/detail.md) |
| `ml model list` | 查询当前业务的模型列表 | [详情](commands/model/list.md) |
| `ml model source` | 查询模型溯源或关联训练任务信息 | [详情](commands/model/source.md) |
| `ml mtp swanboard experiment config list` | 查询实验配置。 | [详情](commands/mtp/swanboard/experiment/config/list.md) |
| `ml mtp swanboard experiment environment get` | 查询实验环境。 | [详情](commands/mtp/swanboard/experiment/environment/get.md) |
| `ml mtp swanboard experiment feature list` | 查询实验特性。 | [详情](commands/mtp/swanboard/experiment/feature/list.md) |
| `ml mtp swanboard experiment inspect` | 一次性查询实验的特性、环境、指标和配置。 | [详情](commands/mtp/swanboard/experiment/inspect.md) |
| `ml mtp swanboard experiment metrics` | 查询实验指标统计，默认查询 loss 和 accuracy。 | [详情](commands/mtp/swanboard/experiment/metrics.md) |
| `ml mtp swanboard project experiment list` | 查询项目空间下的全部实验。 | [详情](commands/mtp/swanboard/project/experiment/list.md) |
| `ml mtp swanboard project list` | 分页查询训练看板项目。 | [详情](commands/mtp/swanboard/project/list.md) |
| `ml mtp swanboard project namespace list` | 查询训练看板项目下的全部项目空间。 | [详情](commands/mtp/swanboard/project/namespace/list.md) |
| `ml offline experiment clone` | 查询源实验详情并同步克隆，仅修改实验名称。 | [详情](commands/offline/experiment/clone.md) |
| `ml offline experiment list` | 分页查询离线实验。 | [详情](commands/offline/experiment/list.md) |
| `ml offline experiment trial list` | 分页查询某个离线实验下的 trial。 | [详情](commands/offline/experiment/trial/list.md) |
| `ml resource template detail` | 查询资源模板详情 | [详情](commands/resource/template/detail.md) |
| `ml resource template list` | 查询资源模板列表 | [详情](commands/resource/template/list.md) |
| `ml sample-task execution list` | 分页查询新版样本任务的执行记录 | [详情](commands/sample-task/execution/list.md) |
| `ml sample-task list` | 分页查询样本任务，默认使用旧任务管理 | [详情](commands/sample-task/list.md) |
| `ml sample-task period list` | 分页查询新版样本任务的执行周期 | [详情](commands/sample-task/period/list.md) |
| `ml service deployment list` | 查询指定服务的部署视图。 | [详情](commands/service/deployment/list.md) |
| `ml service host list` | 查询指定服务的主机视图。 | [详情](commands/service/host/list.md) |
| `ml service host mock` | 使用样例报文测试指定主机 | [详情](commands/service/host/mock.md) |
| `ml service list` | 分页查询当前业务的服务。 | [详情](commands/service/list.md) |
| `ml service logs` | 选择服务主机和文件并查看日志 | [详情](commands/service/logs.md) |
| `ml service mock` | 使用样例报文测试服务响应 | [详情](commands/service/mock.md) |
| `ml train cancel` | 查询所有执行实例并逐个取消。 | [详情](commands/train/cancel.md) |
| `ml train clone` | 读取完整训练任务详情并创建副本。 | [详情](commands/train/clone.md) |
| `ml train config export` | 导出并下载训练任务的 YAML 配置。 | [详情](commands/train/config/export.md) |
| `ml train config update` | 获取训练任务详情，保留完整 taskInfo 后更新自定义参数。 | [详情](commands/train/config/update.md) |
| `ml train delete` | 软删除当前业务下的训练任务。 | [详情](commands/train/delete.md) |
| `ml train history list` | 直接查询执行记录；固定第 1 页 10 条，开始时间倒序。 | [详情](commands/train/history/list.md) |
| `ml train history logs download` | 获取日志地址并下载；发送 isApplicantPromise=true，不覆盖已有文件。 | [详情](commands/train/history/logs/download.md) |
| `ml train instance list` | 查找训练任务并查询执行实例；固定第 1 页 10 条，开始时间升序。 | [详情](commands/train/instance/list.md) |
| `ml train list` | 分页查询当前业务下的训练任务。 | [详情](commands/train/list.md) |
| `ml train start` | 立即执行指定训练任务，返回作业 ID；不预先查询任务列表。 | [详情](commands/train/start.md) |
| `ml tree` | 显示当前安装版本的完整命令树。 | [详情](commands/tree.md) |
| `ml user info` | 查询当前登录用户信息。 | [详情](commands/user/info.md) |
| `ml webstudio list` | 当前业务的实例列表；name 模糊匹配，其余条件精确匹配。 | [详情](commands/webstudio/list.md) |
| `ml webstudio login` | 重新建立并验证 Jupyter 连接，保存默认实例与短期会话缓存。 | [详情](commands/webstudio/login.md) |
| `ml webstudio show` | 显示当前环境、账号与业务绑定的选择（不代表实例实时状态）。 | [详情](commands/webstudio/show.md) |
| `ml webstudio start` | 启动指定 Web Studio；接口可能需要约 15 秒才返回。 | [详情](commands/webstudio/start.md) |
| `ml webstudio stop` | 停止指定 Web Studio。 | [详情](commands/webstudio/stop.md) |
| `ml quality feature list` | 特征质量分页查询 | [详情](commands/quality/feature/list.md) |
| `ml quality wide-featureset list` | 宽表特征集质量分页查询 | [详情](commands/quality/wide-featureset/list.md) |
