"""历史日志完整请求链、角色选择及故障门禁。"""
import inspect
import json
from io import StringIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from cli_test_support import invoke_with_config
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.train_history_detail import show_roles, role_value
from wiserec_cli.commands.train_history_logs import ready_url
from wiserec_cli.errors import ApiError, AuthenticationError, BusinessError
from wiserec_cli.models import Credentials, Profile
from wiserec_cli.runtime import Runtime
from wiserec_cli.services.train import TrainService
from wiserec_cli.services.train_history_logs import HistoryLogService, LogNotReady


ROLE_ID = '50bd3610-7aeb-4844-b96f-45a787b5989d'


def roles():
    return [dict(roleJobId=ROLE_ID, roleType='worker', taskId='role-task', jobId='role-job',
                 algorithmName='file_tools_bj', status='COMPLETED', infraSize=1,
                 cpuSize=7, gpuSize=0, memorySize=50, hostIp='10.1.1.1', createTime=1793950592000),
            dict(roleJobId='server-id', roleType='server', taskId='role-task', jobId='role-job')]


def invoke(tmp_path, handler, args, platform='wiserec', **kwargs):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'profiles': [
        {'name': 'dev', 'platform_type': platform, 'api_endpoint': 'https://current.example'},
        {'name': 'other', 'api_endpoint': 'https://other.example'}]}))
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    def checked(request):
        assert request.url.host == 'current.example'
        assert request.headers['businessid'] == 'selected'
        return handler(request)
    with PlatformClient(Profile('dev', 'https://current.example', platform_type=platform),
                        Credentials.create('dev', 'cookie', 'csrf', 'user', 60), 1000, 0, True,
                        transport=httpx.MockTransport(checked),
                        business_selection=SimpleNamespace(business_id='selected')) as client:
        with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
             patch.object(runtime, 'authenticated_call', side_effect=lambda op, **kw: op(client)), \
             patch('wiserec_cli.commands.train_history_logs.download_file',
                   return_value=(tmp_path / 'log.zip', 12)) as download:
            runner = CliRunner(**({'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}))
            result = invoke_with_config(runner, app, config, ['train', 'history', *args], **kwargs)
    return result, download


def response(**result):
    return httpx.Response(200, json={'result': {'code': 0, **result}})


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
@pytest.mark.parametrize('distributed', [False, True])
def test_ready_logs_always_checked_before_url(tmp_path, platform, distributed):
    calls = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            body = json.loads(request.content)
            assert body['taskId'] == 'task' and body['source'] == 'history'
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train' if distributed else 'train',
                                            'roleJobInfo': roles()}])
        params = {'businessId': 'selected', 'jobId': 'role-job' if distributed else 'job'}
        if distributed:
            params['roleJobId'] = ROLE_ID
        if action == 'queryJobLogIsExist':
            assert dict(request.url.params) == params
            return response(isExistLog=True, failedUploadSwitch=False, extra='preserved')
        assert action == 'downloadLogUrl'
        params.update(taskId='role-task' if distributed else 'task', isApplicantPromise='true')
        assert dict(request.url.params) == params
        return response(url='https://files.example/log?signature=secret', des='ok')
    args = ['logs', 'download', 'task', 'job', '-o', 'json', '--directory', str(tmp_path)]
    if distributed:
        args += ['--role-job-id', ROLE_ID]
    result, download = invoke(tmp_path, handler, args, platform)
    assert result.exit_code == 0, result.output
    output = json.loads(result.stdout)
    item = output['items'][0] if distributed else output
    assert item['status'] == 'downloaded' and item['bytes'] == 12
    assert 'signature=secret' not in result.stdout
    assert calls == ['queryScheduleTaskList', 'queryJobLogIsExist', 'downloadLogUrl']
    assert download.call_count == 1
    if distributed:
        assert ROLE_ID in download.call_args.kwargs['destination'].name
    else:
        assert download.call_args.kwargs['directory'] == tmp_path


@pytest.mark.parametrize('missing', [{'isExistLog': False}, {'failedUploadSwitch': False}])
@pytest.mark.parametrize('distributed', [False, True])
def test_archive_then_poll_and_download(tmp_path, missing, distributed):
    calls, states = [], iter([missing, missing, {'isExistLog': True}])
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train' if distributed else 'train',
                                           'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            return response(**next(states))
        if action == 'manualArchiveLog':
            assert request.method == 'POST'
            body = json.loads(request.content)
            UUID(body['meta']['uuid'])
            assert body['version'] == '1.0'
            assert body['data'] == {'businessId': 'selected', 'jobId': 'role-job' if distributed else 'job'}
            return response()
        assert action == 'downloadLogUrl'
        return response(url='https://files.example/log')
    args = ['logs', 'download', 'task', 'job', '-o', 'json']
    if distributed:
        args += ['--select', '1']
    with patch('wiserec_cli.commands.train_history_logs.time.sleep') as sleep:
        result, download = invoke(tmp_path, handler, args)
    assert result.exit_code == 0, result.output
    assert calls == ['queryScheduleTaskList', 'queryJobLogIsExist', 'manualArchiveLog',
                     'queryJobLogIsExist', 'queryJobLogIsExist', 'downloadLogUrl']
    assert sleep.call_count == 2 and download.call_count == 1


def test_batch_timeout_deduplicates_archive_and_continues(tmp_path):
    calls = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            return response(isExistLog=False)
        assert action == 'manualArchiveLog'
        return response()
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job',
        '--select', 'all', '--wait-timeout', '0', '-o', 'json'])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert output['failed'] == 2
    assert all(item['status'] == 'not_ready' for item in output['items'])
    assert calls.count('manualArchiveLog') == 1
    download.assert_not_called()


def test_batch_archive_once_and_partial_download_failure(tmp_path):
    checks, calls = {}, []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            role_id = request.url.params['roleJobId']
            checks[role_id] = checks.get(role_id, 0) + 1
            return response(isExistLog=checks[role_id] > 1)
        if action == 'manualArchiveLog':
            return response()
        assert action == 'downloadLogUrl'
        if request.url.params['roleJobId'] == ROLE_ID:
            return response(code=5, des='日志获取失败')
        return response(url='https://files.example/log')
    with patch('wiserec_cli.commands.train_history_logs.time.sleep'):
        result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '--select', 'all', '-o', 'json'])
    assert result.exit_code == 1
    output = json.loads(result.stdout)
    assert (output['succeeded'], output['failed']) == (1, 1)
    assert calls.count('manualArchiveLog') == 1 and download.call_count == 1


@pytest.mark.parametrize('state', [{}, {'isExistLog': 'true'}, {'isExistLog': 1},
                                  {'failedUploadSwitch': True}, {'code': False}, {'code': 5}])
def test_unknown_or_failed_check_never_archives_or_downloads(tmp_path, state):
    calls = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'train'}])
        assert action == 'queryJobLogIsExist'
        return response(**state)
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '-o', 'json'])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['status'] == 'failed'
    assert calls == ['queryScheduleTaskList', 'queryJobLogIsExist']
    download.assert_not_called()


def test_archive_auth_failure_is_not_replayed_for_next_role():
    seen = []
    def authenticated(operation, **kwargs):
        seen.append(kwargs)
        if kwargs.get('retry_auth') is False:
            raise AuthenticationError('expired')
        raise LogNotReady('missing')
    runtime = SimpleNamespace(authenticated_call=authenticated)
    archives = {}
    with pytest.raises(AuthenticationError):
        ready_url(runtime, roles()[0], 120, archives)
    with pytest.raises(ApiError, match='不重复提交'):
        ready_url(runtime, roles()[1], 120, archives)
    assert seen == [{}, {'retry_auth': False}, {}]


@pytest.mark.parametrize('options', [['--select', '0'], ['--select', '3'], ['--select', '1，2'],
                                   ['--role-job-id', 'missing'], [], ['--select', '']])
def test_invalid_or_missing_selection_never_checks_logs(tmp_path, options):
    def handler(request):
        assert request.url.path.endswith('/queryScheduleTaskList')
        return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles()}])
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '-o', 'json', *options])
    assert result.exit_code != 0
    download.assert_not_called()


@pytest.mark.parametrize('options', [['--select', 'all', '--role-job-id', ROLE_ID],
    ['--type', 'plog', '--select', 'all'], ['--type', 'plog', '--role-job-id', ROLE_ID],
    ['--wait-timeout', '-1'], ['--role-job-id', ' ']])
def test_invalid_options_never_request(tmp_path, options):
    result, download = invoke(tmp_path, lambda r: pytest.fail('must not request'),
                             ['logs', 'download', 'task', 'job', *options])
    assert result.exit_code != 0
    download.assert_not_called()


@pytest.mark.parametrize('role_info', [None, {}, [], [None], [{'roleJobId': ROLE_ID}]])
def test_invalid_role_data_never_falls_back_to_parent(tmp_path, role_info):
    def handler(request):
        assert request.url.path.endswith('/queryScheduleTaskList')
        return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': role_info}])
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '--select', 'all'])
    assert result.exit_code != 0
    download.assert_not_called()


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
def test_detail_searches_pages_and_preserves_extra_fields(tmp_path, platform):
    pages = []
    record = {'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles(), 'futureField': {'x': 1}}
    def handler(request):
        assert request.url.path.endswith('/queryScheduleTaskList')
        page = json.loads(request.content)['pageIndex']
        pages.append(page)
        return response(count=201, jobs=[{'jobId': str(i)} for i in range(200)] if page == 1 else [record])
    result, _ = invoke(tmp_path, handler, ['detail', 'task', 'job', '-o', 'json'], platform)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == record
    assert pages == [1, 2]


def test_role_table_id_first_intact_on_narrow_terminal():
    stream = StringIO()
    console = Console(file=stream, width=40)
    data = roles()
    data[0]['algorithmName'] = 'long algorithm ' * 20
    with patch('wiserec_cli.commands.train_history_detail.console', console):
        show_roles(data)
    rendered = stream.getvalue()
    assert ROLE_ID in rendered
    assert '2026-11-06 15:36:32' in rendered
    assert rendered.index('角色作业 ID') < rendered.index('名称')
    assert role_value('gpuSize', 0) == '0'
    assert role_value('gpuSize', None) == '-'
    assert role_value('createTime', '2026-09-08T06:54:36.000+00:00') == '2026-09-08 14:54:36'


@pytest.mark.parametrize('url', [None, '', 'http://host/log', 'https://', 'https://user:pass@host/log'])
def test_legacy_service_entry_checks_before_invalid_download_url(url):
    calls = []
    def request(method, path, **kwargs):
        calls.append(path)
        return {'result': {'code': 0, 'isExistLog': True, 'url': url}}
    with pytest.raises(ApiError):
        TrainService(SimpleNamespace(business_id='selected', request=request)).get_log_url('t', 'j')
    assert [path.rsplit('/', 1)[-1] for path in calls] == ['queryJobLogIsExist', 'downloadLogUrl']


def test_missing_business_never_requests():
    client = SimpleNamespace(business_id='', request=lambda *a, **kw: pytest.fail('must not request'))
    with pytest.raises(BusinessError):
        HistoryLogService(client).download_url('t', 'j')


def test_wait_deadline_is_bounded_without_repeated_archive():
    operations = []
    def authenticated(operation, **kwargs):
        if kwargs.get('retry_auth') is False:
            operations.append('archive')
            return
        operations.append('check')
        raise LogNotReady('missing')
    with patch('wiserec_cli.commands.train_history_logs.time.monotonic', side_effect=[0, 0, 6]), \
         patch('wiserec_cli.commands.train_history_logs.time.sleep') as sleep:
        with pytest.raises(LogNotReady, match='等待上限'):
            ready_url(SimpleNamespace(authenticated_call=authenticated), roles()[0], 6, {})
    assert operations == ['check', 'archive', 'check']
    sleep.assert_called_once_with(5)


def test_check_repeated_for_each_url_and_ids_encoded():
    actions = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        actions.append(action)
        assert request.url.params['jobId'] == 'job & id'
        assert request.url.params['roleJobId'] == 'role & id'
        if action == 'queryJobLogIsExist':
            return response(isExistLog=True)
        assert request.url.params['taskId'] == 'task & id'
        return response(url='https://files.example/log')
    from test_client import PlatformClientTest
    with PlatformClientTest().create_client(handler) as client:
        service = HistoryLogService(client)
        for _ in range(2):
            assert service.download_url('task & id', 'job & id', 'role & id') == 'https://files.example/log'
    assert actions == ['queryJobLogIsExist', 'downloadLogUrl'] * 2


@pytest.mark.parametrize('code', [False, 5])
def test_failed_archive_cannot_download_or_repeat(tmp_path, code):
    calls = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        calls.append(action)
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            return response(isExistLog=False)
        assert action == 'manualArchiveLog'
        return response(code=code, des='归档失败')
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '--select', 'all', '-o', 'json'])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['failed'] == 2
    assert calls.count('manualArchiveLog') == 1
    download.assert_not_called()


@pytest.mark.parametrize('answer,expected', [('q\n', 0), ('0\n2,1,2\n', 2)])
def test_interactive_cancel_or_retry_and_preserve_selection_order(tmp_path, answer, expected):
    requested_roles = []
    def handler(request):
        action = request.url.path.rsplit('/', 1)[-1]
        if action == 'queryScheduleTaskList':
            return response(count=1, jobs=[{'jobId': 'job', 'jobType': 'dps-train', 'roleJobInfo': roles()}])
        if action == 'queryJobLogIsExist':
            requested_roles.append(request.url.params['roleJobId'])
            return response(isExistLog=True)
        assert action == 'downloadLogUrl'
        return response(url='https://files.example/log')
    with patch('wiserec_cli.commands.train_history_logs.sys.stdin.isatty', return_value=True):
        # CliRunner replaces stdin, so patch selection's TTY check at invocation time.
        from wiserec_cli.commands.train_history_logs import choose_roles
        def interactive(*args):
            with patch('sys.stdin.isatty', return_value=True):
                return choose_roles(*args)
        with patch('wiserec_cli.commands.train_history_logs.choose_roles', side_effect=interactive):
            result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'job', '-o', 'table'], input=answer)
    assert result.exit_code == 0, result.output
    assert download.call_count == expected
    assert requested_roles == (['server-id', ROLE_ID] if expected else [])


def test_record_not_found_never_checks_logs(tmp_path):
    def handler(request):
        assert request.url.path.endswith('/queryScheduleTaskList')
        return response(count=0, jobs=[])
    result, download = invoke(tmp_path, handler, ['logs', 'download', 'task', 'missing'])
    assert result.exit_code == 1 and '未找到执行记录' in result.output
    download.assert_not_called()
