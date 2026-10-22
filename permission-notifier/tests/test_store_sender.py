import copy
import json
import httpx
import pytest
from permission_notifier.store import Store, StoreError, Conflict, effective
from permission_notifier.sender import Sender
from permission_notifier.config import Config


def configured(store):
    values=Config().model_dump()
    values.update(permission_service_url='https://permission.example',assistant_token='token-value')
    values['message'].update(url='http://message.example',auth='auth-value',success_mode='http_2xx',
        receivers=[{'uid':'001','label':'A','enabled':True},{'uid':'002','label':'B','enabled':True}])
    store.configure(1,values,{'assistant_token':{'action':'replace','value':'token-value'},'auth':{'action':'replace','value':'auth-value'}})
    return store.snapshot()['config']


def test_file_roundtrip_secret_mask_and_revision(tmp_path):
    store=Store(tmp_path/'assistant.json');configured(store)
    assert json.loads(store.path.read_text())['config']['message']['auth']=='auth-value'
    public=store.public_config()
    assert 'auth-value' not in json.dumps(public) and 'token-value' not in json.dumps(public)
    assert Store(store.path).snapshot()==store.snapshot()
    with pytest.raises(Conflict): store.configure(1,public['config'],{})
    store.configure(public['config_revision'],public['config'],{})
    assert store.snapshot()['config']['message']['auth']=='auth-value'


def test_atomic_write_failure_and_corrupt_recovery(tmp_path,monkeypatch):
    store=Store(tmp_path/'assistant.json');configured(store)
    before=store.path.read_bytes()
    def fail(*a): raise OSError('disk full')
    monkeypatch.setattr('permission_notifier.store.os.replace',fail)
    with pytest.raises(StoreError): store.change(lambda d:d['state'].update(paused=False))
    assert store.path.read_bytes()==before and store.snapshot()['state']['paused']
    store.path.write_text('{broken')
    broken=Store(store.path)
    assert broken.fault
    with pytest.raises(StoreError): broken.change(lambda d:None)
    assert store.path.read_text()=='{broken'


def test_pending_service_switch_preserves_old_connection(tmp_path):
    store=Store(tmp_path/'assistant.json');config=configured(store)
    store.change(lambda d:d['state']['tasks'].update({'task':{'closed':False}}))
    config['permission_service_url']='https://new.example'
    result=store.configure(2,config,{'assistant_token':{'action':'replace','value':'new-token'}})
    assert result['apply_state']=='waiting_action'
    assert effective(store.snapshot())['assistant_token']=='token-value'
    restored=Store(store.path)
    assert effective(restored.snapshot())['permission_service_url']=='https://permission.example'
    restored.change(lambda d:d['state']['tasks']['task'].update(closed=True))
    restored.apply_pending()
    assert effective(restored.snapshot())['assistant_token']=='new-token'
    assert restored.snapshot()['state']['config_apply']['effective_overrides']=={}


def test_cancel_switch_retains_active_credential(tmp_path):
    store=Store(tmp_path/'assistant.json');config=configured(store)
    store.change(lambda d:d['state']['tasks'].update({'task':{'closed':False}}))
    config['permission_service_url']='https://new.example'
    store.configure(2,config,{'assistant_token':{'action':'replace','value':'new-token'}})
    public=store.public_config();public['config']['permission_service_url']='https://permission.example'
    store.configure(public['config_revision'],public['config'],{})
    assert effective(store.snapshot())['assistant_token']=='token-value'
    assert not store.snapshot()['state']['config_apply']['pending_fields']


def test_each_post_exact_fields_and_no_automatic_retry(tmp_path):
    config=configured(Store(tmp_path/'assistant.json'));seen=[]
    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200,json={'ok':True})
    sender=Sender(lambda *_:httpx.Client(transport=httpx.MockTransport(handler)))
    for uid in ('001','002'): assert sender.send(config,config['message'],uid,'hello')['state']=='accepted'
    assert seen==[{'content':'hello','receiver':uid,'auth':'auth-value'} for uid in ('001','002')]
    config['message']['success_mode']='unconfirmed'
    assert sender.send(config,config['message'],'001','hello')['state']=='uncertain'
    def timeout(request): raise httpx.ReadTimeout('must not expose auth')
    sender=Sender(lambda *_:httpx.Client(transport=httpx.MockTransport(timeout)))
    assert sender.send(config,config['message'],'001','hello')['state']=='uncertain'


def test_business_success_requires_exact_type(tmp_path):
    config=configured(Store(tmp_path/'assistant.json'))
    config['message'].update(success_mode='json_equals',success_field='data.code',success_value='0')
    sender=Sender(lambda *_:httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json={'data':{'code':False}}))))
    assert sender.send(config,config['message'],'001','x')['state']=='uncertain'
