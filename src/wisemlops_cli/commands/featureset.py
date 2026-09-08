"""特征集命令与表格展示。"""

import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, error_console, print_result
from ..services.featureset import FeatureSetService
from .common import fail, runtime_from_context


featureset_app = typer.Typer(no_args_is_help=True, help="特征集查询")
wide_app = typer.Typer(no_args_is_help=True, help="宽表特征集查询")
model_app = typer.Typer(no_args_is_help=True, help="模型特征集查询")
featureset_app.add_typer(wide_app, name="wide")
featureset_app.add_typer(model_app, name="model")

COLUMNS = (
    ("特征集 ID", "setId"), ("特征集名称", "setName"),
    ("特征集类型", "setType"), ("场景", "scene"),
    ("创建者", "creator"), ("创建时间", "createTime"),
    ("修改者", "modifier"), ("修改时间", "updateTime"),
)
DISPLAY_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def display_value(field: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if field in {"createTime", "updateTime"}:
        try:
            # Python 3.9 的 fromisoformat 不接受 Z，先转换为显式 UTC 偏移。
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                raise ValueError("时间缺少时区")
            return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError):
            error_console.print(f"提示：{field} 无法解析，保留原值：{value}", markup=False)
    return str(value)


def render_page(result: Dict[str, Any], output: str) -> None:
    if output == "json":
        print_result(result, output)
        return
    table = Table(show_header=True, header_style="bold cyan")
    for title, _ in COLUMNS:
        table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in COLUMNS))
    console.print(table)
    if not result["items"]:
        console.print("暂无特征集")
    console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")
    console.print("时间：Asia/Shanghai (UTC+08:00)")


@wide_app.command("list")
@model_app.command("list")
def list_sets(
    context: typer.Context,
    name: Optional[str] = typer.Option(None, "--name", help="按特征集名称查询"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """分页查询当前业务下的特征集。"""
    try:
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {"table", "json"}:
            raise ValueError("output 仅支持 table 或 json")
        set_type = context.parent.info_name
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(
                lambda client: FeatureSetService(client).list_sets(set_type, page, page_size, name)
            )
        render_page(result, selected)
    except Exception as exc:
        fail(exc)


@wide_app.command("config")
@model_app.command("config")
def get_config(
    context: typer.Context,
    set_id: str = typer.Argument(..., help="特征集 ID"),
) -> None:
    """查询特征集配置，固定输出解析后的 JSON 对象。"""
    try:
        set_id = set_id.strip()
        if not set_id:
            raise ValueError("特征集 ID 不能为空")
        runtime = runtime_from_context(context)
        with redirect_stdout(sys.stderr):
            config = runtime.authenticated_call(
                lambda client: FeatureSetService(client).get_config(set_id)
            )
        print_result(config, "json")
    except Exception as exc:
        fail(exc)
