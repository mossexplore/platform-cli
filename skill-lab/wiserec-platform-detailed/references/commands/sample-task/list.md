# `ml sample-task list`

分页查询样本任务，默认使用旧任务管理

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读查询；不代表远端任务已经完成。

## 命令格式

```text
ml sample-task list [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `--source` | TEXT | 否 | `"legacy"` | 任务来源: legacy 旧任务管理，new 新任务管理 |
| `--page` | INTEGER RANGE | 否 | `1` | ≥1；CLI 未设置上限；开始页码 |
| `--page-size` | INTEGER RANGE | 否 | `10` | ≥1；CLI 未设置上限；每页记录数 |
| `--name` | TEXT | 否 | 未指定（None） | 按任务名称查询 |
| `--creator` | TEXT | 否 | 未指定（None） | 按创建者查询 |
| `--updater` | TEXT | 否 | 未指定（None） | 按修改者查询 |
| `--type` | TEXT | 否 | 未指定（None） | 可重复传入；任务类型，可重复指定；旧版默认查询前四种类型。旧版: feature_preprocess_realtime=特征预处理(实时); feature_preprocess_offline=特征预处理(离线); feature_assemble=特征装配; label_assemble=标签装配; feature_monitor=样本监控; new_feature_assemble=新特征装配; spark_jar=spark_jar。新版: FEATURE_ASSEMBLE=特征装配任务; LABEL_ASSEMBLE=标签装配任务; FEATURE_SYNC=特征同步任务; FEATURE_IMPORT_OFFLINE=离线特征导入任务; FEATURE_IMPORT_REALTIME=实时特征导入任务; OFFLINE_FEATURE_SYNC=离线特征回流同步任务; FEATURE_PREPROCESS_OFFLINE=预处理任务; FEATURE_QUALITY_MONITOR=监控任务; OFFLINE_FEEDBACK=离线回流任务; REAL_TIME_FEEDBACK=实时回流任务; REALTIME_LABEL_CALC=实时标签计算任务; SAMPLE_GENERATION_OFFLINE=样本生成离线任务; SAMPLE_GENERATION_REALTIME=样本生成实时任务 |
| `--status` | TEXT | 否 | 未指定（None） | 仅旧版: all、stopped、started，默认 all |
| `--sort` | TEXT | 否 | 未指定（None） | 仅新版: desc，默认 desc |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | 输出格式: table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

source 仅 legacy/new。legacy 才支持 status=all/stopped/started；new 才支持 sort=desc。--type 可重复、去重，枚举依来源而异，详见参数表；legacy 缺省仅查询前四种类型，new 缺省不传类型过滤。

- `--page`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--page-size`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

`{source: string, page: integer, pageSize: integer, total: integer, items: object[]}`。legacy 从 result.taskInfos/count 提取；new 从 result.data.list/total 提取，并展平一层分组；记录对象保留额外字段。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读查询；不代表远端任务已经完成。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml sample-task list -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "source": "new",
  "page": 1,
  "pageSize": 10,
  "total": 0,
  "items": []
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/sample_task.py`
- `src/wiserec_cli/services/sample_task.py`

命令入口函数 `list_tasks`，记录时起始行 81。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
