"""授权必须在实际业务调用前验证；不可缓存撤销结果。"""
import json
from unittest.mock import Mock, patch
import httpx
import pytest
from wisemlops_cli.access import check_access, validate_settings
from wisemlops_cli.config import _sync_packaged_config
from wisemlops_cli.errors import AuthenticationError, ConfigError, MlError
from wisemlops_cli.models import Profile, Credentials
from wisemlops_cli.business import BusinessSelection
from wisemlops_cli.runtime import Runtime


@pytest.fixture
def inputs():
    return ({'url': 'https://access.example.com', 'enabled': True},
            Profile('dev', 'https://platform.example.com/dashboard'),
            Credentials.create('dev', 'secret-cookie', 'secret-csrf', 'alice', 1000),
            Mock(business_id='current-business'))


def response_mock(response):
    manager = Mock()
    client = manager.__enter__ = Mock(return_value=Mock())
    manager.__exit__ = Mock(return_value=False)
    client.return_value.post.return_value = response
    return manager


def test_authorization_headers_and_environment(inputs):
    response = httpx.Response(200, json={'allowed': True, 'username': 'alice', 'environment': 'dev'})
    manager = response_mock(response)
    with patch('wisemlops_cli.access.httpx.Client', return_value=manager) as ctor:
        assert check_access(*inputs)['allowed']
    args, kwargs = manager.__enter__().post.call_args
    assert args[0] == 'https://access.example.com/cli-permission/api/v1/access/check'
    assert kwargs['headers'] == {'businessid': 'current-business'}
    assert kwargs['json'] == {'username': 'alice', 'environment': 'dev', 'platform_origin': 'https://platform.example.com', 'command': 'unknown'}
    assert ctor.call_args.kwargs['verify'] is True
    assert ctor.call_args.kwargs['follow_redirects'] is False


@pytest.mark.parametrize('status,payload,error', [
    (200, {'allowed': False, 'reason': 'GRANT_EXPIRED'}, '已过期'),
    (200, {'allowed': 'true'}, '格式错误'), (200, [], '格式错误'),
    (200, {'allowed': True, 'username': 'mallory', 'environment': 'dev'}, '不一致'),
    (503, {}, '503'), (302, {}, '302')])
def test_denial_and_invalid_response(inputs, status, payload, error):
    with patch('wisemlops_cli.access.httpx.Client', return_value=response_mock(httpx.Response(status, json=payload))):
        with pytest.raises(MlError, match=error):
            check_access(*inputs)


def test_access_401_reports_service_rejection(inputs):
    with patch('wisemlops_cli.access.httpx.Client', return_value=response_mock(httpx.Response(401))):
        with pytest.raises(MlError, match="权限服务拒绝请求"):
            check_access(*inputs)


def test_network_error_hides_credentials(inputs):
    with patch('wisemlops_cli.access.httpx.Client', side_effect=httpx.ConnectError('secret-cookie')):
        with pytest.raises(MlError) as error:
            check_access(*inputs)
        assert 'secret-cookie' not in str(error.value)


def test_runtime_blocks_operation_and_rechecks_each_command(inputs):
    runtime = Runtime.__new__(Runtime)
    runtime.config = Mock(access_control=inputs[0], timeout_ms=1000, retry_times=0, verify_ssl=True)
    runtime.config.current_profile.return_value = inputs[1]
    runtime.auth = Mock()
    runtime.auth.ensure_credentials.return_value = inputs[2]
    runtime.business = Mock()
    runtime.business.require_selection.return_value = inputs[3]
    operation = Mock()
    with patch('wisemlops_cli.runtime.check_access', side_effect=MlError('denied')), patch('wisemlops_cli.runtime.PlatformClient') as client:
        with pytest.raises(MlError):
            runtime.authenticated_call(operation)
        client.assert_not_called()
        operation.assert_not_called()
    with patch('wisemlops_cli.runtime.check_access', side_effect=[{}, MlError('revoked')]) as check, patch('wisemlops_cli.runtime.PlatformClient'):
        runtime.authenticated_call(operation)
        with pytest.raises(MlError):
            runtime.authenticated_call(operation)
        assert check.call_count == 2
        assert operation.call_count == 1


@pytest.mark.parametrize('settings', [{'url': 'ftp://access.example.com'}, {'url': 'https://u:p@access.example.com'},
    {'url': 'https://access.example.com/path'}, {'enabled': 'false'}, {'enabled': True},
    {'enabled': False, 'timeout_seconds': True}, {'enabled': False, 'timeout_seconds': float('nan')}])
def test_bad_settings(settings):
    with pytest.raises(ConfigError):
        validate_settings(settings)


def test_disabled_does_not_connect(inputs):
    with patch('wisemlops_cli.access.httpx.Client') as client:
        assert check_access({}, *inputs[1:]) is None
        client.assert_not_called()


def test_upgrade_replaces_access_configuration(tmp_path):
    target = tmp_path / 'config.json'
    settings = {'enabled': True, 'url': 'https://access.example.com'}
    target.write_text(json.dumps({'old': 'config', 'access_control': settings}))
    with patch('wisemlops_cli.config._packaged_config_text', return_value='{"new":"config"}'):
        _sync_packaged_config(target)
    assert json.loads(target.read_text()) == {'new': 'config'}


@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_access_accepts_http_and_https(inputs, scheme):
    settings = validate_settings({'url': scheme + '://access.example.com:8008'})
    response = httpx.Response(200, json={'allowed': True, 'username': 'alice', 'environment': 'dev'})
    manager = response_mock(response)
    with patch('wisemlops_cli.access.httpx.Client', return_value=manager):
        assert check_access(settings, *inputs[1:])['allowed']
    assert manager.__enter__().post.call_args.args[0] == scheme + '://access.example.com:8008/cli-permission/api/v1/access/check'


def test_command_name_excludes_argument_values(tmp_path):
    from typer.testing import CliRunner
    from wisemlops_cli.cli import app
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'profiles': [
        {'name': 'dev', 'api_endpoint': 'https://platform.example.com'}]}))
    commands = []
    def capture(runtime, operation):
        commands.append(runtime.invocation_command)
        return 'job-id'
    with patch.object(Runtime, 'authenticated_call', capture):
        result = CliRunner().invoke(app, ['--config', str(config), 'train', 'start', 'sensitive-task-id'])
    assert result.exit_code == 0, result.output
    assert commands == ['ml train start']


def test_access_module_imports_without_click():
    # 独立进程模拟 click 不可用，验证配置加载依赖的 access 模块仍可导入。
    import subprocess
    import sys
    import os
    from pathlib import Path
    script = """
import sys
sys.modules['click'] = None
import wisemlops_cli.access
assert wisemlops_cli.access.command_name(None) == 'unknown'
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
    result = subprocess.run([sys.executable, '-c', script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize('exception,message', [
    (httpx.ConnectTimeout, '连接权限服务超时'),
    (httpx.ReadTimeout, '等待权限服务响应超时'),
    (httpx.WriteTimeout, '权限服务请求超时'),
    (httpx.ConnectError, '无法连接权限服务'),
    (httpx.RemoteProtocolError, 'HTTP 响应不完整'),
    (httpx.ProxyError, 'HTTP 通信异常'),
])
def test_access_network_failure_categories(inputs, exception, message):
    manager = response_mock(None)
    manager.__enter__().post.side_effect = exception('secret-cookie secret-csrf')
    with patch('wisemlops_cli.access.httpx.Client', return_value=manager):
        with pytest.raises(MlError, match=message) as error:
            check_access(*inputs)
    assert 'secret-cookie' not in str(error.value)
    assert 'secret-csrf' not in str(error.value)


def test_non_json_access_response_is_distinct(inputs):
    manager = response_mock(httpx.Response(200, text='<html>secret-cookie</html>'))
    with patch('wisemlops_cli.access.httpx.Client', return_value=manager):
        with pytest.raises(MlError, match='不是有效 JSON') as error:
            check_access(*inputs)
    assert 'secret-cookie' not in str(error.value)
