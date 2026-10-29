# `ml mtp swanboard experiment environment get`

查询实验环境。

## 使用前提

先核对 [共同规则](../../../../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读查询；不代表远端任务已经完成。

## 命令格式

```text
ml mtp swanboard experiment environment get EXPERIMENT_ID [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `experiment_id` | TEXT | 是 | 无，必填 | 实验 experimentId |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | 输出格式: table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

experimentId 非空；空环境是正常空结果，不能补造环境信息。

## 响应与展示

输出 result.data 对象；服务端返回空数组时转换为 {}。常用 python、cpu.brand、memory、requirements；内部字段类型未完整校验，requirements 可为列表或其他值。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读查询；不代表远端任务已经完成。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml mtp swanboard experiment environment get EXPERIMENT_ID -o json
```

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/mtp.py`
- `src/wiserec_cli/services/swanboard.py`

命令入口函数 `get_environment`，记录时起始行 192。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
