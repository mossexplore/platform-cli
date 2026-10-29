# `ml service mock`

使用样例报文测试服务响应

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。实际调用服务，不保证幂等；不自动重试认证；核对每个节点 retCode。

## 命令格式

```text
ml service mock SERVICE_ID [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `service_id` | TEXT | 是 | 无，必填 | 服务 ID |
| `--transmission-tag` | INTEGER RANGE | 否 | `0` | ≥0；≤1；0 不调用透传接口，1 调用透传接口 |
| `--request-sample-file` | FILE | 否 | 未指定（None） | 路径须存在；不允许目录；检查可读；样例报文文件，UTF-8 编码且支持 BOM；默认使用服务文档样例 |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

transmission-tag 只允许 0/1；文件为 UTF-8（可带 BOM）合法 JSON 样例；不提供文件则使用服务文档样例。host mock 要求非空 pod-ip 并唯一定位主机。空节点列表也判失败。

- `--transmission-tag`：≥0；≤1；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

输出平台原始 JSON，未重组业务字段；服务端扩展字段可能继续增加。 result.nodeList 为节点数组；每个节点保留 hostName/scope/domain/retCode/cost 等字段，mockResponseRaw 保存原报文，mockResponse 尝试解析成任意合法 JSON 值。节点失败或报文解析失败仍输出诊断结果，然后退出 1。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

实际调用服务，不保证幂等；不自动重试认证；核对每个节点 retCode。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml service mock SERVICE_ID -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "result": {
    "code": 0,
    "nodeList": [
      {
        "hostName": "HOST_NAME",
        "retCode": 0,
        "mockResponseRaw": "{\"ok\":true}",
        "mockResponse": {
          "ok": true
        },
        "cost": 5
      }
    ]
  }
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/service_mock.py`
- `src/wiserec_cli/services/service_mock.py`

命令入口函数 `service_mock`，记录时起始行 109。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
