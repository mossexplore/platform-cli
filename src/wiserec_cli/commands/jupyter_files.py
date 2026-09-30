"""面向人工及 Agent 的 Contents CLI。"""
import json
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import typer

from ..jupyter import files
from ..jupyter.connection import JupyterError

files_app = typer.Typer(no_args_is_help=True, help='远端单文件与目录操作（非交互）')


def output_result(client, result, output):
    from .jupyter import display_time
    def convert(value):
        if isinstance(value, dict):
            return {key: display_time(item) if key in {'created', 'last_modified'} else convert(item)
                    for key, item in value.items()}
        if isinstance(value, list):
            return [convert(item) for item in value]
        return value
    envelope = {'server_url': client.connection.url, 'studio_id': client.connection.studio_id,
                'business_id': client.connection.business_id, 'result': convert(result)}
    typer.echo(json.dumps(envelope if output == 'json' else envelope['result'],
                          ensure_ascii=False, indent=None if output == 'json' else 2))


@contextmanager
def operation(context, studio_id, output):
    from .jupyter import client_for
    if output not in {'text', 'json'}:
        raise typer.BadParameter('--output 仅支持 text 或 json')
    try:
        with client_for(context, studio_id, report=lambda _: None) as client:
            yield client
    except Exception as exc:
        if output == 'json':
            typer.echo(json.dumps({'status': 'FAILED', 'error': str(exc)}, ensure_ascii=False))
        else:
            typer.echo('错误：' + str(exc), err=True)
        raise typer.Exit(1)


@files_app.command('list')
def list_files(context: typer.Context, path: str = typer.Argument(''),
               output: str = typer.Option('text', '--output', '-o'),
               studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """列出目录的一层内容。"""
    with operation(context, studio_id, output) as client:
        model = files.get(client, path, content=True)
        if model['type'] != 'directory':
            raise JupyterError('list 目标必须是目录')
        output_result(client, model, output)


@files_app.command('stat')
def stat(context: typer.Context, path: str = typer.Argument(...),
         output: str = typer.Option('text', '--output', '-o'),
         studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """查询类型、大小、时间和可写性，不下载内容。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.get(client, path), output)


@files_app.command('read')
def read(context: typer.Context, path: str = typer.Argument(...),
         start_line: int = typer.Option(1, '--start-line', min=1),
         end_line: Optional[int] = typer.Option(None, '--end-line', min=1),
         output: str = typer.Option('text', '--output', '-o'),
         studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """读取 UTF-8 文本；行范围含首尾，底层下载完整文件。"""
    with operation(context, studio_id, output) as client:
        if end_line is not None and end_line < start_line:
            raise JupyterError('--end-line 不能小于 --start-line')
        model = files.get(client, path, content=True, format='text')
        content = model['content']
        text = ''.join(content) if isinstance(content, list) else content
        text = ''.join(text.splitlines(keepends=True)[start_line - 1:end_line])
        if output == 'json':
            output_result(client, {'path': path, 'content': text, 'start_line': start_line, 'end_line': end_line}, output)
        else:
            from .jupyter import _CONTROL
            typer.echo(_CONTROL.sub('', text), nl=False)


@files_app.command('write')
def write(context: typer.Context, path: str = typer.Argument(...),
          from_file: Optional[Path] = typer.Option(None, '--from-file', exists=True, dir_okay=False),
          stdin: bool = typer.Option(False, '--stdin'),
          overwrite: bool = typer.Option(False, '--overwrite'),
          output: str = typer.Option('text', '--output', '-o'),
          studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """从本地 UTF-8 文件或标准输入写入远端文件。"""
    with operation(context, studio_id, output) as client:
        if (from_file is None) == (not stdin):
            raise JupyterError('--from-file 与 --stdin 必须且只能指定一个')
        data = sys.stdin.read().encode('utf-8') if stdin else from_file.read_bytes()
        output_result(client, files.save(client, path, data, overwrite, text=True), output)


@files_app.command('mkdir')
def mkdir(context: typer.Context, path: str = typer.Argument(...),
          output: str = typer.Option('text', '--output', '-o'),
          studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """创建一个目录，父目录必须存在。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.mkdir(client, path), output)


@files_app.command('upload')
def upload(context: typer.Context, local: Path = typer.Argument(..., exists=True, dir_okay=False),
           remote: str = typer.Argument(...), overwrite: bool = typer.Option(False, '--overwrite'),
           output: str = typer.Option('text', '--output', '-o'),
           studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """上传单文件（含二进制），REMOTE 必须含目标文件名。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.save(client, remote, local.read_bytes(), overwrite), output)


@files_app.command('download')
def download(context: typer.Context, remote: str = typer.Argument(...),
             local: Path = typer.Argument(...), overwrite: bool = typer.Option(False, '--overwrite'),
             output: str = typer.Option('text', '--output', '-o'),
             studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """下载单文件，LOCAL 必须含目标文件名，父目录必须存在。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.download(client, remote, local, overwrite), output)


@files_app.command('move')
def move(context: typer.Context, source: str = typer.Argument(...), target: str = typer.Argument(...),
         output: str = typer.Option('text', '--output', '-o'),
         studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """移动或重命名，不覆盖目标。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.move(client, source, target), output)


@files_app.command('copy')
def copy(context: typer.Context, source: str = typer.Argument(...), target_dir: str = typer.Argument(...),
         output: str = typer.Option('text', '--output', '-o'),
         studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """复制单文件至已有目录；新文件名由 Jupyter 决定。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.copy(client, source, target_dir), output)


@files_app.command('delete')
def delete(context: typer.Context, path: str = typer.Argument(...),
           output: str = typer.Option('text', '--output', '-o'),
           studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """显式删除文件或空目录，不递归、不交互确认。"""
    with operation(context, studio_id, output) as client:
        output_result(client, files.delete(client, path), output)
