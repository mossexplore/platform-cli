import json
from unittest.mock import Mock, patch
import httpx
import pytest
from wiserec_cli import __version__
from wiserec_cli.client_metadata import begin_invocation, client_headers, handle_version_result, VersionPolicyError
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.access import check_access
from wiserec_cli.jupyter.connection import Connection, JupyterClient


def test_install_identity_persists_and_requests_have_unique_ids(tmp_path, monkeypatch):
    monkeypatch.setenv('ML_CLIENT_STATE_DIR', str(tmp_path))
    begin_invocation()
    first, second = client_headers(), client_headers()
    assert first['X-CLI-Version'] == __version__
    assert first['X-CLI-Installation-ID'] == second['X-CLI-Installation-ID']
    assert first['X-CLI-Invocation-ID'] == second['X-CLI-Invocation-ID']
    assert first['X-Request-ID'] != second['X-Request-ID']
    begin_invocation()
    third = client_headers()
    assert first['X-CLI-Installation-ID'] == third['X-CLI-Installation-ID']
    assert first['X-CLI-Invocation-ID'] != third['X-CLI-Invocation-ID']


def test_gateway_denial_is_not_authentication_error(tmp_path, monkeypatch):
    monkeypatch.setenv('ML_CLIENT_STATE_DIR', str(tmp_path))
    def handler(request):
        assert request.headers['businessid'] == 'selected'
        assert request.headers['x-cli-version'] == __version__
        assert len(request.headers.get_list('x-cli-version')) == 1
        return httpx.Response(403, json={'code':'CLI_VERSION_TOO_OLD', 'minimum_version':'2.0.0'})
    with PlatformClient(Profile('prod','https://example.com'), Credentials.create('prod','c','s','alice',100),
                        1000,0,True,transport=httpx.MockTransport(handler),business_selection=Mock(business_id='selected')) as client:
        with pytest.raises(VersionPolicyError, match='2.0.0'):
            client.request('GET','/test', headers={'x-cli-version':'spoofed'})


def test_version_warning_is_once_per_invocation_and_stderr(capsys):
    begin_invocation()
    result = {'version_policy':{'warning':True,'recommended_version':'2.0.0'}}
    handle_version_result(result)
    handle_version_result(result)
    output = capsys.readouterr()
    assert not output.out and output.err.count('升级提醒') == 1


def test_jupyter_http_and_websocket_send_same_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv('ML_CLIENT_STATE_DIR',str(tmp_path))
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200,json={})
    with JupyterClient(Connection('https://example.com/','token','selected'),httpx.MockTransport(handler)) as client:
        client.request('GET','api/kernels')
        with patch('wiserec_cli.jupyter.connection.websocket.create_connection') as create:
            create.return_value.getstatus.return_value = 101
            client.socket('api/kernels/id/channels')
            headers = create.call_args.kwargs['header']
    assert seen[0].headers['x-cli-version'] == headers['X-CLI-Version'] == __version__
    assert headers['businessid'] == 'selected'
    assert seen[0].headers['x-cli-invocation-id'] == headers['X-CLI-Invocation-ID']


def test_access_version_rejection_is_actionable():
    manager = Mock()
    manager.__enter__ = Mock(return_value=Mock())
    manager.__exit__ = Mock(return_value=False)
    manager.__enter__().post.return_value = httpx.Response(200,json={
        'allowed':False,'reason':'CLI_VERSION_TOO_OLD','minimum_version':'2.0.0',
        'recommended_version':'2.0.1','upgrade_url':'https://example.com/upgrade'})
    with patch('wiserec_cli.access.httpx.Client', return_value=manager):
        with pytest.raises(VersionPolicyError,match='https://example.com/upgrade'):
            check_access({'url':'https://access.example.com'},Profile('prod','https://example.com'),
                         Credentials.create('prod','c','s','alice',100),Mock(business_id='selected'))


def test_jupyter_gateway_rejection_is_actionable():
    def handler(request):
        return httpx.Response(403,json={'code':'CLI_VERSION_BLOCKED','current_version':'1.0.3','recommended_version':'1.0.4'})
    with JupyterClient(Connection('https://example.com/','token','selected'),httpx.MockTransport(handler)) as client:
        with pytest.raises(VersionPolicyError,match='已停用'):
            client.request('GET','api/kernels')


def test_websocket_gateway_error_body_is_preserved():
    import websocket
    exc = websocket.WebSocketBadStatusException('forbidden',403,resp_headers={},resp_body=json.dumps({'code':'CLI_VERSION_TOO_OLD','minimum_version':'2.0.0'}))
    with JupyterClient(Connection('https://example.com/','token','selected')) as client:
        with patch('wiserec_cli.jupyter.connection.websocket.create_connection',side_effect=exc):
            with pytest.raises(VersionPolicyError,match='2.0.0'):
                client.socket('api/kernels/id/channels')


def test_business_payload_with_non_string_code_is_unchanged():
    handle_version_result({'code':{'nested':'business-specific'}})


def test_gateway_denial_does_not_relogin_or_repeat_operation():
    from wiserec_cli.runtime import Runtime
    runtime = Runtime.__new__(Runtime)
    runtime.config = Mock(access_control={'enable': False}, timeout_ms=1000,retry_times=0,verify_ssl=True)
    runtime.config.current_profile.return_value = Profile('prod','https://example.com')
    runtime.auth = Mock()
    runtime.auth.ensure_credentials.return_value = Credentials.create('prod','c','s','alice',100)
    runtime.business = Mock()
    runtime.business.require_selection.return_value = Mock(business_id='selected')
    client = Mock()
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.request.side_effect = VersionPolicyError('CLI 版本过低')
    with patch('wiserec_cli.runtime.PlatformClient',return_value=client):
        with pytest.raises(VersionPolicyError):
            runtime.authenticated_call(lambda c: c.request('POST','/jobs'))
    assert runtime.auth.ensure_credentials.call_count == 1
    assert client.request.call_count == 1
