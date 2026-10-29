# `ml model deploy`

使用部署模板将模型部署为服务

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。提交会创建服务；先 --dry-run 核对，非交互提交必须 --yes；提交前重新校验业务身份，失败不自动重放，查询服务确认。

## 命令格式

```text
ml model deploy MODEL_ID --template TEMPLATE_ID [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `model_id` | TEXT | 是 | 无，必填 | 模型 ID |
| `--template` | TEXT | 是 | 无，必填 | 部署模板 ID |
| `--service-timeout` | INTEGER RANGE | 否 | 未指定（None） | ≥1；CLI 未设置上限；调用方最大容忍超时时间（ms），优先于模板 |
| `--execute-limit` | INTEGER RANGE | 否 | 未指定（None） | ≥0；CLI 未设置上限；单实例最大并发数，优先于模板 |
| `--qps` | INTEGER RANGE | 否 | 未指定（None） | ≥1；CLI 未设置上限；单实例最大 QPS，未指定时不提交该字段 |
| `--update-mode` | TEXT | 否 | `"rolling"` | rolling 或 in-place |
| `--health-check-mode` | TEXT | 否 | `"default"` | default、response-code 或 response-code-and-data |
| `--health-port` | INTEGER RANGE | 否 | `18090` | ≥1；≤65535；容器健康检查端口 |
| `--description` | TEXT | 否 | `""` | 服务文档描述 |
| `--request-file` | FILE | 否 | 未指定（None） | 路径须存在；不允许目录；检查可读；UTF-8 输入报文文件 |
| `--response-file` | FILE | 否 | 未指定（None） | 路径须存在；不允许目录；检查可读；UTF-8 输出报文文件 |
| `--dry-run` | BOOLEAN | 否 | `false` | 开关，无需参数值；查询并预览完整部署配置，不提交 |
| `--yes` | BOOLEAN | 否 | `false` | 开关，无需参数值；跳过提交确认 |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

模型和模板 ID 非空；service-timeout≥1 毫秒、execute-limit≥0、qps≥1；health-port 包含边界 1..65535。update-mode=rolling/in-place；health-check-mode=default/response-code/response-code-and-data。显式选项优先于模板，缺少必需部署参数报错；qps 缺省不提交。输入/输出报文文件为可读 UTF-8。dry-run 仍需查询平台，但不提交。

- `--service-timeout`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--execute-limit`：≥0；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--qps`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--health-port`：≥1；≤65535；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

dry-run JSON 是提交请求：`{version:string, meta:{uuid:string}, data:{modelInfo:object, serviceInfo:object, comptPkgs:object[], extendConfiguration:object, serviceBlocks:object[], serviceDocument:object}, eFlowInfo:object}`。正式提交 JSON 是原始响应，result.code 为业务结果，serviceId/des 可缺失；业务失败可先输出 JSON 再退出 1。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

提交会创建服务；先 --dry-run 核对，非交互提交必须 --yes；提交前重新校验业务身份，失败不自动重放，查询服务确认。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml model deploy MODEL_ID --template TEMPLATE_ID --yes -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "result": {
    "code": 0,
    "serviceId": "SERVICE_ID",
    "des": "已接受"
  }
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/model_deploy.py`
- `src/wiserec_cli/services/model_deploy.py`
- `src/wiserec_cli/services/deploy_payload.py`

命令入口函数 `deploy`，记录时起始行 42。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
