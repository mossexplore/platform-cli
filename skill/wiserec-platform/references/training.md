# 训练任务、离线实验、算法仓与训练看板

以下命令的列表和查询均支持 `-o json`，具体筛选和分页参数查 `--help`。

## 训练看板（MTP Swanboard）

按“项目 → 项目空间 → 实验 → 实验数据”逐级定位：

```powershell
ml mtp swanboard project list -o json
ml mtp swanboard project namespace list PROJECT_ID -o json
ml mtp swanboard project experiment list PROJECT_ID NAMESPACE_ID -o json
ml mtp swanboard experiment metrics EXPERIMENT_ID --tag loss --tag accuracy -o json
```

- 项目 ID、空间 ID 和实验 ID 不互换。`--team-id` 只筛选结果，不切换当前业务。
- `metrics` 返回统计值，不是完整时间序列；`--tag` 可重复。
- `inspect` 会发起多次请求，其中特性只含第一页；只需单项信息时直接用对应子命令。

## 离线实验

```powershell
ml offline experiment list --name NAME -o json
ml offline experiment trial list PROJECT_ID -o json
ml offline experiment clone PROJECT_ID --name NEW_NAME --dry-run -o json
ml offline experiment clone PROJECT_ID --name NEW_NAME --yes -o json
```

克隆前先用 `--dry-run` 核对源实验和新名称；用户授权后再加 `--yes` 提交。结果不明时先按新名称查询，不重复提交。

## 训练任务

```powershell
ml train list --name NAME -o json
ml train history list TASK_ID -o json
ml train history logs download TASK_ID JOB_ID --file 'D:\logs\job.log' -o json
```

- `instance list` 和 `history list` 只返回第一页 10 条，不能当作完整记录。`history list` 中的 `jobId` 用于下载日志。
- `ml train start TASK_ID` 返回 `jobId` 只表示请求已被接受，之后用 `history list` 确认状态。
- `cancel`、`delete`、`clone` 默认询问确认，授权后加 `--yes`。`cancel` 逐个取消全部执行实例，需看逐条结果和退出码，没有实例时退出 1。`clone` 成功后可能返回新任务 ID。
- `ml train config update TASK_ID --customize-config VALUE` 不询问确认，直接修改任务；值按字符串原样传递，含双引号时注意 [session.md](session.md) 的引号说明，更新后导出配置核对。
- `config export` 和 `history logs download` 写入本地文件，父目录必须已存在，不覆盖同名文件。

## 算法仓

```powershell
ml algorithm list --name NAME -o json
ml algorithm download ALGORITHM_ID --file 'D:\download\algo.zip'
ml algorithm clone ALGORITHM_ID --name NEW_NAME --version VERSION --yes
```

- 下载先获取签名链接再保存 ZIP；父目录必须已存在，不覆盖同名文件。不要把签名链接写入回复或日志。
- 克隆默认询问确认，授权后加 `--yes`；结果不明时先按新名称和版本查询，再决定是否重试。

## 结果核验

写请求超时或连接中断时，先查询目标任务、实例或资源的实际状态，再决定是否重试。分页字段和响应字段以实际返回为准，文档中的示例不代表完整响应。
