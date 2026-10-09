"""算法仓列表、下载与克隆命令。"""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import typer
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text

from ..algorithm_download import download_algorithm
from ..errors import BusinessError
from ..output import console, error_console, print_result
from ..services.algorithm import AlgorithmService
from .common import fail, runtime_from_context


algorithm_app = typer.Typer(no_args_is_help=True, help="算法仓查询、下载与克隆")
BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
COLUMNS = (
    ("算法仓 ID", "id"), ("算法仓名称", "name"), ("版本", "version"),
    ("区域", "algorithmRegion"), ("修改者", "modifier"),
    ("修改时间", "modifyTime"), ("大小", "fileSize"),
    ("描述", "description"), ("禁用", "enableFlag"),
    ("归档状态", "archiveToNspStatus"),
)


def _selected_business(runtime: Any, client: Any) -> None:
    profile = runtime.config.current_profile()
    selected = runtime.business.selected_business_id(profile.name, client.username)
    if selected != client.business_id:
        raise BusinessError("当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh")


def _display(field: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if field == "modifyTime":
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                return instant.astimezone(BEIJING).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass
    if field == "fileSize" and type(value) in {int, float} and value >= 0:
        if value == 0:
            return "0B"
        divisor, unit = (1024 ** 2, "M") if value < 1024 ** 3 else (1024 ** 3, "G")
        return f"{value / divisor:.2f}{unit}"
    if field == "enableFlag" and type(value) is bool:
        return "否" if value else "是"
    if field == "archiveToNspStatus" and type(value) is int:
        return {1: "归档成功", 0: "未归档"}.get(value, str(value))
    return str(value)


def _render_list(result: dict[str, Any], output: str) -> None:
    if output == "json":
        print_result(result, output)
        return
    table = Table(show_header=True, header_style="bold cyan")
    for index, (title, _) in enumerate(COLUMNS):
        if index == 0:
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, min_width=1, overflow="fold")
    for item in result["items"]:
        table.add_row(*(Text(_display(field, item.get(field))) for _, field in COLUMNS))
    console.print(table)
    if not result["items"]:
        console.print("暂无算法仓记录")
    console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['total']} 条")


@algorithm_app.command("list")
def list_algorithms(
    context: typer.Context,
    page: int = typer.Option(1, "--page", min=1, help="页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页条数"),
    name: str = typer.Option("", "--name", "--algorithm-name", help="算法仓名称条件"),
    bucket_name: str = typer.Option("", "--bucket-name", help="存储桶名称条件"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """分页查询当前业务的算法仓。"""
    try:
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {"table", "json"}:
            raise ValueError("output 仅支持 table 或 json")

        def query(client):
            _selected_business(runtime, client)
            return AlgorithmService(client).list_algorithms(page, page_size, name, bucket_name)

        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(query)
        _render_list(result, selected)
    except Exception as exc:
        fail(exc)


@algorithm_app.command("download")
def download(
    context: typer.Context,
    algorithm_id: str = typer.Argument(..., help="算法仓 ID"),
    file: Optional[Path] = typer.Option(None, "--file", help="保存路径，父目录须已存在"),
) -> None:
    """获取下载地址并保存算法仓文件。"""
    try:
        algorithm_id = algorithm_id.strip()
        if not algorithm_id:
            raise ValueError("算法仓 ID 不能为空")
        if file is not None and not file.expanduser().absolute().parent.is_dir():
            raise ValueError(f"目标目录不存在：{file.expanduser().absolute().parent}")
        runtime = runtime_from_context(context)

        def query(client):
            _selected_business(runtime, client)
            return AlgorithmService(client).download_url(algorithm_id)

        with redirect_stdout(sys.stderr):
            url = runtime.authenticated_call(query)
        typer.echo(f"算法仓下载链接：{url}")
        with Progress(TextColumn("下载算法仓"), BarColumn(), DownloadColumn(),
                      console=error_console) as progress:
            task = progress.add_task("algorithm", total=None)
            path, size = download_algorithm(
                url, algorithm_id, file, verify_ssl=runtime.config.verify_ssl,
                progress=lambda done, total: progress.update(task, completed=done, total=total),
            )
        typer.echo(f"算法仓已下载：{path}（{size} 字节）")
    except Exception as exc:
        fail(exc)


@algorithm_app.command("clone")
def clone(
    context: typer.Context,
    source_id: str = typer.Argument(..., help="源算法仓 ID"),
    name: str = typer.Option(..., "--name", help="新算法仓名称"),
    version: str = typer.Option(..., "--version", help="新算法仓版本"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过克隆确认"),
) -> None:
    """按指定名称和版本克隆算法仓。"""
    try:
        source_id = source_id.strip()
        if not source_id or not name.strip() or not version.strip():
            raise ValueError("源算法仓 ID、新名称和版本均不能为空")
        runtime = runtime_from_context(context)
        typer.echo(f"源算法仓：{source_id}；新名称：{name}；新版本：{version}")
        if not yes and not typer.confirm("确认克隆算法仓？", default=False):
            typer.echo("已取消克隆")
            return

        def create(client):
            _selected_business(runtime, client)
            return AlgorithmService(client).clone(source_id, name, version)

        with redirect_stdout(sys.stderr):
            created_id = runtime.authenticated_call(create)
        typer.echo(f"克隆算法仓{source_id}成功，新名称：{name}，版本：{version}")
        if created_id:
            typer.echo(f"新算法仓 ID：{created_id}")
    except Exception as exc:
        fail(exc)
