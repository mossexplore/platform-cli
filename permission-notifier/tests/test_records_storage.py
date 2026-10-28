import copy
import json
from datetime import datetime, timezone
import pytest
from permission_notifier.store import Store, StoreError, initial
from permission_notifier.records import begin, finish, query, recover_interrupted
from permission_notifier.worker import Worker
from test_store_sender import configured


def test_split_files_and_independent_atomic_writes(tmp_path):
    store=Store(tmp_path/'assistant.json');configured(store)
    settings=json.loads(store.path.read_text());runtime=json.loads(store.records_path.read_text())
    assert settings['file_version']==2 and 'tasks' not in settings['state']
    assert 'config' not in runtime and 'auth-value' not in store.records_path.read_text()
    before_config=store.path.read_bytes()
    rid=begin(store,'test-task','test','001','hello');finish(store,rid,{'state':'accepted'})
    assert store.path.read_bytes()==before_config
    before_records=store.records_path.read_bytes()
    public=store.public_config();public['config']['poll_interval_seconds']=12
    store.configure(public['config_revision'],public['config'],{})
    assert store.records_path.read_bytes()==before_records
    assert Store(store.path).snapshot()==store.snapshot()


def test_legacy_migration_and_old_timestamp_is_not_fabricated(tmp_path):
    path=tmp_path/'assistant.json';data=initial()
    data['config']['assistant_token']='keep-token'
    data['state']['tasks']['legacy-task']={'closed':True,'content':'old content','updated_at':123,
        'deliveries':{'d':{'uid':'001','state':'accepted','attempts':1}}}
    path.write_text(json.dumps(data))
    store=Store(path)
    assert not store.fault
    assert json.loads(path.read_text())['file_version']==2
    assert store.snapshot()['config']['assistant_token']=='keep-token'
    result=query(store.snapshot())['items'][0]
    assert result['sent_at'] is None and result['content']=='old content'
    # Retiring recovery checkpoints does not delete the history.
    store.change(lambda d:d['state']['tasks'].clear())
    assert len(query(Store(path).snapshot())['items'])==1


def test_missing_or_corrupt_runtime_fails_closed(tmp_path):
    store=Store(tmp_path/'assistant.json');configured(store)
    store.records_path.unlink()
    restored=Store(store.path)
    assert restored.fault
    with pytest.raises(StoreError):restored.change(lambda d:None)
    assert not store.records_path.exists()
    store.records_path.write_text('{broken')
    assert Store(store.path).fault


def test_record_write_failure_does_not_modify_settings(tmp_path,monkeypatch):
    store=Store(tmp_path/'assistant.json');configured(store)
    before=store.path.read_bytes();runtime=store.records_path.read_bytes()
    def fail(*a):raise OSError('disk full')
    monkeypatch.setattr('permission_notifier.storage_files.os.replace',fail)
    with pytest.raises(StoreError):begin(store,'task','test','001','hello')
    assert store.path.read_bytes()==before and store.records_path.read_bytes()==runtime
    assert not store.snapshot()['state']['send_records']


def test_interrupted_migration_is_repeatable(tmp_path,monkeypatch):
    from permission_notifier import storage_files
    path=tmp_path/'assistant.json';data=initial();path.write_text(json.dumps(data));before=path.read_bytes()
    original=storage_files.os.replace
    def fail_config(src,dest):
        if str(dest)==str(path):raise OSError('config replace interrupted')
        return original(src,dest)
    monkeypatch.setattr(storage_files.os,'replace',fail_config)
    assert Store(path).fault
    assert path.read_bytes()==before
    monkeypatch.setattr(storage_files.os,'replace',original)
    assert not Store(path).fault


def test_history_filters_beijing_boundaries_and_pages(tmp_path):
    store=Store(tmp_path/'assistant.json')
    rid=begin(store,'one','permission','001','你好')
    epoch=datetime(2026,10,28,2,0,tzinfo=timezone.utc).timestamp()
    def seed(data):
        data['state']['send_records'][rid]['sent_at']=epoch
        for i in range(12):
            data['state']['send_records']['test-'+str(i)]={'id':'test-'+str(i),'task_id':'t-'+str(i),
                'source':'test','sent_at':epoch+i+1,'uid':'002','content':'test','state':'accepted','delivery_id':None}
    store.change(seed)
    data=store.snapshot()
    assert query(data,start='2026-10-28T10:00:00',end='2026-10-28T10:00:00')['total']==1
    assert query(data,source='test')['total']==12
    assert len(query(data,source='test',page=2)['items'])==2
    assert query(data,start='2026-10-28T10:00:13')['total']==0
    with pytest.raises(ValueError):query(data,start='2026-10-29',end='2026-10-28')
    with pytest.raises(ValueError):query(data,source='unknown')


def test_restart_marks_inflight_history_uncertain(tmp_path):
    store=Store(tmp_path/'assistant.json');rid=begin(store,'task','test','001','hello')
    restored=Store(store.path);recover_interrupted(restored)
    assert restored.snapshot()['state']['send_records'][rid]['state']=='uncertain'


def test_test_send_history_survives_restart(tmp_path):
    class Sender:
        def send(self,*a):return {'state':'accepted','http_status':200,'error_code':'','diagnostic':{'response_summary':'private'}}
    store=Store(tmp_path/'assistant.json');config=configured(store)
    worker=Worker(store,sender=Sender());worker.queue_test(config,['001','002'])
    worker.run_test();worker.run_test()
    records=query(Store(store.path).snapshot(),source='test')['items']
    assert len(records)==2 and len({r['task_id'] for r in records})==1
    assert all(r['sent_at'] and r['content']=='【测试】权限通知助手连接验证' for r in records)
    assert 'private' not in store.records_path.read_text()


def test_end_filter_includes_whole_displayed_second(tmp_path):
    store=Store(tmp_path/'assistant.json');rid=begin(store,'task','test','001','test')
    value=datetime(2026,10,28,2,0,tzinfo=timezone.utc).timestamp()+.8
    store.change(lambda d:d['state']['send_records'][rid].update(sent_at=value))
    assert query(store.snapshot(),end='2026-10-28T10:00:00')['total']==1
    assert query(store.snapshot(),end='2026-10-28T09:59:59')['total']==0
