"""无需登录或有效平台配置的本地文本历史管理。"""

import sys
from datetime import datetime
from typing import Optional

import click
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
    rows.reverse()
    rows.sort(key=lambda row: row.get('started_at', 0), reverse=True)
    if output == 'json':
        print_result(rows[:limit or 20], 'json')
        return
    if can_browse():
        browse(rows if limit is None else rows[:limit])
    else:
        render_rows(rows[:limit or 20])


def can_browse():
    return sys.stdin.isatty() and sys.stdout.isatty()


def render_rows(rows):
    table = Table('执行时间', '环境', '结果', '耗时', '命令')
    labels = {'success': '成功', 'failed': '失败', 'interrupted': '中断'}
    for row in rows:
        table.add_row(Text(safe_text(row['time'])), Text(safe_text(row.get('env') or '-')),
            Text(labels.get(row['status'], row['status'])), f"{row.get('duration_ms', 0) / 1000:.2f}s",
            Text(safe_text(row['command'])))
    console.print(table)
    if not rows:
        console.print('暂无匹配的历史记录')


def browse(rows):
    if not rows:
        render_rows(rows)
        return
    page = 0
    size = 20
    pages = (len(rows) + size - 1) // size
    while True:
        render_rows(rows[page * size:(page + 1) * size])
        console.print(f'第 {page + 1} / {pages} 页 · 共 {len(rows)} 条记录')
        while True:
            try:
                answer = click.prompt('[n] 下一页  [p] 上一页  [q] 退出，请输入',
                                      default='', show_default=False).strip().lower()
            except (KeyboardInterrupt, click.Abort, EOFError):
                return
            if answer == 'q':
                return
            if answer == 'n':
                if page + 1 < pages:
                    page += 1
                    break
                console.print('已经是最后一页')
            elif answer == 'p':
                if page > 0:
                    page -= 1
                    break
                console.print('已经是第一页')
            else:
                console.print('请输入 n、p 或 q 后按回车')


@history_app.callback()
def default_history(context: typer.Context):
    """交互浏览历史，非交互时显示最近 20 条"""
    if context.invoked_subcommand is None:
        try:
            show_list(context, None, '', None, None, 'table')
        except Exception as exc:
            fail(exc)


@history_app.command('list')
def list_history(context: typer.Context,
    limit: Optional[int] = typer.Option(None, '--limit', min=1, max=1000, help='最多显示条数；非交互默认 20'),
    search: str = typer.Option('', '--search', help='命令内容关键字'),
    env: Optional[str] = typer.Option(None, '--env', help='执行前的环境'),
    status: Optional[str] = typer.Option(None, '--status', help='success、failed 或 interrupted'),
    output: str = typer.Option('table', '--output', '-o', help='table 或 json')):
    """查询历史执行记录"""
    try:
        show_list(context, limit, search, env, status, output)
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
