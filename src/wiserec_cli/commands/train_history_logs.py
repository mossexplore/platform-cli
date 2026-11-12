"""执行记录日志选择、归档等待及批量下载。"""
from contextlib import redirect_stdout
import re
import sys
import time

import typer
from rich.progress import Progress, BarColumn, DownloadColumn

from .. import messages as msg
from ..downloads import download_file, download_filename
from ..errors import ApiError
from ..output import error_console, print_result
from ..services.train_history_logs import HistoryLogService, LogNotReady, require_ids, role_records
from .train_history_detail import show_roles


def select_roles(value, roles):
    if value.strip().lower() == 'all':
        return list(range(len(roles)))
    if not re.fullmatch(r'\s*[0-9]+\s*(,\s*[0-9]+\s*)*', value):
        raise ValueError('请输入有效编号，多个编号使用英文逗号分隔，例如 1,2')
    indices = list(dict.fromkeys(int(part.strip()) - 1 for part in value.split(',')))
    if any(index < 0 or index >= len(roles) for index in indices):
        raise ValueError('编号超出角色列表范围')
    return indices


def choose_roles(roles, role_job_id, selection, output):
    if not roles:
        raise ApiError('暂无角色信息，无法下载日志')
    if role_job_id is not None:
        matches = [role for role in roles if role.get('roleJobId') == role_job_id]
        if len(matches) != 1:
            raise ValueError('roleJobId 不属于当前执行记录或匹配了多条角色')
        return matches
    show_roles(roles, selection=True)
    if selection is not None:
        return [roles[index] for index in select_roles(selection, roles)]
    if output == 'json' or not sys.stdin.isatty():
        raise ValueError('非交互或 JSON 模式请指定 --role-job-id 或 --select')
    while True:
        value = typer.prompt('请输入角色编号，多个用英文逗号分隔；all 下载全部；q 取消', err=True)
        if value.strip().lower() == 'q':
            return []
        try:
            return [roles[index] for index in select_roles(value, roles)]
        except ValueError as exc:
            msg.error(str(exc))


def ready_url(runtime, record, timeout, archives):
    deadline = time.monotonic() + timeout
    job_id = record['jobId']
    while True:
        try:
            return runtime.authenticated_call(lambda client: HistoryLogService(client).download_url(
                record['taskId'], job_id, record.get('roleJobId')))
        except LogNotReady:
            if job_id not in archives:
                # 写操作结果不明时禁止重放；同一 job 的后续角色也不能再次提交。
                archives[job_id] = '归档请求结果未确认'
                try:
                    runtime.authenticated_call(
                        lambda client: HistoryLogService(client).archive(job_id), retry_auth=False)
                except Exception as exc:
                    archives[job_id] = str(exc)
                    raise
                archives[job_id] = None
                msg.detail(f'作业 {job_id} 已提交日志归档，等待日志就绪')
            elif archives[job_id] is not None:
                raise ApiError(f'本次归档未成功确认，不重复提交：{archives[job_id]}')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise LogNotReady('日志尚未就绪，已达到等待上限；请稍后重新执行下载命令')
            time.sleep(min(5, remaining))


def download_history_logs(runtime, task_id, job_id, directory, output,
                          role_job_id=None, selection=None, wait_timeout=120):
    with redirect_stdout(sys.stderr):
        record = runtime.authenticated_call(
            lambda client: HistoryLogService(client).find_record(task_id, job_id))
    distributed = record.get('jobType') == 'dps-train'
    if distributed:
        records = choose_roles(role_records(record), role_job_id, selection, output)
    else:
        if role_job_id is not None or selection is not None:
            raise ValueError('普通训练不支持 --role-job-id 或 --select')
        records = [{'taskId': task_id, 'jobId': job_id}]
    if not records:
        return
    # 所有选中项先检查，避免参数错误时已经开始部分归档。
    for item in records:
        require_ids(item, distributed)
    summaries, archives = [], {}
    for item in records:
        summary = {'taskId': item['taskId'], 'jobId': item['jobId']}
        if distributed:
            summary.update(roleJobId=item['roleJobId'], roleType=item.get('roleType'))
        try:
            with redirect_stdout(sys.stderr):
                url = ready_url(runtime, item, wait_timeout, archives)
            msg.detail(f'下载地址：{url}')
            with Progress(msg.MessageColumn(), BarColumn(), DownloadColumn(), console=error_console) as progress:
                progress_id = progress.add_task('下载日志', total=None)
                options = {'directory': directory}
                if distributed:
                    name = download_filename('', '-'.join(str(item.get(key) or '') for key in
                                                         ('jobId', 'roleType', 'roleJobId')))
                    options = {'destination': directory / name}
                path, size = download_file(url, item['jobId'], **options,
                    progress=lambda done, total: progress.update(progress_id, completed=done, total=total))
            summary.update(path=str(path), bytes=size, status='downloaded')
        except Exception as exc:
            summary.update(status='not_ready' if isinstance(exc, LogNotReady) else 'failed', error=str(exc))
            msg.error(str(exc))
        summaries.append(summary)
    failed = sum(item['status'] != 'downloaded' for item in summaries)
    result = {'status': 'failed' if failed else 'downloaded', 'succeeded': len(summaries) - failed,
              'failed': failed, 'items': summaries} if distributed else summaries[0]
    print_result(result, output)
    if failed:
        raise typer.Exit(code=1)
