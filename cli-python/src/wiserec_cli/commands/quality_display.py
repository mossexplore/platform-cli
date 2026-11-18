"""质量监控表格展示，JSON 保留原始记录。"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from rich.table import Table
from rich.text import Text

from .. import messages as msg
from ..output import console, print_result, print_text
from ..services.quality import TYPES

FEATURE_COLUMNS = (
    ("特征id", "featureId"), ("特征名", "featureName"), ("特征表名", "featTableName"),
    ("特征类型", "featureType"), ("特征值类型", "featureValueType"),
    ("指标类型", "indicatorType"), ("创建人", "creator"),
    ("特征产出时间", "latestCycleTime"), ("时效性", "freshnessValue"),
    ("空值率", "nullValueRate"),
)
WIDE_COLUMNS = (
    ("特征集id", "setId"), ("特征集名称", "setName"), ("版本", "version"),
    ("特征装配输出表名", "outTableName"), ("场景", "scene"),
    ("创建时间", "createTime"), ("更新时间", "updateTime"),
    ("创建人", "creator"), ("更新人", "modifier"),
)
BEIJING = timezone(timedelta(hours=8))


def display_value(field, value):
    if value is None or value == "":
        return "-"
    if field in {"featureValueType", "indicatorType"}:
        return TYPES.get(str(value), str(value))
    if field == "nullValueRate":
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError("非有限数值")
            text = format(number * 100, "f")
            return (text.rstrip("0").rstrip(".") if "." in text else text) + "%"
        except (InvalidOperation, ValueError):
            msg.warning(f"空值率无法解析，保留原值：{value}")
    if field in {"createTime", "updateTime"}:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is not None:
                return parsed.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError):
            msg.warning(f"{field} 无法解析，保留原值：{value}")
    return str(value)


def render_page(result, output, wide=False):
    if output == "json":
        print_result(result, output)
        return
    columns = WIDE_COLUMNS if wide else FEATURE_COLUMNS
    table = Table(show_header=True, header_style="bold cyan")
    for index, (title, _) in enumerate(columns):
        if index == 0:
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in columns))
    console.print(table)
    if not result["items"]:
        print_text("暂无宽表特征集质量记录" if wide else "暂无特征质量记录")
    print_text(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")
