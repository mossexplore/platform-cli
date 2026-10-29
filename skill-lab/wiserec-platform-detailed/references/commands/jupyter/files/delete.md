# `ml jupyter files delete`

显式删除文件或空目录，不递归、不交互确认。

## 使用前提

先核对 [共同规则](../../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。删除远端文件/空目录；先确认用户具体目标，再调用 stat/list 核验。

## 命令格式

```text
ml jupyter files delete PATH [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `path` | TEXT | 是 | 无，必填 | 无额外解析器约束；业务规则见下文 |
| `--output` / `-o` | TEXT | 否 | `"text"` | 无额外解析器约束；业务规则见下文 |
| `--studio-id` | TEXT | 否 | 未指定（None） | 无额外解析器约束；业务规则见下文 |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

远端路径相对 Jupyter 根目录，拒绝前导 /、反斜杠、NUL 和 .. 段；. 和重复分隔符会归一化。写目标不可为根目录。 仅删除文件或空目录，无递归、无 --yes、无交互确认。

## 响应与展示

JSON 包装 `{server_url:string, studio_id:string（direct 模式为空字符串）, business_id:string, result:...}`；text 通常只缩进打印 result。created/last_modified 字段递归转换为北京时间字符串；其他扩展字段保留。 result=`{path:string, deleted:true}`。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

operation 内部失败且选择 JSON 时，stdout 为 `{ "status": "FAILED", "error": "错误说明" }`，退出 1；错误对象没有 server_url/result 包装。解析器失败可能只输出错误文本，不保证 JSON。

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

删除远端文件/空目录；先确认用户具体目标，再调用 stat/list 核验。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml jupyter files delete PATH -o json
```

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "server_url": "https://jupyter.example.invalid/",
  "studio_id": "ENV_ID",
  "business_id": "BUSINESS_ID",
  "result": {
    "path": "notes.txt",
    "deleted": true
  }
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/jupyter_files.py`
- `src/wiserec_cli/jupyter/files.py`

命令入口函数 `delete`，记录时起始行 153。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
