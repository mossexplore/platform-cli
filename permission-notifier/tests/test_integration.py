"""Opt-in cross-project tests: set PERMISSION_SERVICE_SOURCE to access-service."""
import os
import re
import sys
from pathlib import Path
import pytest

source = os.environ.get('PERMISSION_SERVICE_SOURCE')
if not source:
    pytest.skip('PERMISSION_SERVICE_SOURCE is needed for service integration', allow_module_level=True)
sys.path.insert(0, source)
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.settings import Settings
from app.migrations import migrate
from app.models import Admin, AccessApplication
from app.notification_models import NotificationClient, NotificationTask, enqueue
from app.security import digest
from datetime import timedelta
from app.models import now
from permission_notifier.store import Store
from permission_notifier.worker import Worker
from permission_notifier.service import ServiceError
from test_store_sender import configured


class ServiceBridge:
    def __init__(self, client):
        self.client=client
        self.drop_success=False
        self.drop_sending=False

    def call(self, config, installation, endpoint, body=None):
        response=self.client.post('/cli-permission/api/v1/notifications/'+endpoint,
            headers={'Authorization':'Bearer '+config['assistant_token']},
            json={'protocol_version':1,'installation_id':installation,**(body or {})})
        if not response.is_success:
            raise ServiceError(response.json()['detail'],response.status_code)
        states=[x['state'] for x in (body or {}).get('updates',[])]
        if self.drop_success and 'accepted' in states:
            self.drop_success=False
            raise ServiceError('SERVICE_UNAVAILABLE')
        if self.drop_sending and 'sending' in states:
            self.drop_sending=False
            raise ServiceError('SERVICE_UNAVAILABLE')
        return response.json()


class FakeSender:
    def __init__(self, outcomes=None): self.calls=[];self.outcomes=outcomes or {}
    def send(self, config, route, uid, content):
        self.calls.append(uid)
        return self.outcomes.get(uid,{'state':'accepted','error_code':''})


@pytest.fixture
def pair(tmp_path):
    app=create_app(Settings('sqlite:///'+str(tmp_path/'server.db'),secure_cookie=False,notification_owner_admin_id=1))
    migrate(app.state.engine,app.state.sessions)
    with app.state.sessions() as db:
        db.add(Admin(id=1,username='owner',password_hash='unused',role='admin'))
        client=db.get(NotificationClient,1)
        client.owner_admin_id=1;client.enabled=True;client.token_hash=digest('token-value')
        client.bind_deadline=now()+timedelta(minutes=30)
        application=AccessApplication(username='applicant',display_name='申请人',pending_username='applicant',token_hash='a'*64)
        db.add(application);enqueue(db,application);db.commit()
    with TestClient(app) as client:
        store=Store(tmp_path/'assistant.json');configured(store)
        store.change(lambda d:d['state'].update(paused=False))
        bridge=ServiceBridge(client)
        sender=FakeSender()
        worker=Worker(store,bridge,sender)
        yield app,store,bridge,sender,worker
    app.state.engine.dispose()


def test_multi_recipient_partial_and_retry_only_failed(pair):
    app,store,bridge,sender,worker=pair
    sender.outcomes={'002':{'state':'failed','error_code':'RECEIVER_REJECTED'}}
    worker.tick();worker.tick();worker.tick()
    assert sender.calls==['001','002']
    task_id=next(iter(store.snapshot()['state']['tasks']))
    with app.state.sessions() as db:
        assert db.get(NotificationTask,task_id).status=='partial'
    key=next(k for k,v in store.snapshot()['state']['tasks'][task_id]['deliveries'].items() if v['uid']=='002')
    sender.outcomes={}
    worker.resolve(task_id,key,'retry')
    worker.tick()
    assert sender.calls==['001','002','002']
    assert store.snapshot()['state']['tasks'][task_id]['closed']


def test_success_report_response_lost_restarts_without_resend(pair):
    app,store,bridge,sender,worker=pair
    worker.tick()
    bridge.drop_success=True
    with pytest.raises(ServiceError): worker.tick()
    assert sender.calls==['001']
    assert len(store.snapshot()['state']['pending_reports'])==1
    restarted=Worker(Store(store.path),bridge,sender)
    restarted.tick()
    assert sender.calls==['001','002']
    restarted.tick()
    assert sender.calls==['001','002']
    assert not restarted.store.snapshot()['state']['pending_reports']


def test_crash_after_sending_checkpoint_is_uncertain_not_resent(pair):
    app,store,bridge,sender,worker=pair
    worker.tick()
    bridge.drop_sending=True
    with pytest.raises(ServiceError): worker.tick()
    assert sender.calls==[]
    restarted=Worker(Store(store.path),bridge,sender)
    restarted.tick()
    assert sender.calls==['002']
    task=next(iter(restarted.store.snapshot()['state']['tasks'].values()))
    assert next(i for i in task['deliveries'].values() if i['uid']=='001')['state']=='uncertain'


def test_pause_route_and_receiver_updates_preserve_snapshot(pair):
    app,store,bridge,sender,worker=pair
    worker.tick();worker.tick()
    data=store.snapshot();values=data['config']
    values['message']['receivers']=[{'uid':'003','label':'new','enabled':True}]
    store.configure(data['config_revision'],values,{})
    worker.tick()
    assert sender.calls==['001','002']


def test_uncertain_does_not_block_later_application(pair):
    app,store,bridge,sender,worker=pair
    sender.outcomes={'001':{'state':'uncertain','error_code':'TIMEOUT'}}
    worker.tick();worker.tick();worker.tick()
    with app.state.sessions() as db:
        application=AccessApplication(username='second',display_name='第二人',pending_username='second',token_hash='b'*64)
        db.add(application);enqueue(db,application);db.commit()
    worker.last_poll=0
    worker.tick();worker.tick();worker.tick()
    assert sender.calls==['001','002','001','002']


def test_auth_rejection_survives_restart_and_new_auth_resumes(pair):
    app,store,bridge,sender,worker=pair
    sender.outcomes={'001':{'state':'failed','error_code':'MESSAGE_AUTH_REJECTED'}}
    worker.tick();worker.tick()
    restarted=Worker(Store(store.path),bridge,sender)
    restarted.tick()
    assert sender.calls==['001']
    data=restarted.store.snapshot()
    restarted.store.configure(data['config_revision'],data['config'],{'auth':{'action':'replace','value':'new-auth'}})
    sender.outcomes={}
    restarted.tick();restarted.tick()
    assert sender.calls==['001','001','002']


def test_route_change_requires_explicit_migration(pair):
    app,store,bridge,sender,worker=pair
    worker.tick();worker.tick()
    data=store.snapshot();values=data['config'];values['message']['url']='http://other-message.example'
    store.configure(data['config_revision'],values,{})
    worker.tick()
    assert sender.calls==['001'] and worker.error=='ROUTE_CHANGE_NEEDS_ACTION'
    task_id=next(iter(store.snapshot()['state']['tasks']))
    worker.resolve(task_id,'','migrate_route')
    worker.tick()
    assert sender.calls==['001','002']
