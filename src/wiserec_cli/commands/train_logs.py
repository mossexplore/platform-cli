"""执行实例日志的列表、编号选择与批量下载。"""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import re
import sys

import typer
from rich.progress import Progress, BarColumn, DownloadColumn
from rich.text import Text

from .. import messages as msg
from ..downloads import download_file, download_filename, download_directory
from ..output import error_console, print_result
from ..services.train_logs import RunningLogService
from .common import fail, runtime_from_context


instance_logs_app = typer.Typer(no_args_is_help=True, help='执行实例日志归档与下载')


def select_logs(value, items):
    if '，' in value:
        raise ValueError('检测到中文逗号，请使用英文逗号，例如 1,2,3')
    parts = value.split(',')
    if not all(re.fullmatch(r'[0-9]+', part.strip()) for part in parts):
        raise ValueError('请输入有效编号，多个编号使用英文逗号分隔，例如 1,2,3')
    indices = list(dict.fromkeys(int(part.strip()) for part in parts))
    if any(index < 1 or index > len(items) for index in indices):
        raise ValueError('编号超出列表范围，请重新输入')
    unavailable = [str(index) for index in indices if type(items[index - 1].get('status')) is not int
                   or items[index - 1]['status'] != 1]
    if unavailable:
        raise ValueError(f"编号 {','.join(unavailable)} 尚未归档成功，不能下载，请重新选择")
    return indices


def show_logs(items):
    # 详情块避免长 ID 在窄终端的多列表格中被截断或折行。
    for index, item in enumerate(items, 1):
        status = item.get('status')
        label = f'未知状态（{status}）'
        if type(status) is int:
            label = {0: '归档中', 1: '归档成功'}.get(status, label)
        error_console.print(Text(f"[{index}] 任务名称：{item.get('taskName', '-')}"))
        for title, field in [('jobId', 'jobId'), ('roleJobId', 'roleJobId'),
                             ('节点名称', 'roleType')]:
            error_console.print(Text(f"{title}：{item.get(field, '-')}"), soft_wrap=True)
        error_console.print(Text(f'状态：{label}'))
        for title, field in [('开始时间', 'createTime'), ('结束时间', 'updateTime')]:
            value = item.get(field)
            rendered = '-'
            if type(value) in (int, float):
                try:
                    rendered = datetime.fromtimestamp(value / 1000, timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                except (ValueError, OverflowError, OSError):
                    pass
            error_console.print(Text(f'{title}：{rendered}'))


@instance_logs_app.command('download')
def download_running_logs(
    context: typer.Context,
    task_id: str = typer.Argument(..., help='训练任务 ID'),
    job_id: str = typer.Argument(..., help='执行实例作业 ID'),
    directory: Optional[Path] = typer.Option(None, '--directory', help='已存在的保存目录，默认当前目录'),
    output: Optional[str] = typer.Option(None, '--output', '-o', help='结果摘要格式: table 或 json'),
):
    """归档并下载执行实例日志"""
    try:
        task_id, job_id = task_id.strip(), job_id.strip()
        if not task_id or not job_id:
            raise ValueError('taskId 和 jobId 不能为空')
        directory = download_directory(directory)
        runtime = runtime_from_context(context)
        selected = (output or runtime.config.current_profile().output_format).lower()
        if selected not in {'table', 'json'}:
            raise ValueError('output 仅支持 table 或 json')
        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(lambda client: RunningLogService(client).archive(task_id, job_id))
        items = result['logInfoList']
        if not items:
            msg.detail('日志归档中，请稍后执行下载命令！')
            if selected == 'json':
                print_result({'status': 'archiving', 'count': 0, 'items': []}, selected)
            return
        show_logs(items)
        if not any(type(item.get('status')) is int and item['status'] == 1 for item in items):
            msg.detail('暂无可下载的日志，请稍后执行下载命令！')
            if selected == 'json':
                print_result({'status': 'unavailable', 'count': len(items), 'items': items}, selected)
            return
        while True:
            with redirect_stdout(sys.stderr):
                value = typer.prompt('请输入日志编号，多个用英文逗号分隔，例如 1,2,3；输入 q 取消', err=True)
            if value.strip().lower() == 'q':
                return
            try:
                indices = select_logs(value, items)
                break
            except ValueError as exc:
                msg.error(exc)
        summaries = []
        for index in indices:
            record = items[index - 1]
            summary = {'number': index, 'taskName': record['taskName'],
                       'jobId': record['jobId'], 'roleJobId': record.get('roleJobId')}
            try:
                with redirect_stdout(sys.stderr):
                    url = runtime.authenticated_call(lambda client: RunningLogService(client).download_url(record))
                msg.detail(f'[{index}] OBS 下载链接：{url}')
                # 显式、安全命名，区分任务、节点和不同归档；所有文件保存为 ZIP。
                name = download_filename('', '-'.join(str(record.get(key, '')) for key in
                    ('taskName', 'roleType', 'roleJobId', 'archiveId')))
                with Progress(msg.MessageColumn(), BarColumn(), DownloadColumn(), console=error_console) as progress:
                    progress_id = progress.add_task(f'下载日志 [{index}]', total=None)
                    path, size = download_file(url, record['jobId'], directory / name,
                        progress=lambda done, total: progress.update(progress_id, completed=done, total=total))
                summary.update(status='downloaded', path=str(path), bytes=size)
            except Exception as exc:
                msg.error(f'[{index}] {exc}')
                summary.update(status='failed', error=str(exc))
            summaries.append(summary)
        failed = sum(item['status'] == 'failed' for item in summaries)
        print_result({'status': 'failed' if failed else 'downloaded',
                      'succeeded': len(summaries) - failed, 'failed': failed, 'items': summaries}, selected)
        if failed:
            raise typer.Exit(code=1)
    except typer.Exit:
        raise
    except Exception as exc:
        fail(exc)
