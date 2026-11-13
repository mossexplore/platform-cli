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


STAGE_NAMES = {
    'query_record': '查询执行记录', 'select_role': '选择日志角色',
    'validate_role': '校验角色信息', 'check_log': '查询日志是否存在',
    'archive_log': '手动归档', 'wait_log': '等待日志就绪',
    'get_download_url': '获取下载地址', 'validate_download_url': '校验下载地址',
    'download_file': '下载日志文件',
}


class DownloadStages:
    """进度写入 stderr，保留当前阶段以标注失败原因。"""
    def __init__(self, label):
        self.label = label
        self.stage = 'query_record'

    def start(self, stage, message):
        self.stage = stage
        self.note(message)

    def note(self, message):
        msg.detail(f'[{self.label}] {message}')

    def error(self, exc):
        return f'[{self.label}] 阶段「{STAGE_NAMES[self.stage]}」失败：{exc}'


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


def ready_url(runtime, record, timeout, archives, stages=None):
    deadline = time.monotonic() + timeout
    job_id = record['jobId']
    stages = stages or DownloadStages(f'jobId={job_id}')
    attempt = 0
    while True:
        attempt += 1
        stages.start('check_log', f'准备第 {attempt} 次日志检查，正在检查访问权限')
        try:
            return runtime.authenticated_call(lambda client: HistoryLogService(client).download_url(
                record['taskId'], job_id, record.get('roleJobId'), on_stage=stages.start))
        except LogNotReady:
            stages.note('日志未就绪')
            if job_id not in archives:
                # 写操作结果不明时禁止重放；同一 job 的后续角色也不能再次提交。
                archives[job_id] = '归档请求结果未确认'
                stages.start('archive_log', '准备手动归档，正在检查访问权限')
                def archive(client):
                    stages.start('archive_log', '正在手动归档')
                    HistoryLogService(client).archive(job_id)
                try:
                    runtime.authenticated_call(archive, retry_auth=False)
                except Exception as exc:
                    archives[job_id] = str(exc)
                    raise
                archives[job_id] = None
                stages.note(f'作业 {job_id} 手动归档请求成功，等待日志就绪')
            elif archives[job_id] is not None:
                stages.start('archive_log', '同一作业此前归档请求未成功确认')
                raise ApiError(f'本次归档未成功确认，不重复提交：{archives[job_id]}')
            else:
                stages.note(f'作业 {job_id} 本次已提交归档，不重复提交')
            remaining = deadline - time.monotonic()
            stages.stage = 'wait_log'
            if remaining <= 0:
                raise LogNotReady('日志尚未就绪，已达到等待上限；请稍后重新执行下载命令')
            interval = min(5, remaining)
            stages.note(f'等待日志就绪，{interval:g} 秒后重查，剩余等待时间 {remaining:.0f} 秒')
            time.sleep(interval)


def download_history_logs(runtime, task_id, job_id, directory, output,
                          role_job_id=None, selection=None, wait_timeout=120):
    stages = DownloadStages(f'jobId={job_id}')
    stages.start('query_record', '开始查询执行记录（含权限检查）')
    try:
        with redirect_stdout(sys.stderr):
            record = runtime.authenticated_call(
                lambda client: HistoryLogService(client).find_record(task_id, job_id))
        distributed = record.get('jobType') == 'dps-train'
        stages.note('执行记录查询成功，任务类型：' + ('分布式训练' if distributed else '普通训练'))
        stages.stage = 'select_role'
        if distributed:
            stages.start('select_role', '开始选择日志角色')
            records = choose_roles(role_records(record), role_job_id, selection, output)
        else:
            if role_job_id is not None or selection is not None:
                raise ValueError('普通训练不支持 --role-job-id 或 --select')
            records = [{'taskId': task_id, 'jobId': job_id}]
        if not records:
            stages.note('已取消日志下载')
            return
        # 所有选中项先检查，避免参数错误时已经开始部分归档。
        stages.start('validate_role', f'开始校验 {len(records)} 条待下载日志的信息')
        for item in records:
            require_ids(item, distributed)
    except Exception as exc:
        raise ApiError(stages.error(exc)) from exc
    summaries, archives = [], {}
    for index, item in enumerate(records, 1):
        label = f'{index}/{len(records)} jobId={item["jobId"]}'
        if distributed:
            label += f' {item.get("roleType") or "角色"} roleJobId={item["roleJobId"]}'
        stages = DownloadStages(label)
        summary = {'taskId': item['taskId'], 'jobId': item['jobId']}
        if distributed:
            summary.update(roleJobId=item['roleJobId'], roleType=item.get('roleType'))
        try:
            with redirect_stdout(sys.stderr):
                url = ready_url(runtime, item, wait_timeout, archives, stages)
            msg.detail(f'下载地址：{url}')
            stages.start('download_file', '开始下载日志')
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
            stages.note(f'日志下载完成，保存到：{path}，共 {size} 字节')
        except Exception as exc:
            summary.update(status='not_ready' if isinstance(exc, LogNotReady) else 'failed',
                           stage=stages.stage, error=stages.error(exc))
            msg.error(summary['error'])
        summaries.append(summary)
    failed = sum(item['status'] != 'downloaded' for item in summaries)
    result = {'status': 'failed' if failed else 'downloaded', 'succeeded': len(summaries) - failed,
              'failed': failed, 'items': summaries} if distributed else summaries[0]
    print_result(result, output)
    if failed:
        raise typer.Exit(code=1)


def download_plog_logs(runtime, task_id, job_id, directory, output, downloader):
    from ..services.train import TrainService

    stages = DownloadStages(f'plog jobId={job_id}')
    stages.start('get_download_url', '开始获取 plog 下载地址（含权限检查及地址校验）')
    try:
        with redirect_stdout(sys.stderr):
            url = runtime.authenticated_call(lambda client: TrainService(client).get_plog_url(task_id, job_id))
        stages.note('plog 下载地址校验通过')
        msg.detail(f'下载地址：{url}')
        stages.start('download_file', '开始下载 plog 日志')
        with Progress(msg.MessageColumn(), BarColumn(), DownloadColumn(), console=error_console) as progress:
            progress_id = progress.add_task('下载 plog 日志', total=None)
            path, size = downloader(url, f'{job_id}-plog', directory=directory,
                progress=lambda done, total: progress.update(progress_id, completed=done, total=total))
        stages.note(f'plog 日志下载完成，保存到：{path}，共 {size} 字节')
        print_result({'taskId': task_id, 'jobId': job_id, 'path': str(path),
                      'bytes': size, 'status': 'downloaded'}, output)
    except Exception as exc:
        raise ApiError(stages.error(exc)) from exc
