"""模型信息查询及面向用户的列表、详情展示。"""
import json
import sys
from contextlib import redirect_stdout
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from ..errors import BusinessError
from ..models import BEIJING_TIMEZONE
from ..output import console
from ..services.model import ModelService
from .common import fail, runtime_from_context

model_app = typer.Typer(no_args_is_help=True, help='模型信息查询')
LIST_COLUMNS = (
    ('模型 ID', 'modelId'), ('模型名称', 'name'), ('模型版本', 'version'),
    ('业务编码', 'businessId'), ('类型', 'type'), ('创建时间', 'createTime'),
    ('更新时间', 'updateTime'), ('归属者', 'owner'), ('团队', 'teamId'),
)
DETAIL_FIELDS = (
    ('算法类型', 'algorithm'), ('版本标签', 'modelTag'), ('模型大小', 'modelSize'),
    ('存储方式', 'storeType'), ('SFS标识', 'sfsId'), ('数据源', 'source'),
    ('数据源标签', 'sourceId'), ('更新方式', 'contentMode'), ('模型来源环境', 'sourceEnv'),
)


def readable_size(value):
    if type(value) is bool:
        return str(value)
    try:
        size = Decimal(str(value))
    except InvalidOperation:
        return str(value)
    if not size.is_finite() or size < 0:
        return str(value)
    units = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB')
    index = 0
    while size >= 1024 and index < len(units) - 1:
        size /= 1024
        index += 1
    return f'{size:.2f} {units[index]}' if index else f'{size:f} B'


def display_value(field, value):
    if value is None or value == '':
        return '-'
    if field == 'modelSize':
        return readable_size(value)
    if field in {'createTime', 'updateTime'}:
        try:
            if type(value) in {int, float}:
                instant = datetime.fromtimestamp(
                    value / 1000 if abs(value) >= 100_000_000_000 else value, BEIJING_TIMEZONE)
            else:
                instant = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                if instant.tzinfo is not None:
                    instant = instant.astimezone(BEIJING_TIMEZONE)
            return instant.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OverflowError, OSError):
            return str(value)
    return str(value)


def render_list(payload, page, page_size, output):
    if output == 'json':
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    table = Table(show_header=True, header_style='bold cyan')
    for index, (title, _) in enumerate(LIST_COLUMNS):
        table.add_column(title, **({'width': 36, 'min_width': 36, 'max_width': 36,
                                   'no_wrap': True, 'overflow': 'ignore'} if index == 0
                                  else {'overflow': 'fold', 'min_width': 1}))
    result = payload['result']
    for item in result['models']:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in LIST_COLUMNS))
    console.print(table)
    if not result['models']:
        console.print('暂无模型')
    console.print(f"第 {page} 页 · 每页 {page_size} 条 · 本页 {len(result['models'])} 条 · 共 {result['count']} 条")
    console.print('时间：Asia/Shanghai (UTC+08:00)')


def render_detail(payload, output):
    if output == 'json':
        typer.echo(json.dumps(payload, ensure_ascii=False))
        return
    for title, field in DETAIL_FIELDS:
        console.print(Text(f"{title}：{display_value(field, payload['result'].get(field))}"))


def selected_output(runtime, output):
    selected = (output if output is not None else runtime.config.current_profile().output_format).lower()
    if selected not in {'table', 'json'}:
        raise ValueError('output 仅支持 table 或 json')
    return selected


def selected_service(runtime, client):
    profile = runtime.config.current_profile()
    selected = runtime.business.selected_business_id(profile.name, client.username)
    if selected != client.business_id:
        raise BusinessError('当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh')
    return ModelService(client)


@model_app.command('list')
def list_models(context: typer.Context,
                page: int = typer.Option(1, '--page', min=1, help='页码'),
                page_size: int = typer.Option(10, '--page-size', min=1, help='每页条数'),
                name: str = typer.Option('', '--name', help='模型名称条件'),
                model_type: Optional[str] = typer.Option(None, '--type', help='模型类型条件'),
                owner: Optional[str] = typer.Option(None, '--owner', help='归属者条件'),
                team_id: str = typer.Option('', '--team-id', help='团队条件'),
                output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询当前业务的模型列表"""
    try:
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(lambda client: selected_service(runtime, client).list_models(
                page, page_size, name, model_type, owner, team_id))
        render_list(payload, page, page_size, selected)
    except Exception as exc:
        fail(exc)


@model_app.command('detail')
def detail(context: typer.Context,
           model_id: str = typer.Argument(..., help='模型 ID'),
           output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查询模型详情"""
    try:
        if not model_id.strip():
            raise ValueError('模型 ID 不能为空')
        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(lambda client: selected_service(runtime, client).detail(model_id))
        render_detail(payload, selected)
    except Exception as exc:
        fail(exc)
