"""服务日志的主机、类别和文件选择流程。"""
from __future__ import annotations

import sys
from contextlib import redirect_stdout
from typing import Optional

import click
import typer
from rich.table import Table
from rich.text import Text

from ..errors import ApiError
from ..output import console, error_console
from ..services.service import ServiceCatalog
from .common import fail, runtime_from_context

LOG_TYPES = {
    'infer-python': ('run', 'interface', 'metrics', 'engine', 'ascend', 'mslite', 'alarm'),
    'rtc': ('rtc', 'run', 'interface', 'dcs', 'metrics', 'gc', 'interface_manager',
            'interface_extend', 'engine', 'monitor', 'catalina', 'dmq'),
}


def can_prompt():
    return sys.stdin.isatty()


def choose(items, label, option, interactive, describe):
    if not items:
        raise ValueError(f'没有可用的{label}')
    if len(items) == 1:
        return items[0]
    if not interactive:
        raise ValueError(f'{label}无法唯一确定，请指定 {option}；同名候选需在交互终端选择')
    for index, item in enumerate(items, 1):
        error_console.print(Text(f'{index}. {describe(item)}'))
    index = click.prompt(f'请选择{label}', type=click.IntRange(1, len(items)), err=True)
    return items[index - 1]


def all_hosts(query):
    page = 1
    items = []
    while True:
        result = query(page)
        if not result['items'] and len(items) < result['total']:
            raise ApiError('主机分页提前返回空页，请重试')
        items.extend(result['items'])
        if page * result['pageSize'] >= result['total']:
            return items
        page += 1


def file_table(files):
    from .service import _text, _time
    table = Table('编号', '文件名称', '大小', '修改时间')
    for index, item in enumerate(files, 1):
        value = item.get('updateTime')
        # 无时区的 ls 风格日期保留原值。
        timestamp = _time(value) if isinstance(value, str) and 'T' in value else _text(value)
        table.add_row(str(index), Text(_text(item.get('fileName'))),
                      Text(_text(item.get('fileSize'))), Text(timestamp))
    return table


def service_logs(
    context: typer.Context,
    service_id: str = typer.Argument(..., help='服务 ID'),
    pod: Optional[str] = typer.Option(None, '--pod', help='Pod 名称'),
    log_type: Optional[str] = typer.Option(None, '--type', help='日志类别'),
    file_name: Optional[str] = typer.Option(None, '--file', help='日志文件名称'),
    keywords: Optional[list[str]] = typer.Option(None, '--keyword', '-k', help='关键词，可重复'),
    lines: int = typer.Option(200, '--lines', '-n', min=1, help='查询行数'),
    list_only: bool = typer.Option(False, '--list', help='只显示日志文件列表'),
    no_input: bool = typer.Option(False, '--no-input', help='禁止交互选择'),
    search_order: str = typer.Option('tail', '--search-order', help='检索顺序'),
    grep_scope: str = typer.Option('C', '--grep-scope', help='关键词范围'),
    grep_line: int = typer.Option(0, '--grep-line', min=0, help='关键词上下文行数'),
):
    """选择服务主机和文件并查看日志"""
    from .service import _required_text, _selected_business, display_value
    try:
        service_id = _required_text(service_id, '服务 ID')
        for value, label in ((pod, 'Pod'), (log_type, '日志类别'), (file_name, '文件名称')):
            if value is not None:
                _required_text(value, label)
        search_order = _required_text(search_order, '检索顺序')
        grep_scope = _required_text(grep_scope, '关键词范围')
        if any(not word.strip() for word in keywords or []):
            raise ValueError('关键词不能为空白')
        body_options = ('file_name', 'keywords', 'lines', 'search_order', 'grep_scope', 'grep_line')
        if list_only and any(context.get_parameter_source(name) == click.core.ParameterSource.COMMANDLINE
                             for name in body_options):
            raise ValueError('--list 不能与文件、关键词、行数或正文检索选项同时使用')
        interactive = not no_input and can_prompt()
        runtime = runtime_from_context(context)

        def call(operation):
            def query(client):
                _selected_business(runtime, client)
                return operation(ServiceCatalog(client))
            with redirect_stdout(sys.stderr):
                return runtime.authenticated_call(query)

        hosts = all_hosts(lambda page: call(lambda service: service.list_hosts(service_id, page)))
        if pod is not None:
            hosts = [host for host in hosts if host.get('nodeName') == pod]
        host = choose(hosts, '主机', '--pod POD_NAME', interactive,
                      lambda h: f"{h.get('nodeName', '-')} · {h.get('clusterName', '-')} · "
                                f"{display_value('health_status', h)}")
        for key in ('nodeName', 'clusterName'):
            if not isinstance(host.get(key), str) or not host[key].strip():
                raise ApiError(f'主机缺少有效的 {key}')
        infra = host.get('infraType')
        if infra not in LOG_TYPES:
            raise ValueError(f'不支持的主机 infraType：{infra}')
        types = LOG_TYPES[infra]
        if log_type is None:
            log_type = choose(types, '日志类别', '--type TYPE', interactive, str)
        elif log_type not in types:
            raise ValueError(f'该主机不支持日志类别 {log_type}，可选：{", ".join(types)}')
        files = call(lambda service: service.list_pod_log_files(
            host['nodeName'], host['clusterName'], log_type, infra_type=infra))
        if list_only:
            console.print(file_table(files))
            if not files:
                console.print('暂无日志文件')
            return
        if not files and file_name is None:
            error_console.print('暂无日志文件')
            return
        if file_name is not None:
            files = [item for item in files if item.get('fileName') == file_name]
        if len(files) > 1 and interactive:
            error_console.print(file_table(files))
        selected = choose(files, '日志文件', '--file FILE_NAME', interactive,
                          lambda item: str(item.get('fileName', '-')))
        name = selected.get('fileName')
        if not isinstance(name, str) or not name.strip():
            raise ApiError('日志文件缺少有效的 fileName')
        error_console.print(Text(f"Pod：{host['nodeName']} · 文件：{name} · {search_order} {lines} 行"))
        content = call(lambda service: service.search_pod_log(
            host['nodeName'], host['clusterName'], log_type, name, keywords or [],
            lines, search_order, grep_scope, grep_line, infra_type=infra))
        typer.echo(content, nl=False)
    except (KeyboardInterrupt, EOFError, click.Abort):
        typer.echo('已取消', err=True)
        raise typer.Exit(130)
    except Exception as exc:
        fail(exc)
