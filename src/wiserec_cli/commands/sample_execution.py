"""新版样本任务执行周期网格与执行记录表格。"""
import sys
from contextlib import redirect_stdout
from datetime import datetime
from typing import List, Optional

import typer
from rich import box
from rich.table import Table
from rich.text import Text

from ..output import console, print_result, print_text
from ..services.sample_execution import BEIJING, STATES, SampleExecutionService, validate_options
from .common import fail, runtime_from_context

period_app = typer.Typer(no_args_is_help=True, help="新版样本任务执行周期")
execution_app = typer.Typer(no_args_is_help=True, help="新版样本任务执行记录")
COLUMNS = (
    ("JOB ID", "jobId"), ("算法名称", "algorithmName"), ("状态", "status"),
    ("文件大小", "fileSize"), ("周期时间", "periodDate"), ("执行时长", "runningTime"),
    ("最新实例", "latestFlag"), ("检查时间", "checkTime"),
    ("开始时间", "createTime"), ("结束时间", "statusTime"),
)


def display_value(field, value):
    if value is None or value == "":
        return "-"
    if field == "status":
        return {"COMPLETED": "执行完成", "FAILED": "执行失败", "CANCELED": "取消"}.get(value, str(value))
    if field == "latestFlag":
        return "是" if value is True else "否" if value is False else str(value)
    if field == "runningTime":
        hours, minutes = divmod(value, 60)
        return f"{hours}h{minutes}min" if hours else f"{minutes}min"
    if field == "fileSize":
        for exponent, suffix in ((3, "G"), (2, "M"), (1, "K")):
            if value >= 1024 ** exponent:
                return f"{value / 1024 ** exponent:.2f}{suffix}"
        return f"{value}B"
    if field in {"checkTime", "createTime", "statusTime"}:
        if isinstance(value, (int, float)):
            date = datetime.fromtimestamp(value / 1000, BEIJING)
        else:
            date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if date.tzinfo is not None:
                date = date.astimezone(BEIJING)
        return date.strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def render_page(result, output, *, periods=False):
    if output == "json":
        print_result(result, output)
        return
    console.print(f"任务 ID：{result['taskId']}", markup=False)
    items = result["items"]
    if not items:
        print_text("暂无执行周期" if periods else "暂无执行记录")
    elif periods:
        table = Table(show_header=False, show_lines=True, box=box.SQUARE, expand=True)
        for _ in range(4):
            table.add_column(ratio=1, overflow="fold", min_width=1)
        cells = []
        for index, item in enumerate(items, 1):
            period = item.get("period") or "-"
            state = item.get("state") or "-"
            cells.append(Text(f"{index} {period} {STATES.get(state, state)}"))
        for offset in range(0, len(cells), 4):
            row = cells[offset:offset + 4]
            table.add_row(*(row + [Text("")] * (4 - len(row))))
        console.print(table)
    else:
        table = Table(show_header=True, header_style="bold cyan")
        for title, field in COLUMNS:
            if field == "jobId":
                table.add_column(title, width=36, min_width=36, max_width=36,
                                 no_wrap=True, overflow="ignore")
            else:
                table.add_column(title, overflow="fold", min_width=1)
        for item in items:
            table.add_row(*(Text(display_value(field, item.get(field))) for _, field in COLUMNS))
        console.print(table)
    print_text(f"第 {result['page']} 页 · 每页 {result['pageSize']} 条 · 共 {result['total']} 条")


def query(context, output, operation, *, periods=False):
    runtime = runtime_from_context(context)
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    with redirect_stdout(sys.stderr):
        result = runtime.authenticated_call(lambda client: operation(SampleExecutionService(client)))
    render_page(result, selected, periods=periods)


@period_app.command("list")
def list_periods(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="新版样本任务 ID"),
    page: int = typer.Option(1, "--page", min=1, help="查询页码"),
    page_size: int = typer.Option(20, "--page-size", min=1, help="每页条数"),
    start_time: Optional[str] = typer.Option(None, "--start-time", help="周期开始日期，北京时间 YYYY-MM-DD HH:mm:ss"),
    end_time: Optional[str] = typer.Option(None, "--end-time", help="周期结束日期，北京时间 YYYY-MM-DD HH:mm:ss"),
    states: Optional[List[str]] = typer.Option(None, "--state", help="运行状态，可重复指定: " + "; ".join(f"{k}={v}" for k, v in STATES.items())),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询新版样本任务的执行周期"""
    try:
        validate_options(task_id, page, page_size, start_time, end_time, states)
        query(context, output, lambda service: service.list_periods(
            task_id, page, page_size, start_time, end_time, states), periods=True)
    except Exception as exc:
        fail(exc)


@execution_app.command("list")
def list_executions(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="新版样本任务 ID"),
    page: int = typer.Option(1, "--page", min=1, help="查询页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页条数"),
    include_history: bool = typer.Option(False, "--include-history", help="包含历史执行实例"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询新版样本任务的执行记录"""
    try:
        validate_options(task_id, page, page_size)
        query(context, output, lambda service: service.list_executions(task_id, page, page_size, include_history))
    except Exception as exc:
        fail(exc)
