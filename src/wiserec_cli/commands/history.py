"""无需登录或有效平台配置的本地文本历史管理。"""

import sys
from datetime import datetime
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from ..history_recording import config_location, safe_text
from ..history_store import HistoryStore
from ..models import BEIJING_TIMEZONE
from ..output import console, print_result
from .common import fail

history_app = typer.Typer(invoke_without_command=True, help='查看和管理本地命令历史')


def store_for(context):
    return HistoryStore(config_location(context.find_root().params.get('config')))


def selected(records, search='', env=None, status=None):
    return [row for row in records if search.casefold() in row['command'].casefold()
            and (env is None or row.get('env') == env)
            and (status is None or row['status'] == status)]


def show_list(context, limit, search, env, status, output):
    if output not in {'table', 'json'}:
        raise ValueError('output 仅支持 table 或 json')
    if status not in {None, 'success', 'failed', 'interrupted'}:
        raise ValueError('status 仅支持 success、failed、interrupted')
    rows = selected(store_for(context).read(), search, env, status)
    rows.sort(key=lambda row: (row.get('started_at', 0), row['id']), reverse=True)
    rows = rows[:limit]
    if output == 'json':
        print_result(rows, 'json')
        return
    table = Table('序号', '执行时间', '环境', '结果', '耗时', '命令')
    labels = {'success': '成功', 'failed': '失败', 'interrupted': '中断'}
    for row in rows:
        table.add_row(str(row['id']), Text(safe_text(row['time'])), Text(safe_text(row.get('env') or '-')),
            Text(labels.get(row['status'], row['status'])), f"{row.get('duration_ms', 0) / 1000:.2f}s",
            Text(safe_text(row['command'])))
    console.print(table)
    if not rows:
        console.print('暂无匹配的历史记录')


@history_app.callback()
def default_history(context: typer.Context):
    """默认显示最近 20 条记录"""
    if context.invoked_subcommand is None:
        try:
            show_list(context, 20, '', None, None, 'table')
        except Exception as exc:
            fail(exc)


@history_app.command('list')
def list_history(context: typer.Context,
    limit: int = typer.Option(20, '--limit', min=1, max=1000, help='最多显示条数'),
    search: str = typer.Option('', '--search', help='命令内容关键字'),
    env: Optional[str] = typer.Option(None, '--env', help='执行前的环境'),
    status: Optional[str] = typer.Option(None, '--status', help='success、failed 或 interrupted'),
    output: str = typer.Option('table', '--output', '-o', help='table 或 json')):
    """查询历史执行记录"""
    try:
        show_list(context, limit, search, env, status, output)
    except Exception as exc:
        fail(exc)


@history_app.command('show')
def show_history(context: typer.Context,
    record_id: int = typer.Argument(..., min=1, help='历史序号'),
    output: str = typer.Option('table', '--output', '-o', help='table 或 json')):
    """查看单条记录"""
    try:
        rows = [row for row in store_for(context).read() if row['id'] == record_id]
        if not rows:
            raise ValueError('历史记录不存在')
        if output == 'json':
            print_result(rows[0], 'json')
        elif output == 'table':
            table = Table('字段', '值')
            for key, value in rows[0].items():
                table.add_row(Text(safe_text(key)), Text(safe_text(str(value))))
            console.print(table)
        else:
            raise ValueError('output 仅支持 table 或 json')
    except Exception as exc:
        fail(exc)


@history_app.command('delete')
def delete_history(context: typer.Context, record_id: int = typer.Argument(..., min=1, help='历史序号')):
    """删除单条记录"""
    try:
        count = store_for(context).remove(lambda row: row['id'] == record_id, lambda count: True)
        if not count:
            raise ValueError('历史记录不存在')
        console.print(f'已删除 {count} 条历史记录')
    except Exception as exc:
        fail(exc)


@history_app.command('clear')
def clear_history(context: typer.Context,
    env: Optional[str] = typer.Option(None, '--env', help='仅清理指定环境'),
    before: Optional[str] = typer.Option(None, '--before', help='清理早于指定北京时间的记录'),
    yes: bool = typer.Option(False, '--yes', help='跳过交互确认')):
    """清理历史记录"""
    try:
        cutoff = None
        if before is not None:
            parsed = datetime.strptime(before, '%Y-%m-%d %H:%M:%S')
            cutoff = parsed.replace(tzinfo=BEIJING_TIMEZONE).timestamp()
        def predicate(row):
            return (env is None or row.get('env') == env) and (
                cutoff is None or row.get('started_at', 0) < cutoff)
        def confirm(count):
            if yes:
                return True
            if not sys.stdin.isatty():
                raise ValueError(f'匹配 {count} 条记录，非交互清理必须传入 --yes')
            return typer.confirm(f'将删除 {count} 条历史记录，是否继续？')
        count = store_for(context).remove(predicate, confirm)
        console.print(f'已清理 {count} 条历史记录')
    except Exception as exc:
        fail(exc)
