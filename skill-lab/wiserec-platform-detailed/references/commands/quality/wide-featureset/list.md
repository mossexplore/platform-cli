# `ml quality wide-featureset list`

质量监控报告的只读分页查询

## 使用前提

遵守 [共同规则](../../../common.md)，先选环境、登录并通过 ml business use 选择业务。当前环境的 selected.businessId 必须有效且与业务上下文一致。

## 命令格式

```text
ml quality wide-featureset list [OPTIONS]
```

## 参数与选项

| 参数 / 别名 | 默认值 | 说明 |
| --- | --- | --- |
| `--name` | 空字符串 | 特征集名称 |
| `--page` | 1 | 正整数页码 |
| `--page-size` | 10 | 1～100 的整数，每次仅查一页 |
| `--output` / `-o` | 当前环境配置 | table 或 json |
| `--help` | 关闭 | 显示帮助 |

## 边界与响应

JSON 为 {items: object[], count: integer, pageIndex: integer, pageSize: integer}。count 来自 totalCount。分页采用响应值，缺失时采用请求值；条目完整保留全部原始字段和值。表格转换不影响 JSON。首列 ID 固定宽度 36，完整不截断，长字段换行；缺失、null 和空字符串显示 -，数值 0 保留。

表格依次展示 setId、setName、version、outTableName、scene、createTime、updateTime、creator、modifier。带时区时间转换为北京时间 YYYY-MM-DD HH:mm:ss，不带时区的已格式化时间保持原值。与 ml featureset wide list 的入口和列不同。

## 错误与核验

参数越界或枚举不合法时不调用接口。缺少业务、业务不一致、HTTP 失败、result.code 非零或必要分页结构无效时返回非零退出码。先检查退出码，再解析标准输出 JSON；诊断信息在标准错误中。空列表正常返回并显示对应暂无记录提示，不等于查询了全部数据。

## 示例

```text
ml quality wide-featureset list --name NAME --page 2 --page-size 20 -o json
```

## 证据

源码审阅与 MockTransport 契约测试，未进行真实平台联调。展示字段不等于完整响应 schema。
