"""真实 HTTP 客户端的缓存恢复、失效与不重放路径。"""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import patch

import httpx
import pytest

from test_webstudio import rt, requests, ENV_ID, ROUTE, TOKEN
from wiserec_cli.auth import AuthManager
from wiserec_cli.jupyter.connection import JupyterClient, JupyterError
from wiserec_cli.webstudio.cache import ConnectionCache, cache_ttl
from wiserec_cli.webstudio.resolve import resolve


@pytest.fixture
def gateway():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.headers['businessid'] == 'pps'
        if request.url.path.endswith('/lab'):
            return httpx.Response(302, headers=[('set-cookie', 'session=private; Path=' + ROUTE + '; HttpOnly; Secure'),
                                               ('set-cookie', '_xsrf=xsrf-value; Path=' + ROUTE),
                                               ('location', ROUTE + 'lab')])
        assert 'session=private' in request.headers.get('cookie', '')
        if request.method == 'PUT':
            assert request.headers['x-xsrftoken'] == 'xsrf-value'
        return httpx.Response(200, json={'type': 'file'})
    return seen, httpx.MockTransport(handler)


def fetch(rt, transport, method='GET'):
    with JupyterClient(resolve(rt, ENV_ID), transport=transport) as client:
        return client.request(method, 'api/contents/example')


def test_independent_clients_reuse_discovery_and_cookies_but_check_permission(rt, requests, gateway):
    seen, transport = gateway
    with patch('wiserec_cli.webstudio.resolve.check_access') as access:
        assert fetch(rt, transport)['type'] == 'file'
        assert fetch(rt, transport, 'PUT')['type'] == 'file'
    assert access.call_count == 2
    assert len(requests) == 2
    assert [r.url.path for r in seen] == [ROUTE + 'lab', ROUTE + 'api/contents/example', ROUTE + 'api/contents/example']
    cache = ConnectionCache(rt.credentials.path, 'prod')
    content = cache.path.read_text()
    assert TOKEN in content and 'private' in content
    assert 'csrf' not in content  # 平台凭据只参与哈希，不持久化
    if os.name != 'nt':
        assert cache.path.stat().st_mode & 0o777 == 0o600
        assert cache.root.stat().st_mode & 0o777 == 0o700


def test_permission_rejection_on_cache_hit_sends_no_jupyter_request(rt, requests, gateway):
    seen, transport = gateway
    fetch(rt, transport)
    with patch('wiserec_cli.webstudio.resolve.check_access', side_effect=JupyterError('denied')):
        with pytest.raises(JupyterError, match='denied'):
            fetch(rt, transport)
    assert len(requests) == 2 and len(seen) == 2


@pytest.mark.parametrize('change', ['expired', 'credentials', 'forced', 'corrupt', 'foreign_origin'])
def test_refresh_causes_new_discovery(rt, requests, change):
    original = resolve(rt, ENV_ID)
    cache = original.session.cache
    if change == 'expired':
        data = cache.read()
        data[original.session.key]['expires_at'] = time.time() - 1
        cache.write(data)
    elif change == 'credentials':
        rt.auth.ensure_credentials.return_value = replace(rt.auth.ensure_credentials.return_value, cookie='new-cookie')
    elif change == 'corrupt':
        cache.path.write_text('invalid json')
    elif change == 'foreign_origin':
        data = cache.read()
        data[original.session.key]['url'] = 'https://foreign.example/instance/'
        cache.write(data)
    new = resolve(rt, ENV_ID, refresh=change == 'forced')
    assert len(requests) == 4
    assert new.session.entry['generation'] != original.session.entry['generation']
    assert new.url == original.url


def test_ttl_disabled_does_not_cache(rt, requests, gateway):
    rt.config._data['profiles'][0]['jupyter']['connection_cache_ttl_seconds'] = 0
    seen, transport = gateway
    fetch(rt, transport)
    fetch(rt, transport)
    assert len(requests) == 4 and len(seen) == 4
    assert not ConnectionCache(rt.credentials.path, 'prod').path.exists()


@pytest.mark.parametrize('value', [-1, 3601, True, '300', 1.5, None])
def test_invalid_ttl(value):
    with pytest.raises(Exception, match='connection_cache_ttl_seconds'):
        cache_ttl({'connection_cache_ttl_seconds': value})


@pytest.mark.parametrize('method,status,expected', [('GET', 401, 2), ('GET', 403, 1),
                                                    ('PUT', 401, 1), ('POST', 401, 1),
                                                    ('PATCH', 401, 1), ('DELETE', 401, 1),
                                                    ('GET', 500, 1), ('GET', 302, 1)])
def test_auth_retry_only_once_for_read_and_never_replay_mutations(rt, requests, method, status, expected):
    calls = []
    def handler(request):
        if request.url.path.endswith('/lab'):
            return httpx.Response(200)
        calls.append(request)
        return httpx.Response(status, json={})
    with pytest.raises(JupyterError):
        fetch(rt, httpx.MockTransport(handler), method)
    assert len(calls) == expected
    assert len(requests) == expected * 2
    cache = ConnectionCache(rt.credentials.path, 'prod')
    if status in (401, 403, 302):
        assert not cache.read()


def test_read_recovers_from_expired_token(rt, requests):
    calls = []
    def handler(request):
        if request.url.path.endswith('/lab'):
            return httpx.Response(200)
        calls.append(request)
        return httpx.Response(401 if len(calls) == 1 else 200, json={'ok': True})
    assert fetch(rt, httpx.MockTransport(handler)) == {'ok': True}
    assert len(calls) == 2 and len(requests) == 4


def test_read_after_mutation_does_not_refresh(rt, requests):
    def handler(request):
        if request.url.path.endswith('/lab') or request.method == 'POST':
            return httpx.Response(200, json={})
        return httpx.Response(401)
    with JupyterClient(resolve(rt, ENV_ID), transport=httpx.MockTransport(handler)) as client:
        client.request('POST', 'api/kernels', {})
        with pytest.raises(JupyterError):
            client.request('GET', 'api/contents/example')
    assert len(requests) == 2


def test_network_timeout_does_not_refresh_or_replay(rt, requests):
    calls = []
    def handler(request):
        if request.url.path.endswith('/lab'):
            return httpx.Response(200)
        calls.append(request)
        raise httpx.ReadTimeout('timeout')
    with pytest.raises(JupyterError, match='未自动重试'):
        fetch(rt, httpx.MockTransport(handler))
    assert len(calls) == 1 and len(requests) == 2


def test_old_generation_cannot_overwrite_or_delete_new_session(rt, requests):
    first = resolve(rt, ENV_ID).session
    second = resolve(rt, ENV_ID, refresh=True).session
    first.invalidate()
    with first.cache.locked():
        first.cache.save_session(first.key, first.entry['generation'], [])
    assert first.cache.read()[first.key]['generation'] == second.entry['generation']


def test_logout_clears_current_or_all_profiles(rt, requests):
    connection = resolve(rt, ENV_ID)
    other = ConnectionCache(rt.credentials.path, 'other')
    with other.locked():
        other.put('key', connection.url, TOKEN, 300)
    manager = AuthManager(rt.config, rt.credentials)
    manager.logout()
    assert not connection.session.cache.path.exists()
    assert other.path.exists()
    manager.logout(all_profiles=True)
    assert not other.path.exists()


def test_concurrent_clients_discover_and_bootstrap_once(rt, requests, gateway):
    seen, transport = gateway
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: fetch(rt, transport), range(4)))
    assert all(item['type'] == 'file' for item in results)
    assert len(requests) == 2
    assert sum(r.url.path.endswith('/lab') for r in seen) == 1


def test_cookie_expiry_bounds_cache_lifetime(rt, requests):
    session = resolve(rt, ENV_ID).session
    expiry = int(time.time()) + 60
    with session.cache.locked():
        session.cache.save_session(session.key, session.entry['generation'], [{'expires': expiry}])
    assert session.cache.read()[session.key]['expires_at'] == expiry - 10


def test_real_cookie_serialization_survives_new_python_process(rt, requests, gateway):
    """新解释器从磁盘恢复会话，不依赖父进程中的 CookieJar。"""
    import subprocess
    import sys
    from pathlib import Path
    _, transport = gateway
    fetch(rt, transport)
    connection = resolve(rt, ENV_ID)
    program = '''
import sys
import httpx
from wiserec_cli.webstudio.cache import ConnectionCache
from wiserec_cli.webstudio.session import CachedSession
from wiserec_cli.jupyter.connection import Connection, JupyterClient
cache = ConnectionCache(sys.argv[1], 'prod')
key, entry = next(iter(cache.read().items()))
def respond(request):
    assert not request.url.path.endswith('/lab'), 'session bootstrap repeated'
    assert request.headers['businessid'] == 'pps'
    assert 'session=private' in request.headers['cookie']
    assert request.headers['x-xsrftoken'] == 'xsrf-value'
    return httpx.Response(200, json={'ok': True})
connection = Connection(entry['url'], entry['token'], 'pps', studio_id='instance',
                        session=CachedSession(cache, key, entry))
with JupyterClient(connection, transport=httpx.MockTransport(respond)) as client:
    assert client.request('PUT', 'api/contents/example', {}) == {'ok': True}
'''
    result = subprocess.run([sys.executable, '-c', program, str(rt.credentials.path)],
                            capture_output=True, text=True,
                            env={**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')})
    assert result.returncode == 0, result.stderr
    assert connection.session.cache.read()


def test_cookie_scope_is_not_flattened(rt, requests):
    def handler(request):
        if request.url.path.endswith('/lab'):
            return httpx.Response(200, headers=[('set-cookie', 'outside=secret; Path=/unrelated/'),
                                               ('set-cookie', 'inside=ok; Path=' + ROUTE)])
        assert 'inside=ok' in request.headers['cookie']
        assert 'outside=' not in request.headers['cookie']
        return httpx.Response(200, json={})
    transport = httpx.MockTransport(handler)
    fetch(rt, transport)
    fetch(rt, transport)


def test_key_isolated_by_instance_and_credentials(rt, requests):
    first = resolve(rt, ENV_ID)
    scope = 'scope'
    credentials = rt.auth.ensure_credentials.return_value
    settings = rt.config.jupyter_settings()
    key = ConnectionCache.key(scope, ENV_ID, credentials, settings)
    assert key != ConnectionCache.key(scope, 'other-instance', credentials, settings)
    assert key != ConnectionCache.key('other-scope', ENV_ID, credentials, settings)
    assert key != ConnectionCache.key(scope, ENV_ID, replace(credentials, csrftoken='changed'), settings)
    assert first.session.entry['token'] == TOKEN


def test_websocket_respects_restored_cookie_scope(rt, requests):
    def handler(request):
        if request.url.path.endswith('/lab'):
            return httpx.Response(200, headers=[('set-cookie', 'outside=secret; Path=/unrelated/'),
                                               ('set-cookie', 'inside=ok; Path=' + ROUTE)])
        return httpx.Response(200, json={})
    transport = httpx.MockTransport(handler)
    fetch(rt, transport)
    with JupyterClient(resolve(rt, ENV_ID), transport=transport) as client:
        with patch('wiserec_cli.jupyter.connection.websocket.create_connection') as create:
            create.return_value.getstatus.return_value = 101
            client.socket('api/kernels/kernel/channels')
        assert create.call_args.kwargs['cookie'] == 'inside=ok'


def test_failed_bootstrap_invalidates_cache_without_deadlock(rt, requests):
    with pytest.raises(JupyterError, match='初始化失败'):
        fetch(rt, httpx.MockTransport(lambda request: httpx.Response(403)))
    assert not ConnectionCache(rt.credentials.path, 'prod').read()


def test_start_and_stop_discard_connection_cache(rt, requests):
    from typer.testing import CliRunner
    from wiserec_cli.cli import app
    for command in ('start', 'stop'):
        connection = resolve(rt, ENV_ID)
        assert connection.session.cache.path.exists()
        with patch('wiserec_cli.commands.webstudio.runtime_from_context', return_value=rt):
            result = CliRunner().invoke(app, ['--config', str(rt.config.path), 'webstudio', command, ENV_ID])
        assert result.exit_code == 0, result.output
        assert not connection.session.cache.path.exists()


def test_failed_explicit_refresh_discards_old_connection(rt, requests):
    connection = resolve(rt, ENV_ID)
    with patch('wiserec_cli.services.webstudio.WebStudioService.get', return_value={'status': 'offline'}):
        with pytest.raises(JupyterError, match='online'):
            resolve(rt, ENV_ID, refresh=True)
    assert not connection.session.cache.read()


def test_html_login_page_discards_session_without_replay(rt, requests):
    seen = []
    def handler(request):
        seen.append(request)
        return httpx.Response(200, text='<html>login</html>')
    with pytest.raises(JupyterError, match='未返回 JSON'):
        fetch(rt, httpx.MockTransport(handler))
    assert len(seen) == 2 and len(requests) == 2
    assert not ConnectionCache(rt.credentials.path, 'prod').read()


def test_stale_auth_failures_reuse_another_process_refresh(rt, requests):
    first = resolve(rt, ENV_ID)
    other = resolve(rt, ENV_ID)
    first.session.invalidate()
    refreshed = first.refresh()
    other.session.invalidate()
    reused = other.refresh()
    assert refreshed.session.entry['generation'] == reused.session.entry['generation']
    assert len(requests) == 4


def test_cache_update_failure_does_not_fail_completed_write(rt, requests, gateway, capsys):
    _, transport = gateway
    connection = resolve(rt, ENV_ID)
    with JupyterClient(connection, transport=transport) as client:
        client.request('GET', 'api/contents/example')
        with patch.object(connection.session.cache, 'save_session', side_effect=OSError('disk full')):
            assert client.request('PUT', 'api/contents/example', {}) == {'type': 'file'}
    assert '本次请求已完成' in capsys.readouterr().err


def test_login_validates_fresh_credentials_once(rt, requests, tmp_path):
    from wiserec_cli.webstudio.store import SelectionStore
    connection = resolve(rt, ENV_ID)
    with patch('wiserec_cli.webstudio.resolve.JupyterClient') as probe:
        resolve(rt, ENV_ID, login=True, store=SelectionStore(tmp_path / 'selection.json'))
    assert probe.call_args.args[0].refresh is None
    assert connection.refresh is not None


@pytest.mark.parametrize('command', [['files', 'stat', 'example', '-o', 'json'], ['doctor']])
def test_jupyter_target_name_and_id_on_fresh_and_cached_connections(rt, requests, gateway, command):
    import inspect
    from typer.testing import CliRunner
    from wiserec_cli.cli import app
    from test_webstudio import studio
    _, transport = gateway
    expected = f'目标Web Studio名称：test0123，envId：{ENV_ID}'
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    with patch('test_webstudio.studio', return_value={**studio(), 'labelName': 'test0123'}), \
         patch('wiserec_cli.commands.jupyter.runtime_from_context', return_value=rt), \
         patch('wiserec_cli.commands.jupyter.JupyterClient',
               side_effect=lambda connection: JupyterClient(connection, transport=transport)):
        for _ in range(2):
            result = CliRunner(**options).invoke(app, ['--config', str(rt.config.path), 'jupyter',
                                              *command, '--studio-id', ENV_ID])
            assert result.exit_code == 0, result.output
            assert expected in result.stderr
            assert TOKEN not in result.output
            if command[0] == 'files':
                assert json.loads(result.stdout)['studio_id'] == ENV_ID
                assert expected not in result.stdout
    assert len(requests) == 2  # 显示名称不会给缓存命中的命令增加平台请求


def test_legacy_cache_fetches_name_once_and_preserves_session(rt, requests, gateway):
    from test_webstudio import studio
    seen, transport = gateway
    fetch(rt, transport)
    connection = resolve(rt, ENV_ID)
    cache, key = connection.session.cache, connection.session.key
    with cache.locked():
        data = cache.read()
        data[key].pop('studio_name')
        cache.write(data)
    old = cache.read()[key]
    restored = resolve(rt, ENV_ID)
    assert restored.studio_name == studio()['labelName']
    updated = cache.read()[key]
    for field in ('token', 'generation', 'cookies', 'expires_at', 'session_ready'):
        assert updated[field] == old[field]
    fetch(rt, transport)
    assert len(requests) == 3  # 只补一次实例名称查询，不重新获取 accessUrl
    assert sum(r.url.path.endswith('/lab') for r in seen) == 1
