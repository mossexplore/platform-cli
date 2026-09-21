import hashlib
import json
from pathlib import Path
from unittest.mock import Mock, patch

import httpx
import pytest
from typer.testing import CliRunner
from rich.console import Console

from wiserec_cli.business import BusinessStore, Department, Tenant
from wiserec_cli.client import PlatformClient as RealClient
from wiserec_cli.cli import app
from wiserec_cli.models import Credentials
from wiserec_cli.runtime import Runtime
from wiserec_cli.jupyter.connection import from_runtime, JupyterError
from wiserec_cli.services.webstudio import WebStudioService
from wiserec_cli.webstudio.resolve import resolve, show
from wiserec_cli.webstudio.store import SelectionStore
from wiserec_cli.webstudio.urls import parse_access_url

ENV_ID = 'f925886d-072c-48fc-a4ec-636ab3ba9a60'
ROUTE = '/explore-env/12963932-4ef3-44e3-9c53-b9180f5a59d2/'
TOKEN = 'test-private-token'


def studio():
    return {'envId': ENV_ID, 'labelName': 'a long name ' * 4, 'clusterType': 'CCE',
            'imageSpecific': '4C32G0GPU', 'status': 'online', 'operator': 'creator',
            'modifier': 'modifier', 'accessTime': '2026-09-20T01:55:29.000Z', 'businessId': 'pps',
            'region': 'cn-north-4', 'extraField': {'keep': True}}


@pytest.fixture
def rt(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'prod', 'profiles': [{
        'name': 'prod', 'api_endpoint': 'https://console.example/dashboard',
        'jupyter': {'mode': 'webstudio', 'server_url': 'https://gateway.example'}}]}))
    runtime = Runtime(config_path=path, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    runtime.auth = Mock()
    runtime.auth.ensure_credentials.return_value = Credentials.create('prod', 'cookie', 'csrf', 'current-user', 3600)
    runtime.business.refresh('prod', 'current-user', [Department('d', 'department', (Tenant('pps', 'PPS', (), ()),))],
                             browser_business_id='pps')
    return runtime


@pytest.fixture
def requests(rt):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append((request, body))
        assert request.headers['businessid'] == body['businessId'] == 'pps'
        if request.url.path.endswith('queryEnvList'):
            result = {'code': 0, 'des': 'ok', 'count': 217, 'envs': [studio()]}
        else:
            result = {'code': 0, 'des': 'success', 'accessUrl': ROUTE + 'lab?token=' + TOKEN}
        return httpx.Response(200, json={'version': '1.0', 'meta': {'uuid': 'trace'}, 'result': result})
    with patch('wiserec_cli.webstudio.resolve.PlatformClient',
               side_effect=lambda *args, **kwargs: RealClient(*args, transport=httpx.MockTransport(handler), **kwargs)):
        yield seen


def test_dynamic_connection_current_operator_and_business(rt, requests, monkeypatch):
    monkeypatch.setenv('ML_JUPYTER_TOKEN', 'wrong-static-token')
    reports = []
    connection = from_runtime(rt, ENV_ID, report=reports.append)
    assert connection.token == TOKEN
    assert connection.url == 'https://gateway.example' + ROUTE
    assert connection.studio_id == ENV_ID
    assert TOKEN not in repr(connection)
    assert ('Jupyter 完整访问地址（包含 token，请谨慎保管）：'
            'https://gateway.example' + ROUTE + 'lab?token=' + TOKEN) in reports
    assert len(requests) == 2
    assert requests[0][1]['envId'] == ENV_ID
    assert requests[1][1]['operator'] == 'current-user'
    assert requests[1][0].url.host == 'console.example'
    assert requests[1][0].url.path == '/ai/backend/webstudio/dataExplorer/accessUrl'


def test_region_selects_gateway_within_same_environment(rt, requests):
    settings = rt.config._data['profiles'][0]['jupyter']
    settings.pop('server_url')
    settings['server_urls_by_region'] = {
        'cn-southwest-2': 'https://southwest.example:8443',
        'cn-north-4': 'https://north.example:8000',
    }
    north = resolve(rt, ENV_ID)
    assert north.url == 'https://north.example:8000' + ROUTE
    southwest_item = {**studio(), 'region': 'cn-southwest-2'}
    with patch.object(WebStudioService, 'get', return_value=southwest_item):
        southwest = resolve(rt, ENV_ID)
    assert southwest.url == 'https://southwest.example:8443' + ROUTE


@pytest.mark.parametrize('item,match', [
    ({'envId': ENV_ID, 'status': 'online'}, '缺少 region'),
    ({'envId': ENV_ID, 'status': 'online', 'region': 'cn-east-3'}, 'cn-east-3 未配置'),
])
def test_region_mapping_rejects_missing_or_unknown_region_before_access(rt, requests, item, match):
    settings = rt.config._data['profiles'][0]['jupyter']
    # 即使保留旧 server_url，显式区域映射也不得向它回退。
    settings['server_urls_by_region'] = {'cn-north-4': 'https://north.example:8000'}
    with patch.object(WebStudioService, 'get', return_value=item):
        with pytest.raises(JupyterError, match=match):
            resolve(rt, ENV_ID)
    assert not requests


@pytest.mark.parametrize('mapping', [
    {},
    {'cn-north-4': 'https://gateway.example/path'},
    {' cn-north-4': 'https://gateway.example'},
    {'cn-north-4': 'https://gateway.example:99999'},
])
def test_invalid_region_gateway_config_fails_before_platform_request(rt, requests, mapping):
    settings = rt.config._data['profiles'][0]['jupyter']
    settings.pop('server_url')
    settings['server_urls_by_region'] = mapping
    with pytest.raises(JupyterError, match='server_urls_by_region'):
        resolve(rt, ENV_ID)
    assert not requests


def test_region_gateway_rejects_absolute_access_url_from_other_origin(rt, requests):
    settings = rt.config._data['profiles'][0]['jupyter']
    settings['server_urls_by_region'] = {'cn-north-4': 'https://north.example:8000'}
    with patch.object(WebStudioService, 'access',
                      return_value='https://other.example' + ROUTE + 'lab?token=' + TOKEN):
        with pytest.raises(JupyterError, match='访问地址无效'):
            resolve(rt, ENV_ID)


def test_login_store_no_token_and_default_resolve(rt, requests, tmp_path):
    store = SelectionStore(tmp_path / 'webstudio.json')
    with patch('wiserec_cli.webstudio.resolve.JupyterClient') as probe:
        resolve(rt, ENV_ID, login=True, store=store)
        probe.return_value.__enter__.return_value.request.assert_called_once_with('GET', 'api/kernelspecs')
    text = store.path.read_text()
    assert TOKEN not in text and 'accessUrl' not in text and ROUTE not in text
    assert resolve(rt, store=store).studio_id == ENV_ID
    assert show(rt, store=store)['envId'] == ENV_ID
    assert len(requests) == 4  # 每次命令获取一次，不重复提交


def test_failed_login_keeps_previous_choice(rt, requests, tmp_path):
    store = SelectionStore(tmp_path / 'webstudio.json')
    key = store.key(rt, 'current-user', 'pps')
    store.save(key, {'envId': 'previous', 'labelName': 'previous'})
    with patch('wiserec_cli.webstudio.resolve.JupyterClient') as probe:
        probe.return_value.__enter__.return_value.request.side_effect = JupyterError('403')
        with pytest.raises(JupyterError):
            resolve(rt, ENV_ID, login=True, store=store)
    assert store.get(key)['envId'] == 'previous'


def test_scope_isolation(rt, tmp_path):
    store = SelectionStore(tmp_path / 'webstudio.json')
    original = store.key(rt, 'user', 'pps')
    legacy_scope = [str(rt.config.path.resolve()), 'prod', 'https://console.example/dashboard',
                    'https://gateway.example', 'user', 'pps']
    assert original == hashlib.sha256(json.dumps(legacy_scope, ensure_ascii=False).encode()).hexdigest()
    assert original != store.key(rt, 'other', 'pps')
    assert original != store.key(rt, 'user', 'other')
    rt.config._data['profiles'][0]['jupyter']['server_url'] = 'https://another.example'
    assert original != store.key(rt, 'user', 'pps')
    rt.config.path = tmp_path / 'another-config.json'
    assert original != store.key(rt, 'user', 'pps')


def test_region_mapping_scope_is_order_independent_and_changes_with_address(rt):
    store = SelectionStore()
    settings = rt.config._data['profiles'][0]['jupyter']
    settings.pop('server_url')
    settings['server_urls_by_region'] = {
        'cn-north-4': 'https://north.example:8000',
        'cn-southwest-2': 'https://southwest.example:8443',
    }
    original = store.key(rt, 'user', 'pps')
    settings['server_urls_by_region'] = {
        'cn-southwest-2': 'https://southwest.example:8443',
        'cn-north-4': 'https://north.example:8000',
    }
    assert store.key(rt, 'user', 'pps') == original
    settings['server_urls_by_region']['cn-north-4'] = 'https://north.example:9443'
    assert store.key(rt, 'user', 'pps') != original


def test_missing_selection_does_not_pick_first(rt, requests, tmp_path):
    with pytest.raises(JupyterError, match='未选择'):
        resolve(rt, store=SelectionStore(tmp_path / 'webstudio.json'))
    assert not requests


def test_query_filters_and_extra_fields():
    client = Mock(business_id='pps')
    client.request.return_value = {'result': {'code': 0, 'count': 217, 'envs': [studio()]}}
    payload = WebStudioService(client).list(2, 20, 'abc', 'online', 'someone', ENV_ID)
    body = client.request.call_args.kwargs['json_body']
    assert body['pageIndex'] == 2 and body['pageSize'] == 20
    assert body['labelName'] == 'abc' and body['relator'] == 'someone'
    assert body['teamId'] == '' and body['beginTime'] == ''
    assert payload['result']['envs'][0]['extraField'] == {'keep': True}
    with pytest.raises(ValueError, match='当前选择'):
        WebStudioService(client).list(business_id='other')


def test_access_failure_does_not_retry_or_leak():
    client = Mock(business_id='pps', username='current')
    client.request.side_effect = RuntimeError('body=' + TOKEN)
    with pytest.raises(Exception) as error:
        WebStudioService(client).access(ENV_ID)
    assert TOKEN not in str(error.value)
    assert client.request.call_count == 1


@pytest.mark.parametrize('url', [
    '//evil.example/x/lab?token=a', 'https://evil.example/x/lab?token=a',
    '/x/lab', '/x/lab?token=a&token=b',
    '/x/../y/lab?token=a', '/x/%2e%2e/y/lab?token=a', '/x/%252e%252e/y/lab?token=a',
    '/x/lab?token=a%0Ab', '/x/lab?token=a#fragment', '/x/lab?token=a&unknown=x',
    '/x/lab/tree/a.ipynb?token=a', '/x/lab?token=a\n', '/x\\y/lab?token=a',
])
def test_reject_ambiguous_or_untrusted_urls(url):
    with pytest.raises(JupyterError):
        parse_access_url('https://gateway.example', url)


def test_url_encoding_and_same_origin():
    base, token = parse_access_url('https://gateway.example/', 'https://gateway.example' + ROUTE + 'lab/?token=a%2Bb%3D')
    assert base.endswith(ROUTE)
    assert token == 'a+b='


def test_empty_platform_token_is_allowed():
    base, token = parse_access_url('https://gateway.example', ROUTE + 'lab?token=')
    assert base == 'https://gateway.example' + ROUTE
    assert token == ''


@pytest.mark.parametrize('base', ['https://gateway.example/lab', 'https://u:p@gateway.example',
                                 'https://gateway.example?token=x', None])
def test_invalid_gateway(base):
    with pytest.raises(JupyterError):
        parse_access_url(base, ROUTE + 'lab?token=a')


def test_cli_json_and_narrow_id(rt, requests, monkeypatch):
    runner = CliRunner()
    with patch('wiserec_cli.commands.webstudio.runtime_from_context', return_value=rt):
        result = runner.invoke(app, ['--config', str(rt.config.path), 'webstudio', 'list', '--output', 'json'])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout)['result']['envs'][0]['extraField']['keep'] is True
        console = Console(width=65, color_system=None)
        with patch('wiserec_cli.commands.webstudio.console', console):
            with console.capture() as capture:
                result = runner.invoke(app, ['--config', str(rt.config.path), 'webstudio', 'list'])
        assert result.exit_code == 0, result.output
        assert ENV_ID in capture.get()


@pytest.mark.parametrize('args', [['doctor'], ['terminal', 'open'], ['terminal', 'attach', '1'],
                                 ['terminal', 'close', '1'], ['terminal', 'list'], ['notebook', 'run']])
def test_jupyter_studio_option(args, rt):
    result = CliRunner().invoke(app, ['--config', str(rt.config.path), 'jupyter', *args, '--help'])
    assert result.exit_code == 0
    assert '--studio-id' in result.output


def test_direct_rejects_studio_id(rt):
    rt.config._data['profiles'][0]['jupyter']['mode'] = 'direct'
    with pytest.raises(JupyterError, match='--studio-id'):
        from_runtime(rt, ENV_ID)


def test_non_online_does_not_request_access(rt, requests):
    with patch.object(WebStudioService, 'get', return_value={'envId': ENV_ID, 'status': 'offline'}):
        with pytest.raises(JupyterError, match='online'):
            resolve(rt, ENV_ID)
    assert not requests


def test_invalid_access_url_is_reported_before_validation(rt, requests):
    reports = []
    with patch.object(WebStudioService, 'access', return_value='/broken?token=' + TOKEN):
        with pytest.raises(JupyterError, match='访问地址无效'):
            resolve(rt, ENV_ID, report=reports.append)
    assert reports[-1] == ('Jupyter 完整访问地址（包含 token，请谨慎保管）：'
                           'https://gateway.example/broken?token=' + TOKEN)


def test_business_mismatch_rejected_before_any_request(rt, requests):
    value = json.loads(rt.business.path.read_text())
    value['profiles']['prod']['selected']['businessId'] = 'other'
    rt.business.path.write_text(json.dumps(value))
    with pytest.raises(JupyterError, match='businessId'):
        resolve(rt, ENV_ID)
    assert not requests


def test_safe_json_redacts_new_sensitive_fields():
    from wiserec_cli.commands.webstudio import safe_data
    payload = {'extra': True, 'accessUrl': '/route/lab?token=' + TOKEN, 'nested': {'token': TOKEN}}
    result = safe_data(payload)
    assert result['extra'] is True
    assert TOKEN not in json.dumps(result)


def test_doctor_reports_kernel_success_before_terminal_failure(rt):
    with patch('wiserec_cli.commands.jupyter.client_for') as factory:
        factory.return_value.__enter__.return_value.request.side_effect = [
            {'kernelspecs': {'python3': {}}}, JupyterError('Jupyter GET api/terminals HTTP 403')]
        result = CliRunner().invoke(app, ['--config', str(rt.config.path), 'jupyter', 'doctor'])
    assert result.exit_code == 1
    assert 'Kernel 接口：通过' in result.output
    assert 'api/terminals' in result.output
