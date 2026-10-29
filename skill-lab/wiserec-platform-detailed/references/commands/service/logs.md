# `ml service logs`

选择服务主机和文件并查看日志

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读日志查询。

## 命令格式

```text
ml service logs SERVICE_ID [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `service_id` | TEXT | 是 | 无，必填 | 服务 ID |
| `--pod` | TEXT | 否 | 未指定（None） | Pod 名称 |
| `--cluster-name` | TEXT | 否 | 未指定（None） | 集群名称，必须与 --pod 同时提供 |
| `--type` | TEXT | 否 | 未指定（None） | 日志类别 |
| `--file` | TEXT | 否 | 未指定（None） | 日志文件名称 |
| `--keyword` / `-k` | TEXT | 否 | 未指定（None） | 可重复传入；关键词，可重复 |
| `--lines` / `-n` | INTEGER RANGE | 否 | `200` | ≥1；CLI 未设置上限；查询行数 |
| `--list` | BOOLEAN | 否 | `false` | 开关，无需参数值；只显示日志文件列表 |
| `--no-input` | BOOLEAN | 否 | `false` | 开关，无需参数值；禁止交互选择 |
| `--search-order` | TEXT | 否 | `"tail"` | 检索顺序 |
| `--grep-scope` | TEXT | 否 | `"C"` | 关键词范围 |
| `--grep-line` | INTEGER RANGE | 否 | `0` | ≥0；CLI 未设置上限；关键词上下文行数 |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

--pod 与 --cluster-name 必须同时提供；--list 不能与显式 --file/--keyword/--lines/--search-order/--grep-scope/--grep-line 共用。Agent 加 --no-input；多候选时补齐目标而非选择第一项。infer-python 类别 run/interface/metrics/engine/ascend/mslite/alarm；rtc 类别 rtc/run/interface/dcs/metrics/gc/interface_manager/interface_extend/engine/monitor/catalina/dmq。keyword 不得纯空白。search-order/grep-scope 只校验非空，不能把常见值当完整服务端枚举。

- `--lines`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--grep-line`：≥0；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

无 JSON 开关；--list 输出日志文件表格（fileName/fileSize/updateTime）；否则原样输出正文，不额外补末尾换行。取消交互退出 130。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读日志查询。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml service logs SERVICE_ID --no-input --pod POD_NAME --cluster-name CLUSTER_NAME --type run --list
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/service_logs.py`
- `src/wiserec_cli/services/service.py`

命令入口函数 `service_logs`，记录时起始行 120。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
