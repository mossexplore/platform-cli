"""数据集列表与详情命令。"""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..errors import BusinessError
from ..output import console, print_result
from ..services.dataset import DatasetService
from .common import fail, runtime_from_context


dataset_app = typer.Typer(no_args_is_help=True, help="数据集列表与详情查询")
BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
LIST_COLUMNS = (
    ("数据集 ID", "dataSetId"), ("数据集名称", "dataSetName"),
    ("租户", "businessId"), ("数据类型", "dataSetType"),
    ("修改者", "updateUser"), ("大小", "fileSize"),
    ("更新时间", "modifyTime"), ("最近使用", "useTime"),
    ("区域", "region"), ("存储桶", "bucketName"),
    ("描述", "description"),
)
DETAIL_FIELDS = (
    ("租户", "businessId"), ("团队", "teamId"),
    ("创建者", "createUser"), ("创建时间", "createTime"),
    ("更新时间", "modifyTime"), ("业务子场景", "subScene"),
    ("数据集 ID", "bucketFileId"), ("存储桶名称", "bucketName"),
    ("存储方式", "storageType"), ("文件名称", "fileName"),
    ("来源", "source"), ("描述", "description"),
)
TIME_FIELDS = {"createTime", "modifyTime", "useTime"}


def _time(value: Any) -> str:
    try:
        if type(value) in {int, float}:
            number = float(value)
            instant = datetime.fromtimestamp(
                number / 1000 if abs(number) >= 100_000_000_000 else number,
                BEIJING,
            )
        else:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if instant.tzinfo is not None:
                instant = instant.astimezone(BEIJING)
        return instant.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return str(value)


def _size(value: Any) -> str:
    if type(value) is bool:
        return str(value)
    try:
        number = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if not number.is_finite() or number < 0:
        return str(value)
    if number < 1024:
        return f"{number:g}B"
    for divisor, unit in ((1024 ** 3, "G"), (1024 ** 2, "M"), (1024, "K")):
        if number >= divisor:
            return f"{number / divisor:.2f}{unit}"
    return str(value)


def display_value(field: str, value: Any) -> str:
    if value is None or value == "":
        return "-"
    if field == "fileSize":
        return _size(value)
    if field in TIME_FIELDS:
        return _time(value)
    return str(value)


def render_list(result: dict[str, Any], output: str) -> None:
    if output == "json":
        print_result(result, output)
        return
    table = Table(show_header=True, header_style="bold cyan")
    for index, (title, _) in enumerate(LIST_COLUMNS):
        if index == 0:
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, min_width=1, overflow="fold")
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field)))
                        for _, field in LIST_COLUMNS))
    console.print(table)
    if not result["items"]:
        console.print("暂无数据集记录")
    console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['total']} 条")
    console.print("时间：Asia/Shanghai (UTC+08:00)")


def render_detail(data: dict[str, Any], output: str) -> None:
    if output == "json":
        print_result(data, output)
        return
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("字段")
    table.add_column("值", min_width=1, overflow="fold")
    for title, field in DETAIL_FIELDS:
        table.add_row(title, Text(display_value(field, data.get(field))))
    console.print(table)
    console.print("时间：Asia/Shanghai (UTC+08:00)")


def _selected_output(runtime: Any, output: Optional[str]) -> str:
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    return selected


def _selected_business(runtime: Any, client: Any) -> None:
    profile = runtime.config.current_profile()
    selected = runtime.business.selected_business_id(profile.name, client.username)
    if selected != client.business_id:
        raise BusinessError("当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh")


@dataset_app.command("list")
def list_datasets(
    context: typer.Context,
    page: int = typer.Option(1, "--page", min=1, help="页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页条数"),
    name: str = typer.Option("", "--name", "--dataset-name", help="数据集名称条件"),
    create_user: str = typer.Option("", "--create-user", help="创建者条件"),
    update_user: str = typer.Option("", "--update-user", help="修改者条件"),
    bucket_name: Optional[str] = typer.Option(None, "--bucket-name", help="存储桶条件"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """分页查询当前业务的数据集。"""
    try:
        filters = (name, create_user, update_user, bucket_name)
        if any(value is not None and value and not value.strip() for value in filters):
            raise ValueError("筛选条件不能为空白")
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return DatasetService(client).list_datasets(
                page, page_size, name.strip(), create_user.strip(),
                update_user.strip(), bucket_name.strip() if bucket_name is not None else None,
            )

        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(query)
        render_list(result, selected)
    except Exception as exc:
        fail(exc)


@dataset_app.command("detail")
def dataset_detail(
    context: typer.Context,
    dataset_id: str = typer.Argument(..., help="数据集 ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """查询指定数据集的详情。"""
    try:
        dataset_id = dataset_id.strip()
        if not dataset_id:
            raise ValueError("数据集 ID 不能为空")
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return DatasetService(client).dataset_detail(dataset_id)

        with redirect_stdout(sys.stderr):
            data = runtime.authenticated_call(query)
        render_detail(data, selected)
    except Exception as exc:
        fail(exc)
