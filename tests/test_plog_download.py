"""Plog 请求契约、两平台命令调度与参数限制。"""
import json
import inspect
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.runtime import Runtime
from wiserec_cli.services.train import TrainService
from wiserec_cli.errors import ApiError, BusinessError
from cli_test_support import invoke_with_config


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
def test_plog_request_and_cli_download(tmp_path, platform):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'profiles': [{'name': 'dev',
        'platform_type': platform, 'api_endpoint': 'https://current.example'}]}))
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    def handler(request):
        assert request.method == 'GET'
        assert request.url.host == 'current.example'
        assert request.url.path == '/ai/backend/mtp/traintask/downloadPlog'
        assert dict(request.url.params) == dict(businessId='selected', jobId='job',
            taskId='task', isApplicantPromise='true')
        assert request.headers['businessid'] == 'selected'
        return httpx.Response(200, json={'result': {'code': 0, 'des': 'get plog success',
                                                   'plogUrl': 'https://files.example/plog'}})
    path = tmp_path / 'plog.zip'
    with PlatformClient(Profile('dev', 'https://current.example', platform_type=platform),
                        Credentials.create('dev', 'cookie', 'csrf', 'user', 60), 1000, 0, True,
                        transport=httpx.MockTransport(handler),
                        business_selection=SimpleNamespace(business_id='selected')) as client:
        with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
             patch.object(runtime, 'authenticated_call', side_effect=lambda operation: operation(client)), \
             patch('wiserec_cli.commands.train.download_file', return_value=(path, 123)) as download:
            result = invoke_with_config(CliRunner(**({"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {})), app, config, ['train', 'history', 'logs',
                'download', 'task', 'job', '--type', 'plog', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == dict(taskId='task', jobId='job', path=str(path),
                                           bytes=123, status='downloaded')
    assert download.call_args.args[:3] == ('https://files.example/plog', 'job-plog')


@pytest.mark.parametrize('options', [
    ['--type', 'bad'], ['--type', 'plog', '--target', ' '],
    ['--target', 'x'], ['--type', 'log', '--target', 'x'],
])
def test_invalid_combinations_never_request_or_download(options):
    runtime = SimpleNamespace(config=SimpleNamespace(current_profile=lambda: SimpleNamespace(
        platform_type='wiserec')), authenticated_call=lambda op: pytest.fail('must not authenticate'))
    with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
         patch('wiserec_cli.commands.train.download_file', side_effect=AssertionError('must not download')):
        result = CliRunner(**({"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {})).invoke(app, ['train', 'history', 'logs', 'download', 't', 'j', *options])
    assert result.exit_code != 0


@pytest.mark.parametrize('result', [None, {'code': 1, 'des': 'denied'},
    {'code': False, 'plogUrl': 'https://files.example/log'},
    {'code': 0}, {'code': 0, 'plogUrl': 'http://files.example/log'},
    {'code': 0, 'plogUrl': 'https://user:pass@files.example/log'}])
def test_invalid_plog_responses(result):
    client = SimpleNamespace(business_id='b', request=lambda *a, **kw: {'result': result})
    with pytest.raises(ApiError):
        TrainService(client).get_plog_url('t', 'j')


def test_missing_business_never_requests():
    client = SimpleNamespace(business_id='', request=lambda *a, **kw: pytest.fail('must not request'))
    with pytest.raises(BusinessError):
        TrainService(client).get_plog_url('t', 'j')
