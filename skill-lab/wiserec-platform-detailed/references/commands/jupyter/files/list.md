# `ml jupyter files list`

列出目录的一层内容。

## 使用前提

先核对 [共同规则](../../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读目录查询。

## 命令格式

```text
ml jupyter files list [PATH] [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `path` | TEXT | 否 | `""` | 无额外解析器约束；业务规则见下文 |
| `--output` / `-o` | TEXT | 否 | `"text"` | 无额外解析器约束；业务规则见下文 |
| `--studio-id` | TEXT | 否 | 未指定（None） | 无额外解析器约束；业务规则见下文 |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

远端路径相对 Jupyter 根目录，拒绝前导 /、反斜杠、NUL 和 .. 段；. 和重复分隔符会归一化。写目标不可为根目录。 PATH 缺省空字符串表示根目录；只列一层，目标必须目录。

## 响应与展示

JSON 包装 `{server_url:string, studio_id:string（direct 模式为空字符串）, business_id:string, result:...}`；text 通常只缩进打印 result。created/last_modified 字段递归转换为北京时间字符串；其他扩展字段保留。 result 为 Contents 对象：name/path/type 常用字符串字段，type=file/directory/notebook；content 依查询可为 null、字符串、子项数组或 Notebook 对象；format 可为 text/base64/json/null，size 可为数值或 null，writable 常为 boolean。以上为服务使用字段而非完整客户端强制 schema；服务可能添加字段。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

operation 内部失败且选择 JSON 时，stdout 为 `{ "status": "FAILED", "error": "错误说明" }`，退出 1；错误对象没有 server_url/result 包装。解析器失败可能只输出错误文本，不保证 JSON。

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读目录查询。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml jupyter files list -o json
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/jupyter_files.py`
- `src/wiserec_cli/jupyter/files.py`
- `src/wiserec_cli/jupyter/connection.py`

命令入口函数 `list_files`，记录时起始行 49。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
