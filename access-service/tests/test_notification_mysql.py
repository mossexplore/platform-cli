"""Opt-in disposable MySQL verification; never point at a production database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, inspect, text
from sqlalchemy.dialects.mysql import LONGTEXT
from app.main import create_app
from app.settings import Settings
from app.migrations import migrate, SCHEMA_VERSION
from app.models import Admin, AccessApplication, CallLog, SchemaVersion, now
from app.notification_models import NotificationClient, NotificationTask, enqueue
from app.security import digest


@pytest.mark.skipif(not os.environ.get('NOTIFIER_TEST_DATABASE_URL'), reason='requires disposable MySQL')
def test_mysql_migration_concurrent_claim_and_report():
    url=os.environ['NOTIFIER_TEST_DATABASE_URL']
    from sqlalchemy.engine import make_url
    assert make_url(url).database=='notification_test', 'Only the disposable notification_test database is allowed'
    app=create_app(Settings(url, notification_owner_admin_id=1))
    migrate(app.state.engine,app.state.sessions)
    # Exercise the real 11 -> 12 path after initial schema bootstrap.
    NotificationTask.__table__.drop(app.state.engine)
    NotificationClient.__table__.drop(app.state.engine)
    with app.state.sessions() as db:
        db.get(SchemaVersion,SCHEMA_VERSION).version=11
        db.commit()
    migrate(app.state.engine,app.state.sessions)
    migrate(app.state.engine,app.state.sessions)
    with app.state.sessions() as db:
        db.add(Admin(id=1,username='mysql-owner',password_hash='unused',role='admin'))
        client=db.get(NotificationClient,1)
        client.owner_admin_id=1;client.enabled=True;client.token_hash=digest('mysql-test-token')
        client.installation_id='mysql-test-installation';client.expires_at=now()+timedelta(days=1)
        for i in range(8):
            item=AccessApplication(username=f'mysql{i}',display_name='Test',pending_username=f'mysql{i}',token_hash=f'{i:064x}')
            db.add(item);enqueue(db,item)
        db.commit()
    ident={'installation_id':'mysql-test-installation','protocol_version':1}
    headers={'Authorization':'Bearer mysql-test-token'}
    base='/cli-permission/api/v1/notifications'
    with TestClient(app) as client:
        def claim(_):
            result=client.post(base+'/claim',json=ident,headers=headers)
            assert result.status_code==200,result.text
            return result.json()['task']
        with ThreadPoolExecutor(max_workers=4) as pool:
            tasks=list(pool.map(claim,range(4)))
        # Lost-response recovery intentionally reissues the same unprepared task;
        # only the newest lease may prepare or send.
        assert len({t['id'] for t in tasks})==1
        ordered=sorted(tasks,key=lambda t:t['lease_generation'])
        for task in ordered[:-1]:
            body={**ident,'lease_token':task['lease_token'],'lease_generation':task['lease_generation'],
                  'snapshot_id':'mysql-snapshot','delivery_ids':['mysql-delivery']}
            assert client.post(base+f"/{task['id']}/prepare",json=body,headers=headers).status_code==409
        task=ordered[-1]
        body={**ident,'lease_token':task['lease_token'],'lease_generation':task['lease_generation']}
        assert client.post(base+f"/{task['id']}/prepare",json={**body,'snapshot_id':'mysql-snapshot','delivery_ids':['mysql-delivery']},headers=headers).status_code==200
        for seq,state in enumerate(('sending','accepted'),1):
            response=client.post(base+f"/{task['id']}/result",headers=headers,json={**body,
                'report_id':f'mysql-report-{seq}','report_seq':seq,'updates':[{
                    'delivery_id':'mysql-delivery','attempt_id':'mysql-attempt','state':state}]})
            assert response.status_code==200,response.text
        assert response.json()['status']=='sent'
    app.state.engine.dispose()


@pytest.mark.skipif(not os.environ.get('NOTIFIER_TEST_DATABASE_URL'), reason='requires disposable MySQL')
def test_mysql_schema_13_upgrade_keeps_old_logs_and_stores_complete_commands():
    from sqlalchemy.engine import make_url

    url = os.environ['NOTIFIER_TEST_DATABASE_URL']
    assert make_url(url).database == 'notification_test', 'Only the disposable notification_test database is allowed'
    app = create_app(Settings(url))
    engine, sessions = app.state.engine, app.state.sessions
    old_text = 'ml jupyter exec "[REDACTED EXEC]"'
    new_text = "ml jupyter exec -- python -c 'print(\"测试😀\")\n# " + '参数😀' * 10000 + "'"
    try:
        migrate(engine, sessions)
        with engine.begin() as connection:
            connection.execute(text('ALTER TABLE cli_call_logs MODIFY COLUMN full_command TEXT NULL'))
            connection.execute(text('UPDATE schema_versions SET version=13'))
        with sessions() as db:
            old = CallLog(actor='mysql-audit-legacy', command='ml jupyter exec', full_command=old_text,
                          environment='test', business_id='demo', source_ip='', allowed=False, reason='USER_DISABLED')
            db.add(old)
            db.commit()
        migrate(engine, sessions)
        migrate(engine, sessions)
        columns = {column['name']: column['type'] for column in inspect(engine).get_columns('cli_call_logs')}
        assert isinstance(columns['full_command'], LONGTEXT)
        with TestClient(app) as client:
            result = client.post('/cli-permission/api/v1/access/check', headers={'businessid': 'demo'}, json={
                'username': 'mysql-audit-full', 'environment': 'test', 'platform_origin': 'https://test.example.com',
                'command': 'ml jupyter exec', 'full_command': new_text,
            })
            assert result.status_code == 200
        with sessions() as db:
            assert db.get(SchemaVersion, SCHEMA_VERSION)
            assert db.get(CallLog, old.id).full_command == old_text
            query = select(CallLog.full_command).where(CallLog.actor == 'mysql-audit-full').order_by(CallLog.id.desc())
            assert db.scalar(query.limit(1)) == new_text
    finally:
        engine.dispose()
