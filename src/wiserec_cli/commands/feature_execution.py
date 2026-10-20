"""特征任务执行记录查询。"""
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, print_result, print_text
from ..errors import ApiError
from ..services.feature_execution import FeatureExecutionService, validate_log_options
from .common import fail, runtime_from_context

execution_app = typer.Typer(no_args_is_help=True, help="特征任务执行记录")
logs_app = typer.Typer(no_args_is_help=True, help="执行记录日志")
execution_app.add_typer(logs_app, name="logs")
COLUMNS = (
    ("job ID", "jobId"), ("算法名称", "algorithmName"), ("CPU", "cpuSize"),
    ("GPU", "gpuSize"), ("内存", "memorySize"), ("状态", "status"),
    ("集群", "poolName"), ("节点数", "infraSize"), ("大小", "fileSize"),
    ("执行时长", "runningTime"), ("最新实例", "latestFlag"),
    ("检查时间", "checkTime"), ("开始时间", "createTime"), ("结束时间", "statusTime"),
)


def display_value(field, value):
    if value is None or value == "":
        return "-"
    if field in {"checkTime", "createTime", "statusTime"}:
        return datetime.fromtimestamp(value / 1000, timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    if field == "latestFlag":
        return "是" if value is True else "否" if value is False else str(value)
    if field == "runningTime":
        hours, minutes = divmod(value, 60)
        return f"{hours}h{minutes}min" if hours else f"{minutes}min"
    if field == "fileSize":
        if value < 1024:
            return f"{value}B"
        for exponent, suffix in ((3, "G"), (2, "M"), (1, "K")):
            if value >= 1024 ** exponent:
                return f"{value / 1024 ** exponent:.2f}{suffix}"
    return str(value)


def render_page(result, task_id, output):
    if output == "json":
        print_result(result, output)
        return
    console.print(f"任务 ID：{task_id}", markup=False)
    table = Table(show_header=True, header_style="bold cyan")
    for title, field in COLUMNS:
        if field == "jobId":
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in COLUMNS))
    console.print(table)
    if not result["items"]:
        print_text("暂无执行记录")
    print_text(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")


@execution_app.command("list")
def list_executions(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="特征任务 ID"),
    page: int = typer.Option(1, "--page", min=1, help="查询页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页条数"),
    include_history: bool = typer.Option(False, "--include-history", help="包含历史执行实例"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询特征任务的执行记录"""
    try:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {"table", "json"}:
            raise ValueError("output 仅支持 table 或 json")
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(lambda client: FeatureExecutionService(client).list_executions(
                task_id, page, page_size, include_history))
        render_page(result, task_id.strip(), selected)
    except Exception as exc:
        fail(exc)


@logs_app.command("search")
def search_logs(
    context: typer.Context,
    job_id: str = typer.Argument(..., help="执行记录 job ID"),
    start_line: int = typer.Option(1, "--start-line", min=1, help="起始行"),
    end_line: int = typer.Option(2000, "--end-line", min=1, help="结束行"),
    keyword: Optional[List[str]] = typer.Option(None, "--keyword", help="搜索关键词，可重复指定"),
    scope: Optional[str] = typer.Option(None, "--scope", help="A 关键词后，B 关键词前，C 关键词前后"),
    scope_lines: Optional[int] = typer.Option(None, "--scope-lines", min=1, help="搜索范围行数"),
    output: str = typer.Option("text", "--output", "-o", help="输出格式: text 或 json，默认原样显示日志文本"),
):
    """查询和搜索训练日志"""
    try:
        validate_log_options(job_id, start_line, end_line, keyword, scope, scope_lines)
        if output.lower() not in {"text", "json"}:
            raise ValueError("output 仅支持 text 或 json")
        runtime = runtime_from_context(context)
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(lambda client: FeatureExecutionService(client).search_logs(
                job_id, start_line, end_line, keyword, scope, scope_lines))
        if output.lower() == "json":
            print_result(result, "json")
        else:
            logs = result["result"].get("logs")
            if not isinstance(logs, list):
                raise ApiError("日志响应缺少有效的 logs 数组")
            if logs:
                first = logs[0]
                if not isinstance(first, dict) or not isinstance(first.get("log"), str):
                    raise ApiError("日志响应缺少有效的 logs[0].log 文本")
                # Do not use Rich: preserve whitespace, tabs and the original final newline.
                sys.stdout.write(first["log"])
                sys.stdout.flush()
    except Exception as exc:
        fail(exc)
