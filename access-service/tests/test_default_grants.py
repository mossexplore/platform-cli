"""默认开通只控制审批预选，迁移和配置变更不得自动授权。"""
import json
import re

from sqlalchemy import inspect, select, text

from app.models import AccessApplication, Audit, Environment, Grant, SchemaVersion
from app.migrations import SCHEMA_VERSION, migrate
from test_service import system, login
from test_applications import submit, application_id, approval, preview


def choices(html):
    return re.findall(r'<input type="checkbox" name="environments"[^>]+>', html)


def test_environment_create_edit_and_audit(system):
    app, client, _ = system
    csrf = login(client)
    data = {'csrf': csrf, 'name': 'dev', 'display_name': '开发',
            'platform_origin': 'https://dev.example.com', 'enabled': 'true'}
    assert client.post('/cli-permission/admin/environments', data=data).status_code == 200
    with app.state.sessions() as db:
        env = db.scalar(select(Environment).where(Environment.name == 'dev'))
        assert env.default_grant is False
        data['item_id'] = env.id
    data['default_grant'] = 'true'
    assert client.post('/cli-permission/admin/environments', data=data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Environment, data['item_id']).default_grant is True
        audit = db.scalar(select(Audit).where(Audit.action == 'environments.save').order_by(Audit.id.desc()))
        assert json.loads(audit.detail)['after']['default_grant'] == 'True'
    page = client.get('/cli-permission/admin?tab=environments').text
    assert '<th>默认开通</th>' in page
    assert 'name="default_grant" value="true" checked' in page
    data.pop('default_grant')
    assert client.post('/cli-permission/admin/environments', data=data).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Environment, data['item_id']).default_grant is False


def test_preview_selects_only_enabled_default_environments(system):
    app, client, _ = system
    with app.state.sessions() as db:
        db.add_all([
            Environment(name='default', display_name='默认环境', platform_origin='https://default.example.com', default_grant=True),
            Environment(name='disabled', display_name='停用', platform_origin='https://disabled.example.com', enabled=False, default_grant=True)])
        db.commit()
        selected_id = db.scalar(select(Environment.id).where(Environment.name == 'default'))
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    page = preview(client, csrf, item_id).text
    assert page.count('src="/cli-permission/static/approval-environments.js"') == 1
    assert '<script' not in re.search(r'<title>(.*?)</title>', page, re.S)[1]
    inputs = choices(page)
    assert len(inputs) == 2
    assert [re.search(r'value="(\d+)"', c)[1] for c in inputs if 'checked' in c] == [str(selected_id)]
    assert '默认全选' not in page and '默认开通</small>' in page
    assert '选择默认环境' in page and '清空' in page
    data = approval(client, csrf, item_id, environments=[str(selected_id)])
    assert client.post(f'/cli-permission/admin/applications/{item_id}/approve', data=data).status_code == 200
    with app.state.sessions() as db:
        user_grants = db.scalars(select(Grant).where(Grant.environment_id == selected_id)).all()
        assert len(user_grants) == 1


def test_no_defaults_requires_manual_selection(system):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    html = preview(client, csrf, item_id).text
    assert all('checked' not in c for c in choices(html))
    assert '尚未设置默认开通环境' in html
    data = approval(client, csrf, item_id, environments=[])
    response = client.post(f'/cli-permission/admin/applications/{item_id}/approve', data=data)
    assert response.status_code == 400
    with app.state.sessions() as db:
        assert db.get(AccessApplication, item_id).status == 'pending'


def test_default_change_invalidates_approval_snapshot(system):
    app, client, _ = system
    submit(client)
    csrf = login(client)
    item_id = application_id(app)
    data = approval(client, csrf, item_id)
    with app.state.sessions() as db:
        db.scalar(select(Environment)).default_grant = True
        db.commit()
    response = client.post(f'/cli-permission/admin/applications/{item_id}/approve', data=data)
    assert response.status_code == 409
    assert '重新核对' in response.text
    with app.state.sessions() as db:
        assert db.get(AccessApplication, item_id).status == 'pending'
        assert db.scalar(select(Grant).where(Grant.environment_id == 1)) is not None


def test_schema10_upgrade_initializes_false_and_is_repeatable(system):
    app, client, _ = system
    with app.state.engine.begin() as connection:
        connection.execute(text('ALTER TABLE environments DROP COLUMN default_grant'))
        connection.execute(text('UPDATE schema_versions SET version=10'))
    assert client.get('/cli-permission/healthz').status_code == 503
    migrate(app.state.engine, app.state.sessions)
    # Simulate interrupted DDL: column exists but schema version is still old.
    with app.state.engine.begin() as connection:
        connection.execute(text('UPDATE schema_versions SET version=10'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        assert db.get(SchemaVersion, SCHEMA_VERSION)
        assert db.scalar(select(Environment)).default_grant is False
        assert db.scalar(select(Grant)) is not None
    assert client.get('/cli-permission/healthz').status_code == 200
    assert 'default_grant' in {c['name'] for c in inspect(app.state.engine).get_columns('environments')}
