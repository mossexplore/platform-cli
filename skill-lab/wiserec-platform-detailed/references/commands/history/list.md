# `ml history list`

查询历史执行记录

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。本地只读；历史只证明本地调用记录，不能替代远端核验。

## 命令格式

```text
ml history list [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `--limit` | INTEGER RANGE | 否 | 未指定（None） | ≥1；≤1000；最多显示条数；非交互默认 20 |
| `--search` | TEXT | 否 | `""` | 命令内容关键字 |
| `--env` | TEXT | 否 | 未指定（None） | 执行前的环境 |
| `--status` | TEXT | 否 | 未指定（None） | success、failed 或 interrupted |
| `--output` / `-o` | TEXT | 否 | `"table"` | table 或 json |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

status 仅 success/failed/interrupted；limit=1..1000。JSON 或非交互缺省最近 20 条；交互表格缺省可浏览全部。search 大小写不敏感；env 匹配执行前环境。

- `--limit`：≥1；≤1000；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

JSON 顶层 object[]。记录包含 time:string、started_at/finished_at:number（秒时间戳）、duration_ms:integer、command:string、env/env_after/business_id:可空上下文值、config/cwd/version:string、exit_code:integer、status:string、redacted/truncated:boolean。空结果 []。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

本地只读；历史只证明本地调用记录，不能替代远端核验。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml history list -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
[]
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/history.py`
- `src/wiserec_cli/history_recording.py`

命令入口函数 `list_history`，记录时起始行 109。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
