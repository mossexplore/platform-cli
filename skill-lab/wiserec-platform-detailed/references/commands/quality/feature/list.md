# `ml quality feature list`

质量监控报告的只读分页查询

## 使用前提

遵守 [共同规则](../../../common.md)，先选环境、登录并通过 ml business use 选择业务。当前环境的 selected.businessId 必须有效且与业务上下文一致。

## 命令格式

```text
ml quality feature list [OPTIONS]
```

## 参数与选项

| 参数 / 别名 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | 空字符串 | 特征名称 |
| `--table-name` | 空字符串 | 特征表名 |
| `--feature-value-type` | 不传 | 特征值类型 |
| `--indicator-type` | 不传 | 指标类型 |
| `--page` | 1 | 正整数页码 |
| `--page-size` | 10 | 1～100 的整数，每次仅查一页 |
| `--output` / `-o` | 当前环境配置 | table 或 json |
| `--help` | 关闭 | 显示帮助 |

## 边界与响应

JSON 为 {items: object[], count: integer, pageIndex: integer, pageSize: integer}。count 来自 totalCount。分页采用响应值，缺失时采用请求值；条目完整保留全部原始字段和值。表格转换不影响 JSON。首列 ID 固定宽度 36，完整不截断，长字段换行；缺失、null 和空字符串显示 -，数值 0 保留。

表格依次展示 featureId、featureName、featTableName、featureType、featureValueType、indicatorType、creator、latestCycleTime、freshnessValue、nullValueRate。两个类型字段翻译为中文，未知枚举保留原值。latestCycleTime 保留周期原值，freshnessValue 不拼接单位，nullValueRate 乘以 100 后显示百分号，零为 0%。两个类型筛选均接受连续/CONTINUOUS、离散/DISCRETE、有序/ORDINAL、分类/CATEGORICAL、序列/SEQUENCE、长序列/LONG_SEQUENCE、向量/VECTOR，英文忽略大小写；两者独立且默认省略。

## 错误与核验

参数越界或枚举不合法时不调用接口。缺少业务、业务不一致、HTTP 失败、result.code 非零或必要分页结构无效时返回非零退出码。先检查退出码，再解析标准输出 JSON；诊断信息在标准错误中。空列表正常返回并显示对应暂无记录提示，不等于查询了全部数据。

## 示例

```text
ml quality feature list --name NAME --page 2 --page-size 20 -o json
```

## 证据

源码审阅与 MockTransport 契约测试，未进行真实平台联调。展示字段不等于完整响应 schema。
