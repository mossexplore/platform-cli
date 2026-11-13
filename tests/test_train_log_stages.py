"""日志阶段必须对应实际请求，并在失败和 JSON 摘要中保留定位信息。"""
import json
from unittest.mock import patch

import pytest

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
    with patch('wiserec_cli.commands.train_history_logs.time.sleep'):
        result, _ = invoke(tmp_path, handler_for(distributed=distributed, missing=True), args)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['status'] == 'downloaded'
    assert '开始' not in result.stdout and 'signature=secret' not in result.stdout
    stages = ['开始查询执行记录', '执行记录查询成功', '开始查询日志是否存在', '日志未就绪',
              '正在手动归档', '手动归档请求成功', '等待日志就绪，', '准备第 2 次日志检查',
              '开始查询日志是否存在', '日志已就绪', '开始获取日志下载地址',
              '开始校验下载地址', '下载地址校验通过', '开始下载日志', '日志下载完成']
    offset = 0
    for stage in stages:
        offset = result.stderr.index(stage, offset) + len(stage)
    if distributed:
        assert f'worker roleJobId={ROLE_ID}' in result.stderr


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
    assert '日志下载完成' not in result.stderr
    if failure != 'file':
        download.assert_not_called()
        assert '开始下载日志' not in result.stderr


@pytest.mark.parametrize('call,stage', [(2, 'check_log'), (3, 'archive_log'), (4, 'check_log')])
def test_permission_502_identifies_pending_stage(tmp_path, call, stage):
    with patch('wiserec_cli.commands.train_history_logs.time.sleep'):
        result, download = invoke(tmp_path, handler_for(missing=True),
            ['logs', 'download', 'task', 'job', '-o', 'json'], permission_failure_at=call)
    assert result.exit_code == 1
    summary = json.loads(result.stdout)
    assert summary['stage'] == stage
    assert 'HTTP 502' in summary['error']
    download.assert_not_called()
    if call == 2:
        assert '开始查询日志是否存在' not in result.stderr
    if call == 3:
        assert '正在手动归档' not in result.stderr


def test_lookup_permission_failure_identified_before_any_platform_request(tmp_path):
    result, download = invoke(tmp_path, lambda r: pytest.fail('must not request'),
        ['logs', 'download', 'task', 'job', '-o', 'json'], permission_failure_at=1)
    assert result.exit_code == 1
    assert '阶段「查询执行记录」失败' in result.stderr and 'HTTP 502' in result.stderr
    assert result.stdout == ''
    download.assert_not_called()


def test_no_wait_has_distinct_wait_stage_and_no_download(tmp_path):
    result, download = invoke(tmp_path, handler_for(missing=True),
        ['logs', 'download', 'task', 'job', '--wait-timeout', '0', '-o', 'json'])
    assert result.exit_code == 1
    summary = json.loads(result.stdout)
    assert summary['stage'] == 'wait_log' and summary['status'] == 'not_ready'
    assert '阶段「等待日志就绪」失败' in result.stderr
    assert '开始下载日志' not in result.stderr
    download.assert_not_called()


def test_ready_path_has_no_archive_or_wait_messages(tmp_path):
    result, _ = invoke(tmp_path, handler_for(), ['logs', 'download', 'task', 'job', '-o', 'json'])
    assert result.exit_code == 0
    assert '日志已就绪' in result.stderr
    assert '归档' not in result.stderr and '等待日志就绪' not in result.stderr


def test_batch_messages_identify_each_role(tmp_path):
    result, _ = invoke(tmp_path, handler_for(distributed=True),
                       ['logs', 'download', 'task', 'job', '--select', 'all', '-o', 'json'])
    assert result.exit_code == 0
    for label in (f'1/2 jobId=role-job worker roleJobId={ROLE_ID}', '2/2 jobId=role-job server roleJobId=server-id'):
        assert f'[{label}] 开始查询日志是否存在' in result.stderr
        assert f'[{label}] 开始下载日志' in result.stderr
