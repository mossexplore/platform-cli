import asyncio
import json
import time
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select
from conftest import ready, headers, BUSINESS
from test_runs import wait
from app.models import Event, Session, Run
from app.approvals import Approvals
from app.errors import AppError


class WriteEngine:
    async def run(self, history, message, context, invoke, delta, progress=None):
        result = await invoke('start_webstudio', {'env_id': 'studio-1'})
        return json.dumps(result), [], {}


def pending(client, app):
    ready(client)
    original = app.state.platform.transport.handler
    def upstream(request):
        if request.url.path.endswith('/dataExplorer/start'):
            app.test_upstream.calls.append(request)
            return httpx.Response(200, json={'result': {'code': 0}})
        return original(request)
    app.state.platform.transport = httpx.MockTransport(upstream)
    app.state.runs.engine = WriteEngine()
    cid = client.post('/api/conversations', headers=headers(client)).json()['id']
    rid = client.post(f'/api/conversations/{cid}/runs', headers=headers(client), json={
        'message': '启动开发环境', 'client_message_id': str(uuid4())}).json()['run_id']
    for _ in range(200):
        with app.state.db() as db:
            event = db.scalar(select(Event).where(Event.run_id == rid, Event.kind == 'action.required'))
            if event: return rid, event.payload
        time.sleep(.01)
    raise AssertionError('confirmation was not emitted')


def writes(app):
    return [r for r in app.test_upstream.calls if r.url.path.endswith('/dataExplorer/start')]


def test_write_waits_for_browser_and_checks_permission_again(client, app):
    rid, action = pending(client, app)
    assert not writes(app)
    endpoint = f'/api/runs/{rid}/actions/' + action['action_id']
    assert client.post(endpoint, json={'approved': True}).status_code == 403
    assert client.post(endpoint, headers=headers(client), json={'approved': True, 'env_id': 'changed'}).status_code == 400
    assert client.post(endpoint, headers=headers(client), json={'approved': 'true'}).status_code == 400
    assert not writes(app)
    assert client.post(endpoint, headers=headers(client), json={'approved': True}).status_code == 200
    assert wait(client, rid)['status'] == 'completed'
    assert len(writes(app)) == 1
    request = writes(app)[0]
    assert request.headers['businessid'] == 'b1'
    assert json.loads(request.content)['operator'] == 'zhangsan'
    calls = app.test_upstream.calls
    gateway = calls[calls.index(request) - 1]
    assert json.loads(gateway.content)['command'] == 'ml webstudio start'
    assert client.post(endpoint, headers=headers(client), json={'approved': True}).status_code == 409
    assert len(writes(app)) == 1


@pytest.mark.parametrize('mode', ['reject', 'revoke', 'cancel'])
def test_rejection_revocation_and_cancel_prevent_mutation(client, app, mode):
    rid, action = pending(client, app)
    if mode == 'revoke': app.test_upstream.allow = False
    if mode == 'cancel':
        client.post(f'/api/runs/{rid}/cancel', headers=headers(client))
    else:
        result = client.post(f'/api/runs/{rid}/actions/' + action['action_id'],
            headers=headers(client), json={'approved': mode != 'reject'})
        assert result.status_code == 200
    assert wait(client, rid)['status'] in ('failed', 'cancelled')
    assert not writes(app)
    assert not app.state.runs.approvals.permits


def test_other_browser_cannot_approve(client, app):
    rid, action = pending(client, app)
    original_cookies = dict(client.cookies)
    client.cookies.clear()
    ready(client)
    response = client.post(f'/api/runs/{rid}/actions/' + action['action_id'],
        headers=headers(client), json={'approved': True})
    assert response.status_code == 404
    assert not writes(app)
    client.cookies.clear()
    client.cookies.update(original_cookies)
    client.post(f'/api/runs/{rid}/cancel', headers=headers(client))
    wait(client, rid)


async def test_permits_bind_arguments_owner_business_run_and_are_single_use():
    approvals = Approvals()
    events = []
    async def emit(kind, payload): events.append((kind, payload))
    args = {'env_id': 'a'}
    task = asyncio.create_task(approvals.request('s', 'r', BUSINESS, 'start_webstudio', args, emit))
    await asyncio.sleep(0)
    key = events[0][1]['action_id']
    args['env_id'] = 'changed'
    with pytest.raises(AppError): approvals.decide(key, 'other', 'r', True)
    approvals.decide(key, 's', 'r', True)
    with pytest.raises(AppError): approvals.decide(key, 's', 'r', True)
    permit = await task
    with pytest.raises(AppError):
        approvals.consume(permit, 's', 'r', BUSINESS, 'start_webstudio', args)
    # A failed consume burns the permit, so it cannot later authorize the original target.
    with pytest.raises(AppError):
        approvals.consume(permit, 's', 'r', BUSINESS, 'start_webstudio', {'env_id': 'a'})


def test_direct_platform_write_without_confirmation_cannot_make_http_call(client, app):
    ready(client)
    before = len(app.test_upstream.calls)
    with app.state.db() as db: sid = db.scalar(select(Session.id).where(Session.status == 'ready'))
    with pytest.raises(AppError, match='确认'):
        app.state.platform.execute(sid, None, BUSINESS, 'start_webstudio', {'env_id': 's'}, 'call')
    assert len(app.test_upstream.calls) == before
