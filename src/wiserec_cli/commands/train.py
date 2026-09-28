"""训练任务管理命令及表格展示。"""

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
from ..services.train_export import export_config
from .common import fail, runtime_from_context


train_app = typer.Typer(no_args_is_help=True, help="训练任务查询与执行管理")
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
        elif field == "taskId" and task is None and history_task_id is None:
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


@config_app.command("export")
def export_train_config(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务 ID"),
    file: Optional[Path] = typer.Option(None, "--file", help="本地保存路径，父目录须已存在"),
) -> None:
    """导出并下载训练任务的 YAML 配置。"""
    try:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        if file is not None and not file.expanduser().absolute().parent.is_dir():
            raise ValueError(f"目标目录不存在：{file.expanduser().absolute().parent}")
        runtime = runtime_from_context(context)
        with Progress(TextColumn("下载训练任务配置"), BarColumn(), DownloadColumn(),
                      console=error_console) as progress:
            progress_id = progress.add_task("export", total=None)
            with redirect_stdout(sys.stderr):
                path, size = runtime.authenticated_call(
                    lambda client: export_config(
                        client, task_id, file,
                        progress=lambda done, total: progress.update(
                            progress_id, completed=done, total=total,
                        ),
                    )
                )
        typer.echo(f"训练任务配置已下载：{path}（{size} 字节）")
    except Exception as exc:
        fail(exc)


@train_app.command("cancel")
def cancel_task(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过批量取消确认"),
) -> None:
    """查询所有执行实例并逐个取消。"""
    failed = 0
    try:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)

        def query(client):
            service = TrainService(client)
            task = service.find_task(task_id)
            return service.all_instances(task)

        with redirect_stdout(sys.stderr):
            instances = runtime.authenticated_call(query)
        if not instances:
            typer.echo("没有正在执行的任务，无法取消任务执行！")
            raise typer.Exit(code=1)
        typer.echo(f"训练任务 {task_id} 有 {len(instances)} 个执行实例待取消。")
        if not yes and not typer.confirm("确认逐个取消全部执行实例？", default=False):
            typer.echo("已取消操作")
            return
        for instance in instances:
            job_id = instance["jobId"]
            try:
                with redirect_stdout(sys.stderr):
                    description = runtime.authenticated_call(
                        lambda client: TrainService(client).cancel_instance(
                            task_id, job_id, instance["taskName"],
                        )
                    )
                typer.echo(f"取消训练任务{task_id}的执行实例{job_id}成功，响应描述是{description}")
            except Exception as exc:
                failed += 1
                print(f"取消训练任务{task_id}的执行实例{job_id}失败：{exc}", file=sys.stderr)
        typer.echo(f"取消完成：成功 {len(instances) - failed} 个，失败 {failed} 个。")
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)
    if failed:
        raise typer.Exit(code=1)


@train_app.command("delete")
def delete_task(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="训练任务 ID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过删除确认"),
) -> None:
    """软删除当前业务下的训练任务。"""
    try:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)
        with redirect_stdout(sys.stderr):
            task = runtime.authenticated_call(
                lambda client: TrainService(client).find_task(
                    task_id, required_fields=("teamId", "taskName"),
                )
            )
        if not isinstance(task.get("teamId"), str) or not isinstance(task.get("taskName"), str):
            raise ValueError("训练任务缺少 teamId 或 taskName，无法删除")
        typer.echo(f"待删除训练任务：{task['taskName']} · {task_id}（团队 {task['teamId'] or '-'}）")
        if not yes and not typer.confirm("确认软删除此任务？", default=False):
            typer.echo("已取消操作")
            return
        with redirect_stdout(sys.stderr):
            runtime.authenticated_call(lambda client: TrainService(client).delete_task(task))
        typer.echo(f"删除训练任务{task_id}成功")
    except Exception as exc:
        fail(exc)


@train_app.command("clone")
def clone_task(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="源训练任务 ID"),
    name: str = typer.Option(..., "--name", help="克隆后的新任务名称"),
    customize_config: Optional[str] = typer.Option(
        None, "--customize-config", help="可选自定义参数，按字符串原样传递",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过克隆确认"),
) -> None:
    """读取完整训练任务详情并创建副本。"""
    try:
        task_id = task_id.strip()
        if not task_id or not name.strip():
            raise ValueError("taskId 和新任务名称不能为空")
        runtime = runtime_from_context(context)

        def query(client):
            service = TrainService(client)
            task = service.find_task(task_id, required_fields=("teamId",))
            return task, service.clone_detail(task)

        with redirect_stdout(sys.stderr):
            task, detail = runtime.authenticated_call(query)
        typer.echo(f"获取训练任务{task_id}详情成功")
        typer.echo(f"克隆为：{name}（源任务：{task.get('taskName') or task_id}）")
        if not yes and not typer.confirm("确认克隆？", default=False):
            typer.echo("已取消克隆")
            return
        with redirect_stdout(sys.stderr):
            created_id = runtime.authenticated_call(
                lambda client: TrainService(client).clone_task(detail, name, customize_config)
            )
        typer.echo(f"克隆训练任务{task_id}成功")
        if created_id:
            typer.echo(f"新任务 ID：{created_id}")
    except Exception as exc:
        fail(exc)


@train_app.command("start")
def start_task(
    context: typer.Context,
    task_id: str = typer.Argument(..., help="要执行的训练任务 ID"),
) -> None:
    """立即执行指定训练任务，返回作业 ID；不预先查询任务列表。"""
    try:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        runtime = runtime_from_context(context)
        with redirect_stdout(sys.stderr):
            job_id = runtime.authenticated_call(lambda client: TrainService(client).start(task_id))
        if job_id is None:
            typer.echo("训练任务执行成功，但接口未返回有效 jobId，请查询执行记录确认。")
        else:
            typer.echo(f"训练任务执行成功，jobId：{job_id}")
    except Exception as exc:
        fail(exc)


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
        typer.echo("更新训练任务自定义参数成功！")
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
