"""Protocol, crash recovery and owner isolation; never call a message service."""
import re
from datetime import timedelta
import pytest
from sqlalchemy import select, func, inspect
from app.models import AccessApplication, Admin, SchemaVersion, now
from app.notification_models import NotificationClient, NotificationTask
from app.migrations import migrate, SCHEMA_VERSION
from app.security import digest
from test_service import system, login
from test_applications import submit

BASE = '/cli-permission/api/v1/notifications'
IDENTITY = {'installation_id': 'test-installation-123', 'protocol_version': 1}


@pytest.fixture
def notifications(system):
    app, client, _ = system
    app.state.settings.notification_owner_admin_id = 1
    csrf = login(client)
    response = client.post('/cli-permission/admin/notifications/token', data={'csrf': csrf, 'confirmation': 'reset'})
    assert response.status_code == 200, response.text
    token = re.search(r'aria-label="助手 Token">([^<]+)', response.text)[1]
    headers = {'Authorization': 'Bearer ' + token}
    assert client.post(BASE+'/bind', json=IDENTITY, headers=headers).status_code == 200
    assert client.post('/cli-permission/admin/notifications/enabled', data={'csrf':csrf,'enabled':'true'}).status_code == 200
    return app, client, headers, csrf, token


def call(client, headers, path, **body):
    return client.post(BASE+path, headers=headers, json={**IDENTITY, **body})


def claimed(client, headers, count=2):
    assert submit(client).status_code == 303
    task = call(client, headers, '/claim').json()['task']
    lease = {k: task[k] for k in ('lease_token','lease_generation')}
    ids = ['delivery-%03d' % i for i in range(count)]
    response = call(client, headers, f"/{task['id']}/prepare", **lease, snapshot_id='snapshot-123', delivery_ids=ids)
    assert response.status_code == 200, response.text
    return task['id'], lease, ids


def report(client, headers, task_id, lease, seq, uid, status, **extra):
    return call(client, headers, f'/{task_id}/result', **lease, report_id=f'report-{seq:05d}', report_seq=seq,
                updates=[{'delivery_id':uid,'attempt_id':f'attempt-{uid}','state':status, **extra}])


def test_transaction_duplicate_and_disabled(system):
    app, client, _ = system
    submit(client)
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NotificationTask)) == 0
        db.get(NotificationClient,1).enabled = True
        db.commit()
    submit(client, 'another-account')
    submit(client, 'another-account')
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NotificationTask)) == 1
        task = db.scalar(select(NotificationTask))
        assert task.application_id == db.scalar(select(AccessApplication.id).where(AccessApplication.username=='another-account'))


def test_token_owner_scope_and_reset(notifications):
    app, client, headers, csrf, token = notifications
    with app.state.sessions() as db:
        saved = db.get(NotificationClient,1)
        assert saved.token_hash == digest(token) and token not in saved.token_hash
    assert token not in client.get('/cli-permission/admin/notifications').text
    assert call(client, headers, '/bind', installation_id='different-installation').status_code == 409
    # Machine token does not replace admin session.
    client.cookies.clear()
    assert client.get('/cli-permission/admin/notifications', headers=headers).status_code == 401
    csrf = login(client)
    app.state.settings.notification_owner_admin_id = 999
    assert client.get('/cli-permission/admin/notifications').status_code == 403
    assert call(client, headers, '/claim').status_code == 403
    app.state.settings.notification_owner_admin_id = 1
    client.post('/cli-permission/admin/notifications/revoke',data={'csrf':csrf})
    assert call(client, headers, '/claim').status_code == 401


def test_partial_delivery_idempotency_and_fencing(notifications):
    app, client, headers, _, _ = notifications
    task_id, lease, ids = claimed(client, headers)
    assert report(client, headers, task_id, lease, 1, ids[0], 'sending').status_code == 200
    accepted = report(client, headers, task_id, lease, 2, ids[0], 'accepted')
    assert accepted.status_code == 200, accepted.text
    assert report(client, headers, task_id, lease, 2, ids[0], 'accepted').status_code == 200
    assert report(client, headers, task_id, lease, 2, ids[0], 'failed').status_code == 409
    assert report(client, headers, task_id, lease, 3, ids[1], 'sending').status_code == 200
    with app.state.sessions() as db:
        db.get(NotificationTask, task_id).lease_expires_at = now()-timedelta(seconds=1)
        db.commit()
    assert report(client, headers, task_id, lease, 4, ids[1], 'accepted').status_code == 409
    recovered = call(client,headers,f'/{task_id}/resume',snapshot_id='snapshot-123').json()
    assert recovered['deliveries'][ids[0]]['state'] == 'accepted'
    assert recovered['deliveries'][ids[1]]['state'] == 'uncertain'
    lease2 = {k:recovered[k] for k in ('lease_token','lease_generation')}
    # A durable success response can settle the same interrupted attempt.
    response = report(client, headers, task_id, lease2, 4, ids[1], 'accepted')
    assert response.status_code == 200, response.text
    assert response.json()['status'] == 'sent'
    assert report(client,headers,task_id,lease2,5,ids[0],'sending').status_code == 409


def test_prepared_snapshot_immutable_and_application_decision(notifications):
    app, client, headers, _, _ = notifications
    task_id, lease, ids = claimed(client, headers, 1)
    assert call(client,headers,f'/{task_id}/prepare',**lease,snapshot_id='changed-snapshot',delivery_ids=ids).status_code == 409
    with app.state.sessions() as db:
        task = db.get(NotificationTask,task_id)
        db.get(AccessApplication,task.application_id).status='approved'
        db.commit()
    assert report(client,headers,task_id,lease,1,ids[0],'sending').status_code == 409
    response=report(client,headers,task_id,lease,1,ids[0],'skipped')
    assert response.status_code==200 and response.json()['status']=='skipped'


def test_claim_response_loss_backfill_and_no_raw_recipient(notifications):
    app, client, headers, csrf, _ = notifications
    submit(client)
    a=call(client,headers,'/claim').json()['task']
    b=call(client,headers,'/claim').json()['task']
    assert a['id']==b['id'] and b['lease_generation'] > a['lease_generation']
    assert 'receiver' not in str(b)
    for _ in range(2):
        client.post('/cli-permission/admin/notifications/backfill',data={'csrf':csrf})
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(NotificationTask))==1


def test_schema_11_migration_preserves_existing_data(system):
    app, _, _=system
    NotificationTask.__table__.drop(app.state.engine)
    NotificationClient.__table__.drop(app.state.engine)
    with app.state.sessions() as db:
        db.get(SchemaVersion,SCHEMA_VERSION).version=11
        db.commit()
    migrate(app.state.engine,app.state.sessions)
    migrate(app.state.engine,app.state.sessions)
    assert 'notification_tasks' in inspect(app.state.engine).get_table_names()
    with app.state.sessions() as db:
        assert db.get(Admin,1).username=='admin'
        assert db.get(NotificationClient,1).enabled is False


def test_disabled_owner_and_expiration(notifications):
    app,client,headers,_,_=notifications
    with app.state.sessions() as db:
        db.get(NotificationClient,1).expires_at=now()-timedelta(seconds=1)
        db.commit()
    assert call(client,headers,'/heartbeat').status_code==401
