"""训练任务查询命令及表格展示。"""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, print_result
from ..services.train import TrainService
from .common import fail, runtime_from_context


train_app = typer.Typer(no_args_is_help=True, help="训练任务查询")
instance_app = typer.Typer(no_args_is_help=True, help="训练任务执行实例查询")
train_app.add_typer(instance_app, name="instance")

TASK_COLUMNS = (
    ("任务 ID", "taskId"), ("任务名称", "taskName"), ("任务类型", "taskType"),
    ("业务场景", "scene"), ("修改者", "updateUser"), ("更新时间", "updateTime"),
    ("最新执行时间", "latestRunTime"), ("大小", "fileSize"), ("描述", "description"),
)
INSTANCE_COLUMNS = (
    ("算法 ID", "algorithmId"), ("算法名称", "algorithmName"),
    ("CPU", "cpuSize"), ("GPU", "gpuSize"), ("内存", "memorySize"),
    ("状态", "status"), ("集群", "poolName"), ("节点数", "infraSize"),
    ("执行时长", "runningTime"), ("大小", "fileSize"),
    ("检查时间", "checkTime"), ("开始时间", "createTime"), ("结束时间", "statusTime"),
)
TIME_FIELDS = {"updateTime", "latestRunTime", "checkTime", "createTime", "statusTime"}
# 现代上海时间固定 UTC+08:00，避免 Windows 额外依赖系统 IANA 时区数据库。
DISPLAY_TIMEZONE = timezone(timedelta(hours=8), name="Asia/Shanghai")


def display_value(field: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if field == "fileSize":
        if value == 0:
            return "0B"
        divisor, suffix = (1024 ** 2, "M") if value < 1024 ** 3 else (1024 ** 3, "G")
        return f"{value / divisor:.2f}{suffix}"
    if field in TIME_FIELDS:
        return datetime.fromtimestamp(value / 1000, DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")
    return str(value)


def render_page(result: Dict[str, Any], output: str, task: Optional[Dict[str, Any]] = None) -> None:
    if output == "json":
        print_result(result, output)
        return
    if task is not None:
        console.print(f"任务：{display_value('taskName', task.get('taskName'))} · {task['taskId']}", markup=False)
    columns = INSTANCE_COLUMNS if task is not None else TASK_COLUMNS
    table = Table(show_header=True, header_style="bold cyan")
    for title, _ in columns:
        table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in columns))
    console.print(table)
    if not result["items"]:
        console.print("暂无执行实例" if task is not None else "暂无训练任务")
    console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")
    console.print("时间：Asia/Shanghai (UTC+08:00)")
    if task is not None and result["count"] > 10:
        console.print("当前仅展示第 1 页 10 条，暂不支持翻页；按开始时间升序排列。")


def selected_output(runtime: Any, output: Optional[str]) -> str:
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    return selected


@train_app.command("list")
def list_tasks(
    context: typer.Context,
    name: Optional[str] = typer.Option(None, "--name", help="按任务名称模糊查询"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """分页查询当前业务下的训练任务。"""
    try:
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        # 登录及认证重试提示不能混入 JSON 标准输出。
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(
                lambda client: TrainService(client).list_tasks(page, page_size, name)
            )
        render_page(result, selected)
    except Exception as exc:
        fail(exc)


@instance_app.command("list")
def list_instances(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务的完整 taskId"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查找训练任务并查询执行实例；固定第 1 页 10 条，开始时间升序。"""
    try:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)

        def query(client):
            service = TrainService(client)
            task = service.find_task(task_id)
            return task, service.list_instances(task)

        with redirect_stdout(sys.stderr):
            task, result = runtime.authenticated_call(query)
        render_page(result, selected, task)
    except Exception as exc:
        fail(exc)
