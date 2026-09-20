"""Web Studio 列表、动态登录和默认实例。"""
import json
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from .common import fail, runtime_from_context
from .jupyter import display_time
from ..output import console
from ..webstudio.resolve import platform, resolve, show

webstudio_app = typer.Typer(no_args_is_help=True, help='Web Studio 查询与 Jupyter 动态登录')
COLUMNS = [('envId', 'envId'), ('名称', 'labelName'), ('集群类型', 'clusterType'),
           ('资源规格', 'imageSpecific'), ('状态', 'status'), ('创建者', 'operator'),
           ('修改者', 'modifier'), ('启动时间', 'accessTime')]


def safe_data(value):
    """保留扩展字段，但不得将新增的凭据字段或带 Token 的 URL 输出。"""
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if any(s in k.lower() for s in ('token', 'cookie', 'password', 'secret', 'accessurl', 'authorization'))
                    else safe_data(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [safe_data(v) for v in value]
    if isinstance(value, str) and 'token=' in value.lower():
        return '[REDACTED]'
    return value


@webstudio_app.command('list')
def list_studios(context: typer.Context,
                 page: int = typer.Option(1, '--page', min=1),
                 page_size: int = typer.Option(10, '--page-size', min=1),
                 name: str = typer.Option('', '--name'),
                 status: str = typer.Option('', '--status'),
                 relator: str = typer.Option('', '--relator'),
                 env_id: str = typer.Option('', '--env-id'),
                 business_id: Optional[str] = typer.Option(None, '--business-id'),
                 output: str = typer.Option('table', '--output')):
    """当前业务的实例列表；name 模糊匹配，其余条件精确匹配。"""
    try:
        if output not in ('table', 'json'):
            raise ValueError('--output 仅支持 table 或 json')
        with platform(runtime_from_context(context)) as (service, _, __):
            payload = safe_data(service.list(page, page_size, name, status, relator, env_id, business_id))
        if output == 'json':
            typer.echo(json.dumps(payload, ensure_ascii=False))
            return
        table = Table()
        for index, (title, _) in enumerate(COLUMNS):
            table.add_column(title, **({'width': 36, 'min_width': 36, 'max_width': 36,
                                       'no_wrap': True, 'overflow': 'ignore'} if index == 0
                                      else {'overflow': 'fold', 'min_width': 1}))
        result = payload['result']
        for item in result['envs']:
            table.add_row(*[Text(display_time(item.get(key)) if key == 'accessTime'
                                else str(item.get(key) if item.get(key) is not None else '-')) for _, key in COLUMNS])
        console.print(table)
        typer.echo(f"第 {page} 页 · 本页 {len(result['envs'])} 条 · 总计 {result['count']} 条")
    except Exception as exc:
        fail(exc)


@webstudio_app.command('login')
def login_studio(context: typer.Context, env_id: str = typer.Argument(...)):
    """动态获取凭据并验证 Kernel 接口，成功后保存默认实例；不保存 Token。"""
    try:
        connection = resolve(runtime_from_context(context), env_id, login=True,
                             report=lambda value: typer.echo(value, err=True))
        typer.echo(f'Web Studio 登录成功，默认实例：{connection.studio_id}')
    except Exception as exc:
        fail(exc)


@webstudio_app.command('show')
def show_studio(context: typer.Context):
    """显示当前环境、账号与业务绑定的选择（不代表实例实时状态）。"""
    try:
        result = show(runtime_from_context(context))
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        fail(exc)
