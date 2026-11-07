"""两平台归档/下载请求契约、交互校验和批量失败行为。"""
import inspect
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.runtime import Runtime
from wiserec_cli.services.train import TrainService
from wiserec_cli.services.train_logs import RunningLogService
from wiserec_cli.commands.train_logs import select_logs
from wiserec_cli.downloads import download_file
from wiserec_cli.errors import ApiError, BusinessError


RECORD = dict(businessId='selected', taskId='task', jobId='job', taskName='warmup',
              roleJobId='role', archiveId='archive', createUser='owner', roleType='server',
              status=1, createTime=1794014185000, updateTime=1794014210000)


def runner():
    return CliRunner(**({'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}))


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
def test_full_cli_contract(tmp_path, platform):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'profiles': [{'name': 'dev',
        'platform_type': platform, 'api_endpoint': 'https://current.example'}]}))
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    requests = []
    def handler(request):
        assert request.method == 'POST'
        assert request.url.host == 'current.example'
        assert request.headers['businessid'] == 'selected'
        body = json.loads(request.content)
        UUID(body['meta']['uuid'])
        assert body['version'] == '1.0' and body['eventTarget'] == 'warmup'
        requests.append(request.url.path)
        if request.url.path.endswith('getRunJobLogArchiveList'):
            assert body['data'] == {k: RECORD[k] for k in ('businessId', 'jobId', 'taskId')}
            return httpx.Response(200, json={'result': dict(code=0, count=2,
                logInfoList=[RECORD, dict(RECORD, roleJobId='role2', archiveId='archive2')], extra='retained')})
        assert request.url.path.endswith('getRunningJobLogUrl')
        expected = {k: RECORD[k] for k in ('businessId', 'taskId', 'jobId', 'roleJobId', 'archiveId', 'createUser')}
        if len(requests) == 3:
            expected.update(roleJobId='role2', archiveId='archive2')
        assert body['data'] == dict(expected, isApplicantPromise=True, isUpload=False)
        return httpx.Response(200, json={'result': {'code': 0, 'downloadUrl': 'https://files.example/log'}})
    with PlatformClient(Profile('dev', 'https://current.example', platform_type=platform),
                        Credentials.create('dev', 'cookie', 'csrf', 'user', 60), 1000, 0, True,
                        transport=httpx.MockTransport(handler),
                        business_selection=SimpleNamespace(business_id='selected')) as client:
        with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
             patch.object(runtime, 'authenticated_call', side_effect=lambda op: op(client)), \
             patch.object(TrainService, 'find_task', return_value={'taskId': 'task'}), \
             patch.object(TrainService, 'all_instances', return_value=[RECORD]), \
             patch('wiserec_cli.commands.train_logs.download_file', return_value=(tmp_path/'result.zip', 12)) as download:
            result = runner().invoke(app, ['--config', str(config), 'train', 'instance', 'logs',
                'download', 'task', 'job', '--directory', str(tmp_path), '-o', 'json'], input='1，2\n1,1,2\n')
    assert result.exit_code == 0, result.output
    summary = json.loads(result.stdout)
    assert summary['succeeded'] == 2 and summary['failed'] == 0
    assert download.call_count == 2
    assert all(call.args[2].parent == tmp_path and call.args[2].suffix == '.zip' for call in download.call_args_list)
    assert '中文逗号' in result.stderr and '2026-11-07 09:16:25' in result.stderr
    assert '2026-11-07 09:16:50' in result.stderr and 'OBS 下载链接' in result.stderr


@pytest.mark.parametrize('value', ['1，2', '0', '3', '1,,2', '1,a', '', '-1', '1,2'])
def test_selection_rejects_invalid_and_unavailable(value):
    with pytest.raises(ValueError):
        select_logs(value, [RECORD, dict(RECORD, status=0)])


def test_selection_deduplicates_and_rejects_unknown_status():
    assert select_logs(' 1,1 ', [RECORD]) == [1]
    for status in [True, '1', 2, None, []]:
        with pytest.raises(ValueError):
            select_logs('1', [dict(RECORD, status=status)])


@pytest.mark.parametrize('items,count', [([], 1), ([RECORD], 0), (None, 0), ([None], 1), ([], True)])
def test_malformed_archives(items, count):
    client = SimpleNamespace(business_id='selected', request=lambda *a, **kw:
        {'result': dict(code=0, count=count, logInfoList=items)})
    with patch.object(TrainService, 'find_task', return_value={}), \
         patch.object(TrainService, 'all_instances', return_value=[RECORD]):
        with pytest.raises(ApiError):
            RunningLogService(client).archive('task', 'job')


@pytest.mark.parametrize('changes', [{'status': 0}, {'status': True}, {'createUser': ''},
                                     {'businessId': 'other'}, {'archiveId': None}])
def test_unavailable_or_incomplete_download_never_requests(changes):
    client = SimpleNamespace(business_id='selected', request=lambda *a, **kw: pytest.fail('must not request'))
    with pytest.raises((ApiError, BusinessError)):
        RunningLogService(client).download_url(dict(RECORD, **changes))


@pytest.mark.parametrize('items', [[], [dict(RECORD, status=0)], [dict(RECORD, status=9)]])
def test_no_downloadable_logs_never_prompts(tmp_path, items):
    runtime = SimpleNamespace(config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format='json')),
                              authenticated_call=lambda op: dict(count=len(items), logInfoList=items))
    with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
         patch('wiserec_cli.commands.train_logs.runtime_from_context', return_value=runtime), \
         patch('wiserec_cli.commands.train_logs.typer.prompt', side_effect=AssertionError('must not prompt')):
        result = runner().invoke(app, ['train', 'instance', 'logs', 'download', 't', 'j',
                                     '--directory', str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['status'] in {'archiving', 'unavailable'}
    if not items:
        assert '日志归档中，请稍后执行下载命令！' in result.stderr


def test_batch_failure_continues(tmp_path):
    runtime = SimpleNamespace(config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format='json')))
    runtime.authenticated_call = lambda op: op(SimpleNamespace())
    with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
         patch('wiserec_cli.commands.train_logs.runtime_from_context', return_value=runtime), \
         patch.object(RunningLogService, 'archive', return_value={'logInfoList': [RECORD, RECORD]}), \
         patch.object(RunningLogService, 'download_url', return_value='https://files.example/log'), \
         patch('wiserec_cli.commands.train_logs.download_file', side_effect=[ApiError('failed'), (tmp_path/'ok.zip', 10)]) as download:
        result = runner().invoke(app, ['train', 'instance', 'logs', 'download', 't', 'j'], input='1,2\n')
    assert result.exit_code == 1 and download.call_count == 2
    summary = json.loads(result.stdout)
    assert summary['failed'] == summary['succeeded'] == 1


def test_directory_download_zip_naming_and_no_overwrite(tmp_path):
    transport = httpx.MockTransport(lambda r: httpx.Response(200, stream=httpx.ByteStream(b'zip'),
        headers={'Content-Disposition': 'attachment; filename="../../logs"'}))
    first, _ = download_file('https://files.example/log', 'job', directory=tmp_path, transport=transport)
    second, _ = download_file('https://files.example/log', 'job', directory=tmp_path, transport=transport)
    assert first == tmp_path/'logs.zip' and second == tmp_path/'logs (1).zip'
    assert first.read_bytes() == second.read_bytes() == b'zip'


@pytest.mark.parametrize('kind', ['history', 'instance'])
@pytest.mark.parametrize('bad_option', ['--file', '--directory'])
def test_invalid_destination_never_authenticates(tmp_path, kind, bad_option):
    with patch('wiserec_cli.auth.AuthManager.ensure_credentials', side_effect=AssertionError('must not authenticate')):
        result = runner().invoke(app, ['train', kind, 'logs', 'download', 't', 'j', bad_option, str(tmp_path/'missing')])
    assert result.exit_code != 0
