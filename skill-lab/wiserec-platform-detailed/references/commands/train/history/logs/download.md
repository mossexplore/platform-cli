# `ml train history logs download`

获取日志地址并下载；发送 isApplicantPromise=true，不覆盖已有文件。

## 使用前提

先核对 [共同规则](../../../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。写入本地日志文件；核验路径和字节数。

## 命令格式

```text
ml train history logs download TASK_ID JOB_ID [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `task_id` | TEXT | 是 | 无，必填 | 所属训练任务 ID |
| `job_id` | TEXT | 是 | 无，必填 | 执行记录 ID |
| `--file` | PATH | 否 | 未指定（None） | 检查可读；本地保存路径，目录须已存在 |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | 结果摘要格式: table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

TASK_ID 与 JOB_ID 分别为任务和执行记录 ID；父目录须存在，不覆盖已有文件；CLI 会显示下载地址，分享前剔除签名参数。

## 响应与展示

`{taskId: string, jobId: string, path: string, bytes: integer, status: "downloaded"}`，表示本地下载完成；不是日志正文 JSON。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

写入本地日志文件；核验路径和字节数。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml train history logs download TASK_ID JOB_ID -o json
```

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "taskId": "TASK_ID",
  "jobId": "JOB_ID",
  "path": "LOCAL_LOG_FILE",
  "bytes": 128,
  "status": "downloaded"
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/train.py`
- `src/wiserec_cli/services/train.py`
- `src/wiserec_cli/downloads.py`

命令入口函数 `download_logs`，记录时起始行 322。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
