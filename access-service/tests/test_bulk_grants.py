import json
from datetime import timedelta

import pytest
from sqlalchemy import select, event
from sqlalchemy.exc import SQLAlchemyError

from app.models import User, Environment, Grant, Audit, now
from app.security import display_time
from test_service import system, login

BASE = '/cli-permission/admin/grants/bulk/'


def body(csrf, **edit):
    return {'csrf': csrf, 'user_ids': [1, 2], 'edits': [{'environment_id': 1, **edit}]}


def add_person(app, enabled=True):
    with app.state.sessions() as db:
        db.add(User(username='bob', display_name='Bob', enabled=enabled))
        db.commit()


def save_preview(client, data):
    result = client.post(BASE + 'preview', json=data)
    assert result.status_code == 200, result.text
    data['token'] = result.json()['token']
    return client.post(BASE + 'save', json=data)


def test_open_multiple_people_preserves_details_and_audits(system):
    app, client, _ = system
    add_person(app, enabled=False)
    with app.state.sessions() as db:
        grant = db.get(Grant, 1)
        grant.note = 'original'
        grant.expires_at = now() - timedelta(days=1)
        old_expiry = grant.expires_at
        db.add(Environment(name='other', display_name='其他', platform_origin='https://example.com'))
        db.commit()
    data = body(login(client), operation='enable')
    preview = client.post(BASE + 'preview', json=data).json()
    assert preview['counts'] == {'created': 1, 'updated': 0, 'revoked': 0, 'unchanged': 1}
    assert any('bob 已停用' in warning for warning in preview['warnings'])
    with app.state.sessions() as db:
        assert len(db.scalars(select(Grant)).all()) == 1  # Preview cannot save.
    assert save_preview(client, data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Grant, 1).expires_at == old_expiry
        assert db.get(Grant, 1).note == 'original'
        bob = db.get(User, 2)
        assert not bob.enabled and bob.updated_by == 'admin'
        grant = db.scalar(select(Grant).where(Grant.user_id == 2))
        assert grant.enabled and grant.expires_at is None and grant.note == ''
        audits = db.scalars(select(Audit).where(Audit.action == 'grants.bulk_save')).all()
        assert len(audits) == 1
        assert json.loads(audits[0].detail)['batch_id']
    audit_html = client.get('/cli-permission/admin?tab=audit').text
    assert '多人批量编辑授权' in audit_html and 'bob · prod · 批次' in audit_html


def test_expiry_only_does_not_create_or_enable_and_beijing_is_converted(system):
    app, client, _ = system
    add_person(app)
    with app.state.sessions() as db:
        db.get(Grant, 1).enabled = False
        db.commit()
    data = body(login(client), expiry_mode='set', expires_at='2035-09-08T14:54:36', note_mode='set', note='renew')
    assert save_preview(client, data).status_code == 200
    with app.state.sessions() as db:
        grant = db.get(Grant, 1)
        assert not grant.enabled and grant.note == 'renew'
        assert grant.expires_at.isoformat() == '2035-09-08T06:54:36'
        assert display_time(grant.expires_at) == '2035-09-08 14:54:36'
        assert db.scalar(select(Grant).where(Grant.user_id == 2)) is None


def test_enable_expired_warns_and_revoke_preserves_details(system):
    app, client, _ = system
    add_person(app)
    with app.state.sessions() as db:
        grant = db.get(Grant, 1)
        grant.enabled, grant.expires_at, grant.note = False, now() - timedelta(days=1), 'keep'
        db.commit()
    csrf = login(client)
    data = body(csrf, operation='enable')
    result = client.post(BASE + 'preview', json=data).json()
    assert any('仍已过期' in message for message in result['warnings'])
    assert save_preview(client, data).status_code == 200
    data = body(csrf, operation='revoke')
    result = client.post(BASE + 'preview', json=data).json()
    assert result['counts']['revoked'] == 2
    assert save_preview(client, data).status_code == 200
    with app.state.sessions() as db:
        assert not db.get(Grant, 1).enabled and db.get(Grant, 1).note == 'keep'


@pytest.mark.parametrize('changed', ['grant', 'user', 'environment', 'new_grant', 'payload', 'signature', 'expired'])
def test_stale_or_tampered_preview_cannot_save(system, changed, monkeypatch):
    app, client, _ = system
    add_person(app)
    data = body(login(client), operation='enable', note_mode='set', note='new')
    data['token'] = client.post(BASE + 'preview', json=data).json()['token']
    with app.state.sessions() as db:
        if changed == 'grant': db.get(Grant, 1).note = 'concurrent'
        if changed == 'user': db.get(User, 2).enabled = False
        if changed == 'environment': db.get(Environment, 1).enabled = False
        if changed == 'new_grant': db.add(Grant(user_id=2, environment_id=1))
        db.commit()
    if changed == 'payload': data['edits'][0]['note'] = 'tampered'
    if changed == 'signature': data['token'] += 'bad'
    if changed == 'expired':
        import time
        monkeypatch.setattr('app.bulk_grants.time.time', lambda: int(data['token'].split('.')[0]) + 901)
    result = client.post(BASE + 'save', json=data)
    assert result.status_code == 409
    with app.state.sessions() as db:
        assert not db.scalars(select(Audit).where(Audit.action == 'grants.bulk_save')).all()
        assert db.get(Grant, 1).note != 'new'


def test_validation_auth_and_noop(system):
    app, client, _ = system
    add_person(app)
    assert client.post(BASE + 'preview', json=body('bad')).status_code == 401
    csrf = login(client)
    assert client.post(BASE + 'preview', json=body('bad')).status_code == 403
    for edit in [{'environment_id': 999}, {'expiry_mode': 'set', 'expires_at': ''},
                 {'expiry_mode': 'set', 'expires_at': '2000-01-01T00:00:00'}]:
        assert client.post(BASE + 'preview', json=body(csrf, **edit)).status_code in (400, 409)
    assert client.post(BASE + 'preview', json=body(csrf, operation='revoke', note_mode='clear')).status_code == 422
    data = body(csrf)
    assert save_preview(client, data).status_code == 400
    data['user_ids'] = [1, 1]
    assert client.post(BASE + 'preview', json=data).status_code == 400
    data['user_ids'] = list(range(1, 102))
    assert client.post(BASE + 'preview', json=data).status_code == 422
    data['user_ids'] = list(range(1, 101))
    data['edits'] = [{'environment_id': i} for i in range(1, 22)]
    assert client.post(BASE + 'preview', json=data).status_code == 400


def test_whole_batch_rolls_back_when_audit_write_fails(system):
    app, client, _ = system
    add_person(app)
    data = body(login(client), operation='enable', note_mode='set', note='new')
    data['token'] = client.post(BASE + 'preview', json=data).json()['token']
    def fail_audit(mapper, connection, target):
        if target.action == 'grants.bulk_save': raise SQLAlchemyError('simulated failure')
    event.listen(Audit, 'before_insert', fail_audit)
    try:
        assert client.post(BASE + 'save', json=data).status_code == 503
    finally:
        event.remove(Audit, 'before_insert', fail_audit)
    with app.state.sessions() as db:
        assert db.get(Grant, 1).note == ''
        assert db.scalar(select(Grant).where(Grant.user_id == 2)) is None


def test_labels_and_controls_render_without_changing_public_application(system):
    _, client, _ = system
    login(client)
    html = client.get('/cli-permission/admin?tab=users').text
    assert 'id="bulk-grants"' in html and 'bulk-grants.js' in html
    assert 'data-bulk-env="1"' in html
    html = client.get('/cli-permission/admin/applications').text
    assert '<h1>权限审批</h1>' in html and '<strong>权限审批</strong>' in html
    assert '<title>权限审批' in html and '>权限审批' in html
    assert '权限申请' in client.get('/cli-permission/apply').text
