from uuid import uuid4

import pytest
from sqlalchemy import select

from conftest import ready, headers
from test_runs import run_request, wait
from app.models import Conversation, Run, Message, Event, ToolCall, User


def test_delete_physically_removes_all_conversation_records(client, app):
    cid, _, rid = run_request(client)
    assert wait(client, rid)['status'] == 'completed'
    other = client.post('/api/conversations', headers=headers(client)).json()['id']
    with app.state.db() as db:
        for model in (Message, Event, ToolCall):
            assert db.scalar(select(model).where(model.run_id == rid)) is not None
    assert client.delete('/api/conversations/' + cid, headers=headers(client)).status_code == 200
    with app.state.db() as db:
        assert db.get(Conversation, cid) is None
        assert db.get(Conversation, other) is not None
        assert db.get(Run, rid) is None
        for model in (Message, Event, ToolCall):
            assert db.scalar(select(model).where(model.run_id == rid)) is None
    assert [c['id'] for c in client.get('/api/conversations').json()] == [other]
    for path in (f'/api/conversations/{cid}', f'/api/conversations/{cid}/messages',
                 f'/api/runs/{rid}', f'/api/runs/{rid}/events'):
        assert client.get(path).status_code == 404
    assert client.delete('/api/conversations/' + cid, headers=headers(client)).status_code == 404


@pytest.mark.parametrize('status', ['queued', 'running'])
def test_active_conversation_cannot_be_deleted(client, app, status):
    ready(client)
    cid = client.post('/api/conversations', headers=headers(client)).json()['id']
    with app.state.db() as db:
        from app.models import Session
        sid = db.scalar(select(Session.id).where(Session.status == 'ready'))
        run = Run(session_id=sid, conversation_id=cid, client_message_id=str(uuid4()), status=status)
        db.add(run)
        db.commit()
        rid = run.id
    result = client.delete('/api/conversations/' + cid, headers=headers(client))
    assert result.status_code == 409
    with app.state.db() as db:
        assert db.get(Conversation, cid) is not None
        assert db.get(Run, rid).status == status


def test_delete_requires_csrf_and_ownership_in_same_environment(client, app):
    ready(client)
    cid = client.post('/api/conversations', headers=headers(client)).json()['id']
    assert client.delete('/api/conversations/' + cid).status_code == 403
    with app.state.db() as db:
        own = db.get(Conversation, cid)
        user = User(environment_id='dev', username='other')
        db.add(user)
        db.flush()
        rows = [Conversation(user_id=user.id, environment_id='dev', business={}),
                Conversation(user_id=own.user_id, environment_id='mirror', business={})]
        db.add_all(rows)
        db.commit()
        keys = [row.id for row in rows]
    for key in keys + ['missing']:
        assert client.delete('/api/conversations/' + key, headers=headers(client)).status_code == 404
    with app.state.db() as db:
        assert all(db.get(Conversation, key) is not None for key in keys + [cid])
