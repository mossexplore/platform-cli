import json
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import select
from conftest import ready, headers, BUSINESS
from app.artifacts import Artifacts, MAX_BYTES
from app.models import Session
from app.errors import AppError
from app.business_dispatch import dispatch, external_download


def sid(app):
    with app.state.db() as db:
        return db.scalar(select(Session.id).where(Session.status == 'ready'))


def test_upload_download_and_session_business_isolation(client, app, settings):
    ready(client)
    assert client.post('/api/artifacts?name=a.txt', content=b'hello').status_code == 403
    response = client.post('/api/artifacts?name=../../a.txt', headers=headers(client), content=b'hello')
    assert response.status_code == 200, response.text
    meta = response.json()
    assert meta['name'] == 'a.txt'
    download = client.get(meta['download_url'])
    assert download.content == b'hello'
    assert 'attachment' in download.headers['content-disposition']
    assert download.headers['cache-control'] == 'no-store'
    with pytest.raises(AppError): Artifacts(settings, sid(app), {'businessId': 'other'}).path(meta['artifact_id'])
    with pytest.raises(AppError): Artifacts(settings, sid(app), BUSINESS).path('../anything')
    client.cookies.clear()
    ready(client)
    assert client.get(meta['download_url']).status_code == 404


def test_upload_and_storage_limits(client, app, settings):
    ready(client)
    response = client.post('/api/artifacts?name=a.txt', headers=headers(client), content=b'x' * (MAX_BYTES + 1))
    assert response.status_code == 413
    with pytest.raises(AppError): Artifacts(settings, sid(app), BUSINESS).put('a.txt', b'x' * (MAX_BYTES + 1))


def test_signed_download_is_allowlisted_and_does_not_forward_platform_credentials(settings):
    seen, checks = [], []
    def upstream(request):
        seen.append(request)
        return httpx.Response(200, content=b'zip')
    c = SimpleNamespace(agent_environment=SimpleNamespace(download_hosts=['files.example']),
        agent_transport=httpx.MockTransport(upstream), agent_guard=lambda: checks.append('permission'),
        agent_check=lambda: checks.append('session'), agent_artifacts=Artifacts(settings, 's', BUSINESS))
    with pytest.raises(AppError): external_download(c, 'https://evil.example/a.zip')
    assert not seen
    result = external_download(c, 'https://files.example/a.zip?signature=private')
    assert c.agent_artifacts.path(result['artifact_id']).read_bytes() == b'zip'
    assert checks == ['permission', 'session']
    assert 'cookie' not in seen[0].headers and 'authorization' not in seen[0].headers
    assert 'signature' not in json.dumps(result)
    c.agent_transport = httpx.MockTransport(lambda _: httpx.Response(302, headers={'Location': 'https://evil.example'}))
    with pytest.raises(AppError): external_download(c, 'https://files.example/a.zip')


def test_deployment_plan_is_server_generated_and_publish_uses_exact_payload(settings, monkeypatch):
    payload = {'data': {'model': 'm', 'service': {'timeout': 5}}}
    published = []
    class Deploy:
        def __init__(self, client): pass
        def prepare(self, **kwargs):
            assert kwargs['tenant_id'] == 'b1'
            return payload, {}, {}
        def publish(self, body):
            published.append(body)
            return {'code': 0}
    monkeypatch.setattr('app.business_dispatch.ModelDeployService', Deploy)
    store = Artifacts(settings, 's', BUSINESS)
    c = SimpleNamespace(agent_artifacts=store, agent_business=BUSINESS)
    owner = SimpleNamespace(config=settings)
    plan = dispatch(owner, c, 'preview_model_deployment', {'model_id': 'm', 'template_id': 't'})
    payload['data']['service']['timeout'] = 99
    dispatch(owner, c, 'publish_model_deployment', {'artifact_id': plan['plan']['artifact_id']})
    assert published == [{'data': {'model': 'm', 'service': {'timeout': 5}}}]
    uploaded = store.put('fake.json', b'{}')
    with pytest.raises(AppError): dispatch(owner, c, 'publish_model_deployment', {'artifact_id': uploaded['artifact_id']})


def test_train_export_and_dataset_upload_guard_stream_and_multipart(client, app):
    ready(client)
    session_id = sid(app)
    calls = []
    original = app.state.platform.transport.handler
    def upstream(request):
        calls.append(request)
        path = request.url.path
        if path.endswith('/modelTrain/list'):
            return httpx.Response(200, json={'result': {'code': 0, 'data': {'count': 1, 'taskInfos': [
                {'taskId': 'task', 'businessId': 'b1', 'taskType': 'train'}]}}})
        if path.endswith('/traintask/export'):
            return httpx.Response(200, content=b'epochs: 3\n', headers={'content-type': 'text/yaml'})
        return original(request)
    app.state.platform.transport = httpx.MockTransport(upstream)
    result = app.state.platform.execute(session_id, None, BUSINESS, 'export_train_config', {'task_id': 'task'}, 'call')
    artifact = result['data']
    assert client.get(artifact['download_url']).content == b'epochs: 3\n'
    request = next(x for x in calls if x.url.path.endswith('/traintask/export'))
    gateway = calls[calls.index(request) - 1]
    assert json.loads(gateway.content)['command'] == 'ml train config export'
    assert request.headers['businessid'] == 'b1'
    app.test_upstream.allow = False
    before = len([r for r in calls if r.url.path.endswith('/traintask/export')])
    with pytest.raises(AppError):
        app.state.platform.execute(session_id, None, BUSINESS, 'export_train_config', {'task_id': 'task'}, 'call2')
    assert len([r for r in calls if r.url.path.endswith('/traintask/export')]) == before


def test_dataset_multipart_has_permission_and_current_business(client, app):
    ready(client)
    session_id = sid(app)
    upload = client.post('/api/artifacts?name=data.csv', headers=headers(client), content=b'x,y\n1,2').json()
    args = {'dataset_id': 'd1', 'directory': '/', 'artifact_id': upload['artifact_id']}
    calls = []
    original = app.state.platform.transport.handler
    def upstream(request):
        calls.append(request)
        if request.url.path.endswith('/dataSet/queryDetail'):
            return httpx.Response(200, json={'result': {'code': 0, 'data': {'dataSetName': 'training-data'}}})
        if request.url.path.endswith('/dataSet/file/upload'):
            assert b'x,y\n1,2' in request.read()
            return httpx.Response(200, json={'result': {'code': 0}})
        return original(request)
    app.state.platform.transport = httpx.MockTransport(upstream)
    approvals = app.state.platform.approvals
    # Internal permit injection is confined to this test; public callers cannot mint it.
    approvals.permits['test'] = approvals.fingerprint(session_id, None, BUSINESS, 'upload_dataset_file', args)
    result = app.state.platform.execute(session_id, None, BUSINESS, 'upload_dataset_file', args, 'call', approval='test')
    assert result['ok']
    request = next(r for r in calls if r.url.path.endswith('/dataSet/file/upload'))
    assert 'multipart/form-data' in request.headers['content-type']
    assert request.headers['businessid'] == 'b1'
    assert json.loads(calls[calls.index(request) - 1].content)['command'] == 'ml dataset files upload'
    with pytest.raises(AppError):
        app.state.platform.execute(session_id, None, BUSINESS, 'upload_dataset_file', args, 'replay', approval='test')


def test_expired_artifacts_are_removed(settings):
    import os, time
    from app.artifacts import prune
    store = Artifacts(settings, 'active', BUSINESS)
    meta = store.put('a.txt', b'data')
    other = Artifacts(settings, 'revoked', BUSINESS)
    other.put('b.txt', b'data')
    prune(settings, {'active'})
    assert store.path(meta['artifact_id']).exists()
    assert not other.root.exists()
    metadata = store.root / meta['artifact_id'] / 'metadata.json'
    os.utime(metadata, (0, 0))
    prune(settings, {'active'})
    with pytest.raises(AppError): store.path(meta['artifact_id'])
