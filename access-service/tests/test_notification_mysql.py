"""Opt-in disposable MySQL verification; never point at a production database."""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, inspect
from app.main import create_app
from app.settings import Settings
from app.migrations import migrate, SCHEMA_VERSION
from app.models import Admin, AccessApplication, SchemaVersion, now
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
