# `ml feature-task list`

分页查询当前业务下的特征任务

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读查询；不代表远端任务已经完成。

## 命令格式

```text
ml feature-task list [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `--name` | TEXT | 否 | 未指定（None） | 按任务名称查询 |
| `--category` | TEXT | 否 | `"dpp-all"` | 任务类型: dpp-all=全部; feature_preprocess_realtime=特征预处理(实时); train_fi=FI直连任务; data_sync=数据同步任务; data-preproc=数据预处理任务; feature_generate=特征生成任务; feature_evaluation=特征评估任务; feature_improve=特征加工任务; work_flow=特征工作流任务; feature-push=特征同步任务; train_spark=Spark训练任务; train_fi_sync_hdfs=FI直连同步HDFS任务; train_fi_data_monitor=FI直连数据监控任务; generate_samples=样本生成任务; sample-monitor=样本监控任务; online_storage=在线存储任务; streaming_feature=流特征任务 |
| `--create-user` | TEXT | 否 | 未指定（None） | 按创建者查询 |
| `--page` | INTEGER RANGE | 否 | `1` | ≥1；CLI 未设置上限；开始页码 |
| `--page-size` | INTEGER RANGE | 否 | `10` | ≥1；CLI 未设置上限；每页记录数 |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | 输出格式: table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

分页从 1 开始；代码未设置页大小上限，服务端上限待确认。 category 必须为参数帮助列出的类型，默认 dpp-all。

- `--page`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--page-size`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

`{count: integer, pageIndex: integer, pageSize: integer, items: object[]}`。分页值来自请求，count 为总数，空结果 items=[]；条目扩展字段保留。 常用 taskId、taskName、taskType、scene、jobStatus、createUser、updateUser、updateTime、fileSize、description；表格翻译任务类型、转换毫秒时间，JSON 原值。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

### 展示字段定位

下表描述展示使用的字段；它不是必填字段 schema。除上文明确校验者外，内部字段类型/可空性未由客户端完整约束，缺失时按该命令展示逻辑处理。表格可能转换原值，不应反向重建 JSON。

| JSON 字段或展示输入 | 展示含义 |
| --- | --- |
| `items[].taskId` | 任务 ID |
| `items[].taskName` | 任务名称 |
| `items[].taskType` | 任务类型 |
| `items[].scene` | 业务场景 |
| `items[].jobStatus` | 状态 |
| `items[].createUser` | 创建者 |
| `items[].updateUser` | 修改者 |
| `items[].updateTime` | 更新时间 |
| `items[].fileSize` | 大小 |
| `items[].description` | 描述 |


## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读查询；不代表远端任务已经完成。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml feature-task list -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "count": 0,
  "pageIndex": 1,
  "pageSize": 10,
  "items": []
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/feature_task.py`
- `src/wiserec_cli/services/feature_task.py`

命令入口函数 `list_tasks`，记录时起始行 60。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
