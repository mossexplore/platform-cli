import json
import re
from datetime import timedelta
import pytest
from sqlalchemy import select, func, inspect
from app.models import AccessApplication, ApplicationAttempt, User, Environment, Grant, Audit, SchemaVersion, now
from app.migrations import migrate, SCHEMA_VERSION
from test_service import system, login, check


def submit(client, username='l00123456', name='张三'):
    page = client.get('/cli-permission/apply')
    csrf = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    return client.post('/cli-permission/apply', data={'csrf': csrf, 'username': username, 'display_name': name}, follow_redirects=False)


def application_id(app, username='l00123456'):
    with app.state.sessions() as db:
        return db.scalar(select(AccessApplication.id).where(AccessApplication.username == username))


def preview(client, csrf, item_id, username='l00123456', name='张三'):
    return client.post(f'/cli-permission/admin/applications/{item_id}/preview', data={
        'csrf': csrf, 'username': username, 'display_name': name})


def approval(client, csrf, item_id, username='l00123456', name='张三', **extra):
    response = preview(client, csrf, item_id, username, name)
    assert response.status_code == 200, response.text
    snapshot = re.search('name="snapshot" value="([^"]+)"', response.text)[1]
    return {'csrf': csrf, 'username': username, 'display_name': name, 'snapshot': snapshot,
            'environments': re.findall('name="environments" value="([^"]+)" checked', response.text), **extra}


def test_public_form_private_receipt_and_duplicate(system):
    app, client, _ = system
    page = client.get('/cli-permission/apply')
    assert 'W3账号' in page.text and 'l00123456' in page.text
    response = submit(client)
    assert response.status_code == 303
    receipt = response.headers['location']
    assert '待审批' in client.get(receipt).text
    assert client.get('/cli-permission/apply/status/' + 'x'*43).status_code == 404
    assert client.get('/cli-permission/apply/status/1').status_code == 404
    assert submit(client, name='不能覆盖').status_code == 200
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AccessApplication)) == 1
        item = db.scalar(select(AccessApplication))
        assert item.display_name == '张三' and item.token_hash not in receipt
        assert db.scalar(select(User).where(User.username == item.username)) is None
    assert check(client, username='l00123456').json()['allowed'] is False


def test_approval_corrected_identity_all_enabled_and_audit(system):
    app, client, _ = system
    with app.state.sessions() as db:
        db.add_all([Environment(name='dev', display_name='开发', platform_origin='https://dev.example.com'),
                    Environment(name='off', display_name='停用', platform_origin='https://off.example.com', enabled=False)])
        db.commit()
    receipt = submit(client).headers['location']
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id, username='l00999999', name='李四')
    assert len(data['environments']) == 2
    url = f'/cli-permission/admin/applications/{item_id}/approve'
    response = client.post(url, data=data)
    assert response.status_code == 200, response.text
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username == 'l00999999'))
        assert user.display_name == '李四'
        grants = db.scalars(select(Grant).where(Grant.user_id == user.id)).all()
        assert len(grants) == 2 and all(g.enabled and g.expires_at is None for g in grants)
        item = db.get(AccessApplication, item_id)
        assert (item.username, item.display_name, item.approved_username) == ('l00123456', '张三', 'l00999999')
        assert item.pending_username is None and item.reviewed_by == 'admin'
        audit = db.scalar(select(Audit).where(Audit.action == 'applications.approve'))
        assert json.loads(audit.detail)['corrected']['name'] == '李四'
    assert check(client, username='l00999999').json()['allowed'] is True
    assert 'l00999999' in client.get(receipt).text
    assert client.post(url, data=data).status_code == 409
    assert client.post(f'/cli-permission/admin/applications/{item_id}/reject', data={'csrf':csrf,'reason':'重复'}).status_code == 409


def test_reject_requires_reason_and_allows_reapplication(system):
    app, client, _ = system
    receipt = submit(client).headers['location']
    csrf = login(client)
    url = f'/cli-permission/admin/applications/{application_id(app)}/reject'
    assert client.post(url, data={'csrf':csrf, 'reason':' '}).status_code == 400
    assert client.post(url, data={'csrf':csrf, 'reason':'请核实账号'}).status_code == 200
    assert '请核实账号' in client.get(receipt).text
    assert submit(client).status_code == 303
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AccessApplication)) == 2
        assert db.scalar(select(User).where(User.username == 'l00123456')) is None


def test_existing_person_confirmation_name_and_grant_preservation(system):
    app, client, _ = system
    with app.state.sessions() as db:
        grant = db.get(Grant, 1)
        grant.expires_at = now() + timedelta(days=10)
        grant.note = '原备注'
        original_expiry = grant.expires_at
        db.commit()
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id, username='alice', name='新姓名')
    url = f'/cli-permission/admin/applications/{item_id}/approve'
    assert client.post(url, data=data).status_code == 400
    data['confirm_existing'] = 'true'
    assert client.post(url, data=data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(User, 1).display_name == 'Alice'
        assert db.get(Grant, 1).expires_at == original_expiry
        assert db.get(Grant, 1).note == '原备注'
    submit(client, 'l00222222')
    second = application_id(app, 'l00222222')
    data = approval(client, csrf, second, username='alice', name='新姓名', confirm_existing='true', update_name='true')
    assert client.post(f'/cli-permission/admin/applications/{second}/approve', data=data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(User, 1).display_name == '新姓名'


@pytest.mark.parametrize('change', ['environment', 'person', 'grant', 'duplicate'])
def test_stale_preview_rolls_back_decision(system, change):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id, username='alice', confirm_existing='true')
    with app.state.sessions() as db:
        if change == 'environment':
            db.add(Environment(name='new', display_name='新增', platform_origin='https://new.example.com'))
        elif change == 'person':
            db.get(User, 1).enabled = False
        elif change == 'grant':
            db.get(Grant, 1).enabled = False
        else:
            db.add(AccessApplication(username='alice', display_name='A', pending_username='alice', token_hash='a'*64))
        db.commit()
    assert client.post(f'/cli-permission/admin/applications/{item_id}/approve', data=data).status_code == 409
    with app.state.sessions() as db:
        assert db.get(AccessApplication, item_id).status == 'pending'
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='applications.approve')) == 0


def test_restoring_revoked_grant_requires_explicit_confirmation(system):
    app, client, _ = system
    with app.state.sessions() as db:
        db.get(Grant, 1).enabled = False
        db.commit()
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id, username='alice', confirm_existing='true', update_name='true')
    url = f'/cli-permission/admin/applications/{item_id}/approve'
    assert client.post(url, data=data).status_code == 400
    with app.state.sessions() as db:
        assert db.get(User, 1).display_name == 'Alice'
        assert db.get(AccessApplication, item_id).status == 'pending'
    data['restore_grants'] = 'true'
    data['expires_at'] = '2035-01-01T08:00:00'
    assert client.post(url, data=data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Grant, 1).expires_at.isoformat() == '2035-01-01T00:00:00'


def test_csrf_auth_validation_and_rate_limit(system):
    app, client, _ = system
    assert client.post('/cli-permission/apply', data={'csrf':'bad','username':'x','display_name':'X'}).status_code == 403
    assert submit(client, ' ', 'X').status_code == 400
    assert submit(client, 'a b', 'X').status_code == 400
    assert submit(client, 'x', ' ').status_code == 400
    submit(client)
    item_id = application_id(app)
    assert client.get(f'/cli-permission/admin/applications/{item_id}').status_code == 401
    assert client.post(f'/cli-permission/admin/applications/{item_id}/reject',data={'csrf':'bad','reason':'No'}).status_code == 401
    csrf = login(client)
    assert client.post(f'/cli-permission/admin/applications/{item_id}/reject',data={'csrf':'bad','reason':'No'}).status_code == 403
    with app.state.sessions() as db:
        existing = db.scalar(select(ApplicationAttempt))
        db.add_all([ApplicationAttempt(source=existing.source) for _ in range(10)])
        db.commit()
    assert submit(client, 'another').status_code == 429


def test_list_filter_default_pending_and_no_available_environments(system):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    html = client.get('/cli-permission/admin/applications').text
    assert '权限申请 · 1' in html and 'l00123456' in html
    assert 'l00123456' not in client.get('/cli-permission/admin/applications?status=approved').text
    assert client.get('/cli-permission/admin/applications?status=invalid').status_code == 400
    with app.state.sessions() as db:
        db.get(Environment, 1).enabled = False
        db.commit()
    assert '暂无启用环境' in preview(client, csrf, application_id(app)).text


def test_schema_6_upgrade_is_repeatable(system):
    app, _, _ = system
    with app.state.sessions() as db:
        db.get(SchemaVersion, SCHEMA_VERSION).version = 6
        db.commit()
    AccessApplication.__table__.drop(app.state.engine)
    ApplicationAttempt.__table__.drop(app.state.engine)
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    assert 'access_applications' in inspect(app.state.engine).get_table_names()
    with app.state.sessions() as db:
        assert db.get(SchemaVersion, 7)
        assert db.get(User, 1).username == 'alice'


def test_concurrent_decisions_only_apply_once(system):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from fastapi import HTTPException
    from app.application_review import approve
    from app.models import Admin
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id)
    barrier = Barrier(2)
    def decide():
        with app.state.sessions() as db:
            actor = db.scalar(select(Admin))
            barrier.wait(timeout=5)
            try:
                approve(db, actor, item_id, data['username'], data['display_name'], data['environments'],
                        '', data['snapshot'], False, False, False)
                return 200
            except HTTPException as exc:
                return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: decide(), range(2)))
    assert sorted(results) == [200, 409]
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action == 'applications.approve')) == 1


@pytest.mark.parametrize('selection,expires', [([], ''), (['9999'], ''), (['1'], '2000-01-01T00:00:00')])
def test_invalid_approval_never_creates_person(system, selection, expires):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id)
    data.update(environments=selection, expires_at=expires)
    assert client.post(f'/cli-permission/admin/applications/{item_id}/approve', data=data).status_code == 400
    with app.state.sessions() as db:
        assert db.get(AccessApplication, item_id).status == 'pending'
        assert db.scalar(select(User).where(User.username == 'l00123456')) is None


def test_disabled_person_duplicate_target_and_menu_label(system):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    with app.state.sessions() as db:
        db.get(User, 1).enabled = False
        db.commit()
    assert '该人员已停用' in preview(client, csrf, item_id, 'alice').text
    submit(client, 'l00222222')
    assert '其他待审批申请' in preview(client, csrf, item_id, 'l00222222').text
    html = client.get('/cli-permission/admin/applications').text
    assert '>调用日志</a>' in html and '>CLI 调用日志</a>' not in html
