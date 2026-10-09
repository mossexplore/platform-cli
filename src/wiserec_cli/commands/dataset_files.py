"""查看数据集目录并向目录追加单个文件。"""

import sys
from contextlib import redirect_stdout
from pathlib import Path
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from ..output import console, error_console, print_result
from ..services.dataset_files import DatasetFilesService, child_path, normalize_dir, validate_file
from .common import fail, runtime_from_context
from .dataset import _selected_business, _selected_output, _size, _time

files_app = typer.Typer(no_args_is_help=True, help='管理数据集目录和文件')


def render_files(payload, directory, output):
    info = payload['result']['fileInfos']
    if output == 'json':
        print_result({'currentDir': directory, 'response': payload}, output)
    else:
        console.print(Text(f'当前位置：{directory}'))
        table = Table('类别', '文件名', '更新时间', '文件大小', '完整路径')
        for item in info['files']:
            table.add_row(Text('文件夹' if item['dir'] else '文件'), Text(item['name']),
                Text(_time(item['lastModifyDate']) if item.get('lastModifyDate') is not None else '-'),
                Text(_size(item['size']) if item.get('size') is not None else '-'),
                Text(child_path(directory, item['path'])))
        console.print(table)
        if not info['files']:
            console.print('当前目录为空')
        console.print('时间：Asia/Shanghai (UTC+08:00)')
    if info['hasMore']:
        error_console.print('警告：当前结果不完整，接口分页规则尚未提供')


@files_app.command('list')
def list_files(context: typer.Context,
    dataset_id: str = typer.Argument(..., help='数据集 ID'),
    directory: str = typer.Option('/', '--dir', help='数据集内部目录'),
    output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """查看指定目录内容"""
    try:
        directory = normalize_dir(directory)
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)
        def query(client):
            _selected_business(runtime, client)
            return DatasetFilesService(client).list_files(dataset_id, directory)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(query)
        render_files(payload, directory, selected)
    except Exception as exc:
        fail(exc)


@files_app.command('upload')
def upload(context: typer.Context,
    dataset_id: str = typer.Argument(..., help='数据集 ID'),
    local_file: Path = typer.Argument(..., help='本地单个文件路径'),
    directory: str = typer.Option('/', '--dir', help='数据集内部目标目录'),
    timeout: float = typer.Option(1800, '--timeout', min=1, help='上传网络操作超时秒数'),
    output: Optional[str] = typer.Option(None, '--output', '-o', help='table 或 json')):
    """向指定目录追加文件"""
    try:
        validate_file(local_file)
        directory = normalize_dir(directory)
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)
        def send(client):
            _selected_business(runtime, client)
            return DatasetFilesService(client).upload(dataset_id, local_file, directory, timeout)
        with redirect_stdout(sys.stderr):
            payload = runtime.authenticated_call(send, retry_auth=False)
        if selected == 'json':
            print_result(payload, selected)
        else:
            console.print(Text(f'追加文件请求成功：{local_file.name}'))
            console.print(Text(f'当前位置：{directory}'))
            console.print('可使用 files list 查询目录确认文件处理结果')
    except Exception as exc:
        fail(exc)
