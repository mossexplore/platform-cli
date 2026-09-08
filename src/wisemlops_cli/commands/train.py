"""训练任务查询命令及表格展示。"""

from __future__ import annotations

import sys
import time
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.table import Table
from rich.text import Text
from rich.progress import Progress, BarColumn, DownloadColumn, TextColumn

from ..output import console, error_console, print_result
from ..downloads import download_file
from ..services.train import TrainService
from .common import fail, runtime_from_context


train_app = typer.Typer(no_args_is_help=True, help="训练任务查询")
instance_app = typer.Typer(no_args_is_help=True, help="训练任务执行实例查询")
train_app.add_typer(instance_app, name="instance")
history_app = typer.Typer(no_args_is_help=True, help="训练任务执行记录查询")
train_app.add_typer(history_app, name="history")
logs_app = typer.Typer(no_args_is_help=True, help="执行记录日志下载")
history_app.add_typer(logs_app, name="logs")
config_app = typer.Typer(no_args_is_help=True, help="训练任务自定义参数管理")
train_app.add_typer(config_app, name="config")

TASK_COLUMNS = (
    ("任务 ID", "taskId"), ("任务名称", "taskName"), ("任务类型", "taskType"),
    ("业务场景", "scene"), ("修改者", "updateUser"), ("更新时间", "updateTime"),
    ("最新执行时间", "latestRunTime"), ("大小", "fileSize"), ("描述", "description"),
)
INSTANCE_COLUMNS = (
    ("作业ID", "jobId"), ("算法名称", "algorithmName"),
    ("CPU", "cpuSize"), ("GPU", "gpuSize"), ("内存", "memorySize"),
    ("状态", "status"), ("执行节点", "hostIp"), ("集群", "poolName"),
    ("触发方式", "actionType"), ("开始时间", "createTime"),
    ("执行时长", "runningTime"), ("存储桶", "bucketName"),
)
HISTORY_COLUMNS = (
    ("作业ID", "jobId"), ("算法名称", "algorithmName"),
    ("CPU", "cpuSize"), ("GPU", "gpuSize"), ("内存", "memorySize"),
    ("状态", "status"), ("集群", "poolName"), ("节点数", "infraSize"),
    ("执行时长", "runningTime"), ("大小", "fileSize"),
    ("检查时间", "checkTime"), ("开始时间", "createTime"), ("结束时间", "statusTime"),
    ("触发方式", "actionType"), ("存储桶", "bucketName"),
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


def render_page(
    result: Dict[str, Any], output: str, task: Optional[Dict[str, Any]] = None,
    *, history_task_id: Optional[str] = None,
) -> None:
    if output == "json":
        print_result(result, output)
        return
    if task is not None:
        console.print(f"任务：{display_value('taskName', task.get('taskName'))} · {task['taskId']}", markup=False)
    columns = INSTANCE_COLUMNS if task is not None else TASK_COLUMNS
    if history_task_id is not None:
        console.print(f"任务 ID：{history_task_id}", markup=False)
        columns = HISTORY_COLUMNS
    table = Table(show_header=True, header_style="bold cyan")
    for title, field in columns:
        if field == "jobId":
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    now_ms = int(time.time() * 1000)
    for item in result["items"]:
        cells = []
        for _, field in columns:
            if task is not None and history_task_id is None and field == "runningTime":
                start = item.get("createTime")
                rendered = "-" if start is None or start == "" else f"{max(0, int((now_ms - start) // 60000))}min"
            else:
                rendered = display_value(field, item.get(field))
            cells.append(Text(rendered))
        table.add_row(*cells)
    console.print(table)
    if not result["items"]:
        empty_message = "暂无执行实例" if task is not None else "暂无训练任务"
        console.print("暂无执行记录" if history_task_id is not None else empty_message)
    console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")
    console.print("时间：Asia/Shanghai (UTC+08:00)")
    if (task is not None or history_task_id is not None) and result["count"] > 10:
        order = "倒序" if history_task_id is not None else "升序"
        console.print(f"当前仅展示第 1 页 10 条，暂不支持翻页；按开始时间{order}排列。")


def selected_output(runtime: Any, output: Optional[str]) -> str:
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    return selected


@config_app.command("update")
def update_config(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务 ID"),
    customize_config: str = typer.Option(..., "--customize-config", help="自定义参数，按字符串原样传递"),
) -> None:
    """获取训练任务详情，保留完整 taskInfo 后更新自定义参数。"""
    try:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)

        def update(client):
            profile = runtime.config.current_profile()
            username = runtime.business.username(profile.name, client.username)
            TrainService(client).update_config(task_id, customize_config, username)

        with redirect_stdout(sys.stderr):
            runtime.authenticated_call(update)
        typer.echo("更新训练任务自定义参数")
    except Exception as exc:
        fail(exc)


@logs_app.command("download")
def download_logs(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="所属训练任务 ID"),
    job_id: str = typer.Argument(..., help="执行记录 ID"),
    file: Optional[Path] = typer.Option(None, "--file", help="本地保存路径，目录须已存在"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="结果摘要格式: table 或 json"),
) -> None:
    """获取日志地址并下载；发送 isApplicantPromise=true，不覆盖已有文件。"""
    try:
        if file is not None:
            file = file.expanduser().absolute()
            if not file.parent.is_dir():
                raise ValueError(f"目标目录不存在：{file.parent}")
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            url = runtime.authenticated_call(
                lambda client: TrainService(client).get_log_url(task_id, job_id)
            )
        print(f"下载地址：{url}", file=sys.stderr, flush=True)
        with Progress(TextColumn("下载日志"), BarColumn(), DownloadColumn(),
                      console=error_console) as progress:
            progress_id = progress.add_task("logs", total=None)
            path, size = download_file(
                url, job_id, file,
                progress=lambda done, total: progress.update(progress_id, completed=done, total=total),
            )
        print_result({"taskId": task_id, "jobId": job_id, "path": str(path),
                      "bytes": size, "status": "downloaded"}, selected)
    except Exception as exc:
        fail(exc)


@history_app.command("list")
def list_history(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务的完整 taskId"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """直接查询执行记录；固定第 1 页 10 条，开始时间倒序。"""
    try:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(
                lambda client: TrainService(client).list_history(task_id)
            )
        render_page(result, selected, history_task_id=task_id)
    except Exception as exc:
        fail(exc)


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
