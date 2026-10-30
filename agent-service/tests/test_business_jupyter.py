import json
from types import SimpleNamespace
import httpx
import pytest
from conftest import BUSINESS, ready
from test_business_files import sid
from app.artifacts import Artifacts
from app.errors import AppError
from app.jupyter_tools import dispatch, GuardedSocket
from wiserec_cli.jupyter.connection import Connection


def platform(settings, handler):
    calls = []
    c = SimpleNamespace(agent_artifacts=Artifacts(settings, 's', BUSINESS),
        agent_transport=httpx.MockTransport(handler), agent_guard=lambda: calls.append('permission'),
        agent_check=lambda: calls.append('session'))
    return c, calls


def test_contents_write_move_delete_and_read_use_guards(settings, monkeypatch):
    requests, saved = [], {}
    def handle(r):
        requests.append(r)
        key = r.url.path.removeprefix('/api/contents/')
        if r.method == 'GET':
            return httpx.Response(200, json=saved[key]) if key in saved else httpx.Response(404)
        if r.method == 'PUT':
            saved[key] = json.loads(r.content)
            return httpx.Response(201, json=saved[key])
        if r.method == 'PATCH':
            saved[json.loads(r.content)['path']] = saved.pop(key)
            return httpx.Response(200, json={'path': 'b.txt'})
        if r.method == 'DELETE':
            del saved[key]
            return httpx.Response(204)
        raise AssertionError(r)
    c, checks = platform(settings, handle)
    monkeypatch.setattr('app.jupyter_tools.connection', lambda *_: Connection('http://jupyter/', 'secret', 'b1'))
    dispatch(c, 'jupyter_files_write', {'studio_id': 's', 'path': 'a.txt', 'content': 'hello', 'overwrite': False})
    assert dispatch(c, 'jupyter_files_read', {'studio_id': 's', 'path': 'a.txt'})['content'] == 'hello'
    dispatch(c, 'jupyter_files_move', {'studio_id': 's', 'path': 'a.txt', 'destination': 'b.txt'})
    dispatch(c, 'jupyter_files_delete', {'studio_id': 's', 'path': 'b.txt'})
    assert not saved
    assert checks.count('permission') == len(requests)
    assert all(r.headers['businessid'] == 'b1' for r in requests)
    with pytest.raises(Exception): dispatch(c, 'jupyter_files_read', {'studio_id': 's', 'path': '../escape'})


def test_webstudio_discovery_rejects_untrusted_gateway_and_hides_token(client, app):
    ready(client)
    session_id = sid(app)
    app.state.config.env('dev').jupyter_gateways = {'test': 'https://jupyter.example'}
    original = app.state.platform.transport.handler
    def handle(r):
        path = r.url.path
        if path.endswith('/queryEnvList'):
            return httpx.Response(200, json={'result': {'code': 0, 'count': 1, 'envs': [
                {'envId': 'studio', 'businessId': 'b1', 'status': 'online', 'region': 'test'}]}})
        if path.endswith('/accessUrl'):
            return httpx.Response(200, json={'result': {'code': 0, 'accessUrl': '/studio/lab?token=secret-jupyter-token'}})
        if path == '/studio/lab': return httpx.Response(200)
        if path in ('/studio/api/kernelspecs', '/studio/api/terminals'):
            assert r.headers['businessid'] == 'b1'
            assert r.headers['authorization'] == 'token secret-jupyter-token'
            assert 'platform-secret-cookie' not in r.headers.get('cookie', '')
            return httpx.Response(200, json={} if 'kernelspecs' in path else [])
        return original(r)
    app.state.platform.transport = httpx.MockTransport(handle)
    result = app.state.platform.execute(session_id, None, BUSINESS, 'jupyter_doctor', {'studio_id': 'studio'}, 'call')
    assert result['ok'] and 'secret-jupyter-token' not in json.dumps(result)
    app.state.config.env('dev').jupyter_gateways = {'test': 'https://elsewhere.example'}
    # Relative platform routes resolve against the configured gateway, not a model URL.
    from wiserec_cli.webstudio.urls import parse_access_url
    with pytest.raises(Exception): parse_access_url('https://elsewhere.example', 'https://evil.example/studio/lab?token=x')


def test_websocket_permission_revocation_prevents_send():
    sent = []
    def denied(): raise AppError('ACCESS_DENIED', 'denied', 403)
    socket = GuardedSocket(SimpleNamespace(send=sent.append), SimpleNamespace(agent_guard=denied))
    with pytest.raises(AppError): socket.send('execute_request')
    assert not sent
