# `ml jupyter exec`

独立 Python Kernel 启动 POSIX 子进程，收集结果后释放 Kernel；不重试。

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。新建专用 Kernel 并执行远端程序，结束尝试清理；不自动重试；remote_state=unknown 时先核验状态。

## 命令格式

```text
ml jupyter exec [OPTIONS] -- PROGRAM [ARG...]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `command` | TEXT | 是 | 无，必填 | 一个或多个值；-- 后的程序及参数；不隐式使用 Shell |
| `--cwd` | TEXT | 否 | `""` | 远端已有目录，相对 Jupyter 根目录 |
| `--timeout` | FLOAT RANGE | 否 | `60` | ≥0.1；CLI 未设置上限 |
| `--startup-timeout` | FLOAT RANGE | 否 | `60` | ≥0.1；CLI 未设置上限 |
| `--max-output` | INTEGER RANGE | 否 | `1048576` | ≥1；≤10485760；stdout/stderr 各自保留的最大字节数 |
| `--kernel` | TEXT | 否 | 未指定（None） | 远端 Python Kernel 名称 |
| `--output` / `-o` | TEXT | 否 | `"text"` | 无额外解析器约束；业务规则见下文 |
| `--studio-id` | TEXT | 否 | 未指定（None） | 无额外解析器约束；业务规则见下文 |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

必须 -- 后传程序和参数，不隐式执行 shell；需要远端 POSIX 与 Python Kernel，cwd 已存在。stdout/stderr 各自最多 max-output 字节，截断不等于程序失败。SUCCEEDED→0，TIMED_OUT→124，INTERRUPTED→130，LOST→2；FAILED 时子进程退出码 1..123 透传，其他失败→1。

- `--timeout`：≥0.1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--startup-timeout`：≥0.1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--max-output`：≥1；≤10485760；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

JSON 包装 `{server_url:string, studio_id:string（direct 模式为空字符串）, business_id:string, result:...}`；text 通常只缩进打印 result。created/last_modified 字段递归转换为北京时间字符串；其他扩展字段保留。 result 含 id:string、status:string、exit_code:integer|null、stdout/stderr:string、cwd:string、cleanup_errors:string[]、remote_state:not_started/unknown/finished；kernel_id/error 为条件字符串，truncated/output_incomplete 为条件 boolean，termination 为条件字符串。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

新建专用 Kernel 并执行远端程序，结束尝试清理；不自动重试；remote_state=unknown 时先核验状态。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

操作建立前失败可能输出 `{ "status": "FAILED", "error": "错误说明" }` 并退出 1，不含 result 包装；成功建立连接后的执行失败则按 result.status 判读。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml jupyter exec --timeout 60 -o json -- python -c "print(1)"
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "server_url": "https://jupyter.example.invalid/",
  "studio_id": "ENV_ID",
  "business_id": "BUSINESS_ID",
  "result": {
    "id": "EXECUTION_ID",
    "status": "LOST",
    "exit_code": null,
    "stdout": "",
    "stderr": "",
    "cwd": "",
    "cleanup_errors": [],
    "remote_state": "unknown",
    "error": "执行通道提前结束"
  }
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/jupyter_exec.py`
- `src/wiserec_cli/jupyter/execution.py`
- `src/wiserec_cli/jupyter/exec_worker.py`

命令入口函数 `exec_command`，记录时起始行 10。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
