"""日志阶段必须对应实际请求，并在失败和 JSON 摘要中保留定位信息。"""
import json
import re
from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from test_train_history_logs import invoke, response, roles, ROLE_ID
from wiserec_cli.errors import ApiError


def handler_for(*, distributed=False, missing=False, failure=None):
    checks = 0
    def handler(request):
        nonlocal checks
        action = request.url.path.rsplit('/', 1)[-1]
        if failure == action:
            return response(code=5, des='模拟接口失败')
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train' if distributed else 'train',
                                           'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            checks += 1
            return response(isExistLog=not missing or checks > 1)
        if action == 'manualArchiveLog':
            return response()
        assert action == 'downloadLogUrl'
        return response(url=None if failure == 'invalid_url' else 'https://files.example/log?signature=secret')
    return handler


@pytest.mark.parametrize('distributed', [False, True])
def test_archive_stages_order_and_json_separation(tmp_path, distributed):
    args = ['logs', 'download', 'task', 'job', '-o', 'json']
    if distributed:
        args += ['--role-job-id', ROLE_ID]
    result, download = invoke(tmp_path, handler_for(distributed=distributed, missing=True), args)
    assert result.exit_code == 1, result.output
    output = json.loads(result.stdout)
    summary = output['items'][0] if distributed else output
    assert summary['status'] == 'not_ready'
    assert summary['message'] == '手动归档中，请稍后再次下载日志！'
    download.assert_not_called()
    assert '开始' not in result.stdout and 'signature=secret' not in result.stdout
    stages = ['开始查询执行记录']
    if distributed:
        stages.append('已找到分布式训练记录，选择日志角色')
    stages += ['开始校验', '开始查询日志是否存在', '日志未就绪，准备手动归档',
               '手动归档中，请稍后再次下载日志！']
    numbered_lines = re.findall(r'^\[(\d+)\] (.*)$', result.stderr, re.M)
    assert [int(number) for number, _ in numbered_lines] == list(range(1, len(stages) + 1))
    for (_, line), stage in zip(numbered_lines, stages):
        assert line.startswith(stage)
    assert 'jobId=' not in result.stderr and 'roleJobId=' not in result.stderr


def test_archive_pending_is_red_in_color_terminal(tmp_path, monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    stream = StringIO()
    console = Console(file=stream, force_terminal=True, color_system='standard')
    with patch('wiserec_cli.messages.error_console', console):
        result, _ = invoke(tmp_path, handler_for(missing=True),
                           ['logs', 'download', 'task', 'job', '-o', 'json'])
    assert result.exit_code == 1
    assert re.search(r'\x1b\[31m\[\d+\] 手动归档中，请稍后再次下载日志！\x1b\[0m', stream.getvalue())
    assert json.loads(result.stdout)['status'] == 'not_ready'


@pytest.mark.parametrize('failure,stage,label', [
    ('queryJobLogIsExist', 'check_log', '查询日志是否存在'),
    ('manualArchiveLog', 'archive_log', '手动归档'),
    ('downloadLogUrl', 'get_download_url', '获取下载地址'),
    ('invalid_url', 'validate_download_url', '校验下载地址'),
    ('file', 'download_file', '下载日志文件'),
])
def test_failure_identifies_stage_and_does_not_announce_completion(tmp_path, failure, stage, label):
    result, download = invoke(tmp_path, handler_for(missing=failure == 'manualArchiveLog', failure=failure),
        ['logs', 'download', 'task', 'job', '-o', 'json'],
        download_error=ApiError('模拟文件下载失败') if failure == 'file' else None)
    assert result.exit_code == 1
    summary = json.loads(result.stdout)
    assert summary['stage'] == stage
    assert f'阶段「{label}」失败' in summary['error']
    assert f'阶段「{label}」失败' in result.stderr
    last_step = re.findall(r'^\[(\d+)\] ', result.stderr, re.M)[-1]
    assert summary['error'].startswith(f'[{last_step}] ')
    assert '日志下载完成' not in result.stderr
    if failure != 'file':
        download.assert_not_called()
        assert '开始下载日志' not in result.stderr


@pytest.mark.parametrize('call,stage', [(2, 'check_log'), (3, 'archive_log')])
def test_permission_502_identifies_pending_stage(tmp_path, call, stage):
    requests = []
    handler = handler_for(missing=True)

    def track(request):
        requests.append(request.url.path.rsplit('/', 1)[-1])
        return handler(request)

    result, download = invoke(tmp_path, track,
        ['logs', 'download', 'task', 'job', '-o', 'json'], permission_failure_at=call)
    assert result.exit_code == 1
    summary = json.loads(result.stdout)
    assert summary['stage'] == stage
    assert 'HTTP 502' in summary['error']
    download.assert_not_called()
    assert requests == ['queryScheduleTaskList', 'queryJobLogIsExist', 'manualArchiveLog'][:call - 1]


def test_lookup_permission_failure_identified_before_any_platform_request(tmp_path):
    result, download = invoke(tmp_path, lambda r: pytest.fail('must not request'),
        ['logs', 'download', 'task', 'job', '-o', 'json'], permission_failure_at=1)
    assert result.exit_code == 1
    assert '阶段「查询执行记录」失败' in result.stderr and 'HTTP 502' in result.stderr
    assert result.stdout == ''
    download.assert_not_called()


def test_ready_path_has_no_archive_or_wait_messages(tmp_path):
    result, _ = invoke(tmp_path, handler_for(), ['logs', 'download', 'task', 'job', '-o', 'json'])
    assert result.exit_code == 0
    assert '日志存在，开始获取日志下载地址' in result.stderr
    assert '归档' not in result.stderr and '等待日志就绪' not in result.stderr


def test_batch_steps_keep_numbering_across_roles(tmp_path):
    result, _ = invoke(tmp_path, handler_for(distributed=True),
                       ['logs', 'download', 'task', 'job', '-o', 'table'], interactive=True, input='all\n')
    assert result.exit_code == 0
    lines = re.findall(r'^\[(\d+)\] (.*)$', result.stderr, re.M)
    assert [int(number) for number, _ in lines] == list(range(1, len(lines) + 1))
    assert [line for _, line in lines if line.startswith('开始处理')] == [
        '开始处理第 1/2 条日志', '开始处理第 2/2 条日志',
    ]
    assert 'jobId=' not in result.stderr and 'roleJobId=' not in result.stderr
