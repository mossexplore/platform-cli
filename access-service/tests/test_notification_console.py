"""Console regressions: permissions, one-time tokens, filtering and safe retries."""
import json
import re
from datetime import timedelta
from types import SimpleNamespace
from sqlalchemy import select
import pytest
from app.models import Admin, AccessApplication, now
from app.notification_models import NotificationClient, NotificationTask
from app.notification_views import client_summary
from test_service import system, login

BASE = '/cli-permission/admin/notifications'


def prepare(system):
    app, client, _ = system
    app.state.settings.notification_owner_admin_id = 1
    return app, client, login(client)


def seed(app, states, approved=False):
    with app.state.sessions() as db:
        application = AccessApplication(username='notify-user', display_name='通知测试人员',
                                        token_hash='console-test-token', status='approved' if approved else 'pending')
        db.add(application)
        db.flush()
        task = NotificationTask(application_id=application.id, event_key='console-test',
                                status='partial', data=json.dumps({'deliveries': {
                                    str(i): {'state': state} for i, state in enumerate(states)}, 'reports': {}, 'actions': {}}))
        db.add(task)
        db.commit()
        return task.id


@pytest.mark.parametrize('role', ['admin', 'super_admin'])
def test_owner_navigation_and_permissions(system, role):
    app, client, _ = prepare(system)
    with app.state.sessions() as db:
        db.get(Admin, 1).role = role
        db.commit()
    page = client.get(BASE)
    assert page.status_code == 200
    assert re.search(r'个人设置\s*<span>/</span>\s*<strong>个人通知', page.text)
    assert 'nav-icon' in page.text.split('href="'+BASE+'"')[1].split('</a>')[0]
    app.state.settings.notification_owner_admin_id = 999
    assert 'href="'+BASE+'"' not in client.get('/cli-permission/admin').text
    denied = client.get(BASE)
    assert denied.status_code == 403 and '通知所有者' in denied.text
    client.cookies.clear()
    assert client.get(BASE).status_code == 401


def test_console_localizes_and_only_retries_failed_items(system):
    app, client, csrf = prepare(system)
    task_id = seed(app, ['accepted', 'failed', 'uncertain'])
    html = client.get(BASE).text
    assert '通知测试人员' in html and '接口已接受 1 · 失败 1 · 结果不确定 1' in html
    assert "{'accepted':" not in html
    assert '重试失败项（1）' in html
    response = client.post(BASE+f'/{task_id}/retry', data={'csrf':csrf, 'q':'notify-user', 'status':'partial'})
    assert response.status_code == 200 and '已请求重试 1 个失败项' in response.text
    assert 'value="notify-user"' in response.text and 'value="partial" selected' in response.text
    with app.state.sessions() as db:
        task = db.get(NotificationTask, task_id)
        data = json.loads(task.data)
        assert data['actions'] == {'1':'retry'}
        assert data['deliveries']['2']['state'] == 'uncertain'
    repeat = client.post(BASE+f'/{task_id}/retry', data={'csrf':csrf})
    assert '重试请求已提交' in repeat.text


@pytest.mark.parametrize('states,approved', [(['accepted'], False), (['uncertain'], False), (['failed'], True)])
def test_ineligible_retries_do_not_change_tasks(system, states, approved):
    app, client, csrf = prepare(system)
    task_id = seed(app, states, approved)
    assert '重试失败项（' not in client.get(BASE).text
    response = client.post(BASE+f'/{task_id}/retry', data={'csrf':csrf})
    assert response.status_code == (409 if approved else 200)
    assert ('申请已处理' if approved else '没有可重试') in response.text
    with app.state.sessions() as db:
        assert json.loads(db.get(NotificationTask, task_id).data)['actions'] == {}


def test_pagination_filters_and_literal_search(system):
    app, client, _ = prepare(system)
    with app.state.sessions() as db:
        a = AccessApplication(username='notify-user', display_name='分页人员', token_hash='paging')
        db.add(a); db.flush()
        for i in range(13):
            db.add(NotificationTask(application_id=a.id, event_key=f'paging-{i}', status='sent' if i < 11 else 'failed'))
        db.commit()
    html = client.get(BASE+'?q=notify-user&status=sent&page=2').text
    assert '共 11 条' in html and '第 2 / 2 页' in html
    assert html.count('class="notification-time"') == 1
    assert '暂无匹配的通知记录' in client.get(BASE+'?q=%25').text
    assert '共 13 条' in client.get(BASE+f'?q={a.id}').text
    assert '第 2 / 2 页' in client.get(BASE+'?page=999').text


def test_token_json_one_time_generation_and_csrf(system):
    app, client, csrf = prepare(system)
    response = client.post(BASE+'/token', data={'csrf':csrf, 'confirmation':'reset', 'generation':0},
                           headers={'Accept':'application/json'})
    assert response.status_code == 200
    body = response.json()
    raw = body['token']
    assert raw in body['html'] and raw not in body['url']
    assert 'no-store' in response.headers['cache-control']
    assert '待绑定' in body['html']
    assert raw not in client.get(BASE).text
    repeat = client.post(BASE+'/token', data={'csrf':csrf, 'confirmation':'reset', 'generation':0},
                         headers={'Accept':'application/json'})
    assert repeat.status_code == 409
    with app.state.sessions() as db:
        assert db.get(NotificationClient,1).credential_generation == 1
    assert client.post(BASE+'/revoke',data={'csrf':'wrong'}).status_code == 403
    revoked = client.post(BASE+'/revoke', data={'csrf':csrf})
    assert 'Token 已撤销' in revoked.text and '已撤销' in revoked.text
    with app.state.sessions() as db:
        assert not db.get(NotificationClient,1).token_hash
        assert db.get(NotificationClient,1).last_seen_at is None


def test_backfill_feedback_and_missing_task(system):
    app, client, csrf = prepare(system)
    denied = client.post(BASE+'/backfill', data={'csrf':csrf})
    assert denied.status_code == 400 and '请先开启并保存' in denied.text
    client.post(BASE+'/enabled', data={'csrf':csrf, 'enabled':'true'})
    assert '没有需要补建' in client.post(BASE+'/backfill',data={'csrf':csrf}).text
    with app.state.sessions() as db:
        db.add(AccessApplication(username='history',display_name='历史人员',token_hash='history'))
        db.commit()
    assert '已补建 1 条' in client.post(BASE+'/backfill',data={'csrf':csrf}).text
    assert '没有需要补建' in client.post(BASE+'/backfill',data={'csrf':csrf}).text
    missing = client.post(BASE+'/missing/retry',data={'csrf':csrf})
    assert missing.status_code == 404 and '通知记录不存在' in missing.text


@pytest.mark.parametrize('health', ['running','paused','network_error','auth_error','worker_error',
                                   'storage_error','needs_attention','unconfigured','future-state'])
def test_connection_does_not_imply_running_or_valid_credentials(health):
    at = now()
    client = SimpleNamespace(token_hash='hash',credential_generation=1,installation_id='test',
        expires_at=at+timedelta(days=1),last_seen_at=at,health_code=health,enabled=True)
    summary = client_summary(client, at)
    assert summary[0]['label'] == '连接正常'
    assert summary[1]['label'] != health
    client.token_hash = ''
    summary = client_summary(client, at)
    assert summary[0]['tone'] != 'positive' and summary[1]['label'] == '等待连接'
    assert summary[3]['label'] == '已撤销'
    client.token_hash = 'hash'; client.expires_at = at-timedelta(seconds=1)
    assert client_summary(client,at)[3]['label'] == '已过期'
    client.installation_id = ''; client.bind_deadline = at+timedelta(minutes=30)
    assert client_summary(client,at)[3]['label'] == '待绑定'
    client.bind_deadline = at-timedelta(seconds=1)
    assert client_summary(client,at)[3]['label'] == '绑定已超时'
