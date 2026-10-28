import pytest
from permission_notifier.record_fields import applicant_fields
from permission_notifier.records import begin,query
from permission_notifier.store import Store
from permission_notifier.worker import Worker
from test_store_sender import configured


def test_permission_fields_and_beijing_time_conversion():
    message='【权限申请待审批】\n申请人：张三\n账号：alice\n申请时间：2026-10-28T02:30:00.000+00:00\n审批地址：https://example.com'
    assert applicant_fields('permission',message)=={'applicant_name':'张三','applicant_account':'alice','application_time':'2026-10-28 10:30:00'}
    assert applicant_fields('permission',message.replace('：',':'))['applicant_account']=='alice'
    assert set(applicant_fields('test',message).values())=={'-'}


def test_missing_lines_do_not_consume_next_field():
    fields=applicant_fields('permission','申请人：\n账号：alice\n申请时间：not-a-date')
    assert fields=={'applicant_name':'-','applicant_account':'alice','application_time':'-'}
    assert set(applicant_fields('permission','random message').values())=={'-'}
    assert applicant_fields('permission','申请时间：2026-10-28')['application_time']=='-'


def test_history_api_view_fields_are_derived_from_existing_messages(tmp_path):
    store=Store(tmp_path/'assistant.json')
    begin(store,'task','permission','001','申请人：李四\n账号：test-account\n申请时间：2026-10-28 14:30:00')
    row=query(store.snapshot())['items'][0]
    assert row['applicant_name']=='李四' and row['application_time']=='2026-10-28 14:30:00'


def test_custom_test_content_is_sent_and_persisted_as_snapshot(tmp_path):
    sent=[]
    class Sender:
        def send(self,config,route,uid,content):
            sent.append((uid,content));return {'state':'accepted'}
    store=Store(tmp_path/'assistant.json');config=configured(store)
    worker=Worker(store,sender=Sender())
    content='自定义测试消息\n第二行 <script>只是文本</script>'
    worker.queue_test(config,['001','002'],content)
    worker.run_test();worker.run_test()
    assert sent==[('001',content),('002',content)]
    rows=query(Store(store.path).snapshot())['items']
    assert len(rows)==2 and all(r['content']==content and r['applicant_name']=='-' for r in rows)


@pytest.mark.parametrize('content',['','  \n',None,42,'x'*10001])
def test_invalid_test_content_is_not_enqueued(tmp_path,content):
    store=Store(tmp_path/'assistant.json');config=configured(store);worker=Worker(store)
    with pytest.raises(ValueError):worker.queue_test(config,['001'],content)
    assert not worker.tests
