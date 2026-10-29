# `ml jupyter notebook run`

上传并按顺序执行 Notebook；失败也保存部分结果，不自动重试。

## 使用前提

先核对 [共同规则](../../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。执行 Notebook 代码并创建远端目录及本地结果；清理专用 Kernel；不自动重试。

## 命令格式

```text
ml jupyter notebook run SOURCE [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `source` | FILE | 是 | 无，必填 | 路径须存在；不允许目录；检查可读 |
| `--download` | PATH | 否 | `"results"` | 检查可读；本地结果根目录，每次新建 UUID 子目录 |
| `--kernel` | TEXT | 否 | 未指定（None） | 覆盖当前环境 Kernel 名称 |
| `--cwd` | TEXT | 否 | `""` | 相对服务器根目录的工作目录；默认使用本次独立目录 |
| `--timeout` | FLOAT RANGE | 否 | `600` | ≥0.1；CLI 未设置上限；全部单元格执行时限（秒） |
| `--startup-timeout` | FLOAT RANGE | 否 | `60` | ≥0.1；CLI 未设置上限；Kernel 就绪等待（秒） |
| `--output` / `-o` | TEXT | 否 | `"text"` | text 或 json |
| `--studio-id` | TEXT | 否 | 未指定（None） | 无额外解析器约束；业务规则见下文 |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

输入必须现有可读 .ipynb 并通过 Notebook 校验；timeout 是全部代码单元执行总时限；startup-timeout 单独计算。cwd 相对服务器根目录，缺省在独立目录执行。失败也保存已取得的部分输出。退出码 SUCCEEDED=0、TIMED_OUT=124、INTERRUPTED=130、LOST=2、其他=1。

- `--timeout`：≥0.1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--startup-timeout`：≥0.1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

直接输出摘要 JSON，无 files/exec 包装：id/status/remote_directory/notebook/started_at/finished_at:string，completed_cells:integer，cleanup_errors:string[]；kernel_id/error 为条件字段；webstudio 模式额外 studio_id/server_url。本地 UUID 目录保存 executed.ipynb 和 summary.json。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

执行 Notebook 代码并创建远端目录及本地结果；清理专用 Kernel；不自动重试。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml jupyter notebook run SOURCE -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/jupyter.py`
- `src/wiserec_cli/jupyter/notebook.py`

命令入口函数 `run`，记录时起始行 76。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
