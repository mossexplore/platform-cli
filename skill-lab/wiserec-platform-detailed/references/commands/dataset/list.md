# `ml dataset list`

分页查询当前业务的数据集。

## 使用前提

先核对 [共同规则](../../common.md) 中的环境、业务和认证要求。业务资源 ID 必须来自当前目标上下文。只读查询；不代表远端任务已经完成。

## 命令格式

```text
ml dataset list [OPTIONS]
```

全局选项放在子命令之前；`[OPTIONS]` 仅代表下表列出的选项，不是字面输入。

## 参数与选项

| 参数 / 别名 | 类型 | 必填 | 缺省值 | 约束与用途 |
| --- | --- | --- | --- | --- |
| `--page` | INTEGER RANGE | 否 | `1` | ≥1；CLI 未设置上限；页码 |
| `--page-size` | INTEGER RANGE | 否 | `10` | ≥1；CLI 未设置上限；每页条数 |
| `--name` / `--dataset-name` | TEXT | 否 | `""` | 数据集名称条件 |
| `--create-user` | TEXT | 否 | `""` | 创建者条件 |
| `--update-user` | TEXT | 否 | `""` | 修改者条件 |
| `--bucket-name` | TEXT | 否 | 未指定（None） | 存储桶条件 |
| `--output` / `-o` | TEXT | 否 | 未指定（None） | table 或 json；缺省读取当前环境 output_format |
| `--help` | 开关 | 否 | false | 显示本命令帮助并退出 |

参数表的 None 表示未指定，不应在命令行输入字面量 `None` 或 `null`。空字符串与缺省是否相同，以以下规则为准。

## 边界与组合规则

筛选值去除首尾空白；纯空白拒绝。name/create-user/update-user 缺省为空字符串；bucket-name 缺省 None，与显式空字符串不同。服务端页大小上限未确认。

- `--page`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝
- `--page-size`：≥1；CLI 未设置上限；范围端点按表中包含性判断，越界由解析器拒绝

## 响应与展示

`{total: integer, pageIndex: integer, pageSize: integer, items: object[]}`。分页值来自请求，total 为总数，空结果 items=[]；条目扩展字段保留。 `result.totalSize → total`，`result.data → items`。条目常用 dataSetId、dataSetName、businessId、fileSize、modifyTime、useTime；条目字段未作完整类型校验，可能缺失或为 null。表格转换时间和大小，JSON 保留原值。

仅将明确标注类型和存在条件的字段视为本地实现保证；展示字段清单不等于完整接口 schema。未约束字段的类型、可空性和服务端枚举待接口契约或脱敏实测确认。

### 展示字段定位

下表描述展示使用的字段；它不是必填字段 schema。除上文明确校验者外，内部字段类型/可空性未由客户端完整约束，缺失时按该命令展示逻辑处理。表格可能转换原值，不应反向重建 JSON。

| JSON 字段或展示输入 | 展示含义 |
| --- | --- |
| `items[].dataSetId` | 数据集 ID |
| `items[].dataSetName` | 数据集名称 |
| `items[].businessId` | 租户 |
| `items[].dataSetType` | 数据类型 |
| `items[].updateUser` | 修改者 |
| `items[].fileSize` | 大小 |
| `items[].modifyTime` | 更新时间 |
| `items[].useTime` | 最近使用 |
| `items[].region` | 区域 |
| `items[].bucketName` | 存储桶 |
| `items[].description` | 描述 |


## 错误与核验

参数解析错误通常退出 2，命令捕获的业务/配置/响应错误通常退出 1；本页另有退出码说明时优先按该说明。检查退出码与 stderr，不能仅凭 stdout 有 JSON 或成功提示断定全部操作成功。认证提示和历史记录等全局行为见共同规则。

只读查询；不代表远端任务已经完成。有副作用的操作在超时或失联后先查询状态；不把不确定结果当作未执行。

## 示例

以下为语法示例，替换资源与路径占位符后使用；写操作须先确认目标及用户授权，不作为自动执行清单。

```text
ml dataset list --page 1 --page-size 10 --name "DATASET_NAME" -o json
```

边界验收：分别检查表中最小值、最大值（如有）及刚越界值；整数用 ±1，浮点用临近值。验证解析边界时使用 mock，不发送真实业务写请求。

### 响应示例

以下是依据本地输出逻辑构造的结构示例，非线上抓包；仅展示此情形，其他字段可能省略，不能据此认定完整响应。

```json
{
  "total": 0,
  "pageIndex": 1,
  "pageSize": 10,
  "items": []
}
```

## 证据与未确认项

已核对命令定义和以下仓库实现；未进行真实平台联调。路径用于维护追溯，不要求使用者访问源码。

- `src/wiserec_cli/commands/dataset.py`
- `src/wiserec_cli/services/dataset.py`

命令入口函数 `list_datasets`，记录时起始行 133。服务端额外字段、权限差异和未显式校验的长度/数量限制不作推断。
