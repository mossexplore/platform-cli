import json
from datetime import datetime
from uuid import uuid4
import pytest
from sqlalchemy import select
from app.models import Message
from conftest import ready, headers
from test_runs import wait


@pytest.mark.parametrize('allowed', [True, False])
def test_message_times_survive_history_polling_and_sse_replay(client, app, allowed):
    ready(client)
    app.test_upstream.allow = allowed
    cid = client.post('/api/conversations', headers=headers(client)).json()['id']
    payload = {'message': '查询模型', 'client_message_id': str(uuid4())}
    path = f'/api/conversations/{cid}/runs'
    first = client.post(path, json=payload, headers=headers(client)).json()
    rid = first['run_id']
    assert first['created_at'].endswith('Z')
    run = wait(client, rid)
    assert run['status'] == ('completed' if allowed else 'failed')
    assert run['created_at'].endswith('Z')
    rows = client.get(f'/api/conversations/{cid}/messages').json()
    assert rows[0]['created_at'] == first['created_at']
    assert rows[1]['created_at'] == run['created_at']
    duplicate = client.post(path, json=payload, headers=headers(client)).json()
    assert duplicate['created_at'] == first['created_at']
    # Force a known UTC time to verify the real response paths preserve timezone data.
    with app.state.db() as db:
        for message in db.scalars(select(Message).where(Message.run_id == rid)):
            message.created_at = datetime(2026, 9, 8, 6, 54, 36)
        db.commit()
    rows = client.get(f'/api/conversations/{cid}/messages').json()
    assert all(m['created_at'] == '2026-09-08T06:54:36Z' for m in rows)
    events = client.get(f'/api/runs/{rid}/events').text
    terminal = []
    for block in events.split('\n\n'):
        if any(f'event: {kind}' in block for kind in ['run.completed', 'run.failed', 'stream.closed']):
            data = next(line[6:] for line in block.splitlines() if line.startswith('data: '))
            terminal.append(json.loads(data))
    assert len(terminal) >= 2
    assert all(data['created_at'] == rows[1]['created_at'] for data in terminal)
