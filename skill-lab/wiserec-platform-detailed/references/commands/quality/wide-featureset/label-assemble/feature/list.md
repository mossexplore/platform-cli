# `ml quality wide-featureset label-assemble feature list`

标签装配样本定义下的特征分页查询

## 使用前提

遵守 [共同规则](../../../../../common.md)，先选环境、登录并选择业务。先定位质量监控宽表特征集，再从对应装配列表取得样本定义 ID；特征集 ID、样本定义 ID 与特征 ID 不互换。只读查询，无远端写操作，不需要确认。

## 命令格式

```text
ml quality wide-featureset label-assemble feature list [OPTIONS]
```

## 参数与选项

| 参数 / 别名 | 默认值 | 说明 |
| --- | --- | --- |
| `--set-id` | 必填 | 宽表特征集 ID，不可为空白 |
| `--definition-id` | 必填 | 对应装配样本定义 ID，不可为空白 |
| `--page` | 1 | 正整数 |
| `--page-size` | 10 | 1～100 的整数，每次只取一页 |
| `--output` / `-o` | 当前环境配置 | table 或 json |
| `--help` | 关闭 | 显示帮助 |

## 边界与响应

JSON 为 {items: object[], count: integer, pageIndex: integer, pageSize: integer}；count 来自 totalCount。分页优先用响应值，缺失时用请求值。表格列为特征ID、特征名、特征类型、特征值类型、标签装配最新周期、空值率。类型原样显示，周期保持原编码。

记录全部原始字段和值在 JSON 中保留，不将表格列视为完整 schema。表格比例乘以 100 后按整数四舍五入，0.1538 为 15%、0.017 为 2%、0.125 为 13%、0 为 0%。此规则不改变原有质量监控特征列表的小数百分比规则。缺失、null 和空字符串显示 -。首列 ID 固定宽度 36，完整不截断，其他长字段换行。

## 错误与核验

必填 ID 缺失或空白、分页越界、输出格式错误在调用接口前失败。当前环境业务缺失或不一致、权限拒绝、HTTP 失败、result.code 非零或必要列表结构无效时返回非零退出码。先检查退出码再解析 JSON，诊断在标准错误中。空数组正常退出并提示暂无记录。

## 示例

```text
ml quality wide-featureset label-assemble feature list --set-id SET_ID --definition-id DEFINITION_ID --page 2 --page-size 100 -o json
```

## 证据

源码审阅与 MockTransport 契约测试，未进行真实平台联调。命令分组确定装配类型，无 --type 参数。
