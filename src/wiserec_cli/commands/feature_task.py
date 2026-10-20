"""特征任务命令与表格展示。"""
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, print_result, print_text
from ..services.feature_task import FeatureTaskService, TASK_TYPES
from .common import fail, runtime_from_context

feature_task_app = typer.Typer(no_args_is_help=True, help="特征任务")
COLUMNS = (
    ("任务 ID", "taskId"), ("任务名称", "taskName"), ("任务类型", "taskType"),
    ("业务场景", "scene"), ("状态", "jobStatus"), ("创建者", "createUser"),
    ("修改者", "updateUser"), ("更新时间", "updateTime"),
    ("大小", "fileSize"), ("描述", "description"),
)


def display_value(field, value):
    if value is None or value == "":
        return "-"
    if field == "taskType":
        return TASK_TYPES.get(str(value), str(value))
    if field == "updateTime":
        return datetime.fromtimestamp(value / 1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    if field == "fileSize":
        if value == 0:
            return "0B"
        divisor, suffix = (1024 ** 2, "M") if value < 1024 ** 3 else (1024 ** 3, "G")
        return f"{value / divisor:.2f}{suffix}"
    return str(value)


def render_page(result, output):
    if output == "json":
        print_result(result, output)
        return
    table = Table(show_header=True, header_style="bold cyan")
    for title, field in COLUMNS:
        if field == "taskId":
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in COLUMNS))
    console.print(table)
    if not result["items"]:
        print_text("暂无特征任务")
    print_text(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")


@feature_task_app.command("list")
def list_tasks(
    context: typer.Context,
    name: Optional[str] = typer.Option(None, "--name", help="按任务名称查询"),
    category: str = typer.Option("dpp-all", "--category", help="任务类型: " + "; ".join(f"{k}={v}" for k, v in TASK_TYPES.items())),
    create_user: Optional[str] = typer.Option(None, "--create-user", help="按创建者查询"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询当前业务下的特征任务"""
    try:
        if category not in TASK_TYPES:
            raise ValueError("category 仅支持: " + ", ".join(TASK_TYPES))
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {"table", "json"}:
            raise ValueError("output 仅支持 table 或 json")
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(
                lambda client: FeatureTaskService(client).list_tasks(page, page_size, name, category, create_user)
            )
        render_page(result, selected)
    except Exception as exc:
        fail(exc)
