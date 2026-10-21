"""样本任务命令和展示。"""
import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, print_result, print_text
from ..services.sample_task import LEGACY_TYPES, NEW_TYPES, SampleTaskService, validate_options
from .common import fail, runtime_from_context

sample_task_app = typer.Typer(no_args_is_help=True, help="样本任务")
LEGACY_COLUMNS = (
    ("任务ID", "taskId"), ("任务名称", "taskName"), ("任务类型", "category"),
    ("创建者", "createUser"), ("修改者", "updateUser"),
    ("最近修改时间", "updateTime"), ("描述", "description"),
)
NEW_COLUMNS = (
    ("任务ID", "taskId"), ("任务名称", "taskName"), ("任务类型", "taskSubCategoryCn"),
    ("创建者", "createBy"), ("修改者", "updateBy"), ("创建时间", "createTime"),
    ("开始执行时间", "latestRunTime"), ("最近修改时间", "updateTime"),
    ("描述", "description"), ("任务状态", "taskStateCn"),
)
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))


def display_value(field, item):
    value = item.get(field)
    if field == "taskSubCategoryCn" and not value:
        code = item.get("taskSubCategory")
        value = NEW_TYPES.get(code, code)
    if field == "taskStateCn" and not value:
        code = item.get("taskState") or item.get("taskStatus")
        value = {"START": "启动", "STOP": "停止"}.get(code, code)
    if value is None or value == "":
        return "-"
    if field == "category":
        return LEGACY_TYPES.get(value, str(value))
    if field in {"createTime", "updateTime", "latestRunTime"}:
        try:
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                parsed = datetime.fromtimestamp(value / 1000, DISPLAY_TIMEZONE)
            else:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                if parsed.tzinfo is not None:
                    parsed = parsed.astimezone(DISPLAY_TIMEZONE)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, OverflowError, OSError):
            return str(value)
    return str(value)


def render_page(result, output):
    if output == "json":
        print_result(result, output)
        return
    source = "任务管理（新）" if result["source"] == "new" else "任务管理（旧）"
    print_text(f"来源：{source}")
    columns = NEW_COLUMNS if result["source"] == "new" else LEGACY_COLUMNS
    table = Table(show_header=True, header_style="bold cyan")
    for title, field in columns:
        if field == "taskId":
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item)) for _, field in columns))
    console.print(table)
    if not result["items"]:
        print_text("暂无样本任务")
    print_text(f"第 {result['page']} 页 · 每页 {result['pageSize']} 条 · 共 {result['total']} 条")


@sample_task_app.command("list")
def list_tasks(
    context: typer.Context,
    source: str = typer.Option("legacy", "--source", help="任务来源: legacy 旧任务管理，new 新任务管理"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    name: Optional[str] = typer.Option(None, "--name", help="按任务名称查询"),
    creator: Optional[str] = typer.Option(None, "--creator", help="按创建者查询"),
    updater: Optional[str] = typer.Option(None, "--updater", help="按修改者查询"),
    types: Optional[List[str]] = typer.Option(None, "--type", help=(
        "任务类型，可重复指定；旧版默认查询前四种类型。旧版: "
        + "; ".join(f"{k}={v}" for k, v in LEGACY_TYPES.items())
        + "。新版: " + "; ".join(f"{k}={v}" for k, v in NEW_TYPES.items())
    )),
    status: Optional[str] = typer.Option(None, "--status", help="仅旧版: all、stopped、started，默认 all"),
    sort: Optional[str] = typer.Option(None, "--sort", help="仅新版: desc，默认 desc"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询样本任务，默认使用旧任务管理"""
    try:
        validate_options(source, page, page_size, types, status, sort)
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {"table", "json"}:
            raise ValueError("output 仅支持 table 或 json")
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(lambda client: SampleTaskService(client).list_tasks(
                source=source, page=page, page_size=page_size, name=name, creator=creator,
                updater=updater, types=types, status=status, sort=sort,
            ))
        render_page(result, selected)
    except Exception as exc:
        fail(exc)
