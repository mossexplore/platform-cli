"""执行记录日志选择、归档等待及批量下载。"""
from contextlib import redirect_stdout
import re
import sys

import typer
from rich.progress import Progress, BarColumn, DownloadColumn

from .. import messages as msg
from ..downloads import download_file, download_filename, zip_filename
from ..errors import ApiError
from ..output import error_console, print_result
from ..services.train import TrainService
from ..services.train_history_logs import HistoryLogService, LogNotReady, has_plog, require_ids, role_records
from .train_history_detail import show_roles


STAGE_NAMES = {
    'query_record': '查询执行记录', 'select_role': '选择日志角色',
    'validate_role': '校验角色信息', 'check_log': '查询日志是否存在',
    'archive_log': '手动归档',
    'get_download_url': '获取下载地址', 'validate_download_url': '校验下载地址',
    'download_file': '下载日志文件',
}
NO_PLOG = '该记录没有plog日志，停止下载'


class DownloadStages:
    """进度写入 stderr，保留当前阶段以标注失败原因。"""
    def __init__(self):
        self.number = 0
        self.stage = 'query_record'

    def start(self, stage, message=None, *, style=''):
        self.number += 1
        self.stage = stage
        if message:
            msg.detail(f'[{self.number}] {message}', style=style)

    def note(self, message):
        self.start(self.stage, message)

    def error(self, exc):
        return f'[{self.number}] 阶段「{STAGE_NAMES[self.stage]}」失败：{exc}'


def select_roles(value, roles, *, plog=False):
    if value.strip().lower() == 'all':
        return [index for index, role in enumerate(roles) if not plog or has_plog(role)]
    if not re.fullmatch(r'\s*[0-9]+\s*(,\s*[0-9]+\s*)*', value):
        raise ValueError('请输入有效编号，多个编号使用英文逗号分隔，例如 1,2')
    indices = list(dict.fromkeys(int(part.strip()) - 1 for part in value.split(',')))
    if any(index < 0 or index >= len(roles) for index in indices):
        raise ValueError('编号超出角色列表范围')
    return indices


def choose_roles(roles, role_job_id, output, *, plog=False):
    if plog and not any(has_plog(role) for role in roles):
        raise ApiError(NO_PLOG)
    if not roles:
        raise ApiError('暂无角色信息，无法下载日志')
    if role_job_id is not None:
        matches = [role for role in roles if role.get('roleJobId') == role_job_id]
        if len(matches) != 1:
            raise ValueError('roleJobId 不属于当前执行记录或匹配了多条角色')
        return matches
    if output == 'json' or not sys.stdin.isatty():
        raise ValueError('非交互或 JSON 模式请指定 --role-job-id')
    show_roles(roles, selection=True, plog=plog)
    while True:
        all_label = '全部可下载 plog' if plog else '全部'
        value = typer.prompt(f'请输入角色编号，多个用英文逗号分隔；all 下载{all_label}；q 取消', err=True)
        if value.strip().lower() == 'q':
            return []
        try:
            return [roles[index] for index in select_roles(value, roles, plog=plog)]
        except ValueError as exc:
            msg.error(str(exc))


def ready_url(runtime, record, archives, stages=None):
    job_id = record['jobId']
    stages = stages or DownloadStages()

    def report(stage, message):
        # 首次查询已在权限检查前提示。认证重试回到查询阶段时再次提示。
        if stage != 'check_log' or stages.stage != 'check_log':
            stages.start(stage, message)

    stages.start('check_log', '开始查询日志是否存在')
    try:
        return runtime.authenticated_call(lambda client: HistoryLogService(client).download_url(
            record['taskId'], job_id, record.get('roleJobId'), on_stage=report))
    except LogNotReady as exc:
        if job_id not in archives:
            # 同一命令内，写操作结果未确认时也不重新提交。
            stages.start('archive_log', f'{exc}，准备手动归档')
            try:
                runtime.authenticated_call(
                    lambda client: HistoryLogService(client).archive(job_id), retry_auth=False)
            except Exception as exc:
                archives[job_id] = str(exc)
                raise
            archives[job_id] = None
        elif archives[job_id] is not None:
            stages.start('archive_log')
            raise ApiError(f'本次归档未成功确认，不重复提交：{archives[job_id]}')
        return None


def download_history_logs(runtime, task_id, job_id, directory, output,
                          role_job_id=None, *, log_type='log'):
    plog = log_type == 'plog'
    stages = DownloadStages()
    stages.start('query_record', '开始查询执行记录')
    try:
        with redirect_stdout(sys.stderr):
            record = runtime.authenticated_call(
                lambda client: HistoryLogService(client).find_record(task_id, job_id))
        distributed = record.get('jobType') == 'dps-train'
        if distributed:
            stages.start('select_role', '已找到分布式训练记录，选择日志角色')
            records = choose_roles(role_records(record), role_job_id, output, plog=plog)
        else:
            if role_job_id is not None:
                stages.start('select_role')
                raise ValueError('普通训练不支持 --role-job-id')
            records = [{'taskId': task_id, 'jobId': job_id}]
        if not records:
            stages.note('已取消日志下载')
            return
        # 所有选中项先检查，避免参数错误时已经开始部分归档。
        stages.start('validate_role', f'开始校验 {len(records)} 条待下载日志的信息')
        plog_records = records if distributed else [record]
        if plog and not all(has_plog(item) for item in plog_records):
            raise ApiError(NO_PLOG)
        for item in records:
            require_ids(item, distributed)
    except Exception as exc:
        raise ApiError(stages.error(exc)) from exc
    summaries, archives = [], {}
    log_label = 'plog 日志' if plog else '日志'
    download_label = '下载 plog 日志' if plog else '下载日志'
    for index, item in enumerate(records, 1):
        if len(records) > 1:
            stages.note(f'开始处理第 {index}/{len(records)} 条日志')
        summary = {'taskId': item['taskId'], 'jobId': item['jobId']}
        if distributed:
            summary.update(roleJobId=item['roleJobId'], roleType=item.get('roleType'))
        try:
            with redirect_stdout(sys.stderr):
                if plog:
                    stages.start('get_download_url', '开始获取 plog 下载地址')
                    url = runtime.authenticated_call(lambda client: TrainService(client).get_plog_url(
                        item['taskId'], item['jobId'], item.get('roleJobId')))
                else:
                    url = ready_url(runtime, item, archives, stages)
            if url is None:
                message = '手动归档中，请稍后再次下载日志！'
                stages.start('archive_log', message, style='red')
                summaries.append({**summary, 'status': 'not_ready', 'stage': stages.stage, 'message': message})
                continue
            msg.detail(f'下载地址：{url}')
            stages.start('download_file', f'开始{download_label}')
            with Progress(msg.MessageColumn(), BarColumn(), DownloadColumn(), console=error_console) as progress:
                progress_id = progress.add_task(download_label, total=None)
                options = {'directory': directory}
                if distributed and plog:
                    name = zip_filename(f"{item['roleJobId']}_plog.zip")
                    options = {'destination': directory / name}
                elif distributed:
                    parts = [str(item.get(key) or '') for key in ('jobId', 'roleType', 'roleJobId')]
                    options = {'destination': directory / download_filename('', '-'.join(parts))}
                download_id = f"{item['jobId']}-plog" if plog else item['jobId']
                path, size = download_file(url, download_id, **options,
                    progress=lambda done, total: progress.update(progress_id, completed=done, total=total))
            summary.update(path=str(path), bytes=size, status='downloaded')
            stages.note(f'{log_label}下载完成，保存到：{path}，共 {size} 字节')
        except Exception as exc:
            summary.update(status='failed', stage=stages.stage, error=stages.error(exc))
            msg.error(summary['error'])
        summaries.append(summary)
    failed = sum(item['status'] != 'downloaded' for item in summaries)
    result = {'status': 'failed' if failed else 'downloaded', 'succeeded': len(summaries) - failed,
              'failed': failed, 'items': summaries} if distributed else summaries[0]
    print_result(result, output)
    if failed:
        raise typer.Exit(code=1)
