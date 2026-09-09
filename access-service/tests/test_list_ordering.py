from datetime import datetime, timedelta
import pytest
from sqlalchemy import select, text
from app.models import Admin, Audit, CallLog, Environment, User, SchemaVersion
from app.migrations import migrate, SCHEMA_VERSION
from test_service import system, login


@pytest.mark.parametrize('path,model,fields', [
    ('/admin?tab=users', User, {'username': 'sort-user'}),
    ('/admin?tab=environments', Environment, {'name': 'sort-env', 'display_name': '环境', 'platform_origin': 'https://example.com'}),
    ('/admin/administrators', Admin, {'username': 'sort-admin', 'password_hash': 'unused'}),
    ('/admin?tab=audit', Audit, {'actor': 'sort-audit', 'action': 'login', 'detail': ''}),
    ('/admin/calls', CallLog, {'actor': 'sort-call', 'command': 'ml access status', 'environment': 'prod', 'business_id': '', 'source_ip': '', 'allowed': True, 'reason': 'ALLOWED'}),
])
def test_time_order_before_pagination(system, path, model, fields):
    app, client, _ = system
    login(client)
    base = datetime(2040, 1, 1)
    with app.state.sessions() as db:
        ids = []
        for i in range(12):
            values = fields.copy()
            for key in ('username', 'name'):
                if key in values:
                    values[key] += str(i)
            item = model(**values, created_at=base - timedelta(days=i))
            if hasattr(model, 'updated_at'):
                # ID 和创建时间均与修改时间的顺序相反。
                item.created_at = base + timedelta(days=i)
                item.updated_at = base - timedelta(days=i)
            db.add(item)
            db.flush()
            ids.append(item.id)
        db.commit()
    def rows(page):
        sep = '&' if '?' in path else '?'
        response = client.get('/cli-permission' + path + sep + 'page=' + str(page))
        return response.context['people' if model is User else 'items']
    assert [item.id for item in rows(1)] == ids[:10]
    assert [item.id for item in rows(2)][:2] == ids[10:]
    if hasattr(model, 'updated_at'):
        with app.state.sessions() as db:
            db.get(model, ids[-1]).updated_at = None
            db.commit()
        assert rows(1)[0].id == ids[-1]  # 未知修改时间回退创建时间。


def test_admin_time_migration_and_status_update(system):
    app, client, _ = system
    csrf = login(client)
    with app.state.engine.begin() as connection:
        for name in ('created_at', 'updated_at'):
            connection.execute(text(f'ALTER TABLE admins DROP COLUMN {name}'))
        connection.execute(text('UPDATE schema_versions SET version=5'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        assert db.get(SchemaVersion, SCHEMA_VERSION)
        assert db.get(Admin, 1).updated_at is None
    response = client.post('/cli-permission/admin/administrators', data={'csrf': csrf, 'username': 'new-admin', 'enabled': 'true'})
    assert response.status_code == 201
    with app.state.sessions() as db:
        admin = db.scalar(select(Admin).where(Admin.username == 'new-admin'))
        admin_id, created = admin.id, admin.created_at
        admin.updated_at = datetime(2000, 1, 1)
        db.commit()
    assert client.post(f'/cli-permission/admin/administrators/{admin_id}/status', data={'csrf': csrf, 'enabled': 'false'}).status_code == 200
    with app.state.sessions() as db:
        admin = db.get(Admin, admin_id)
        assert admin.created_at == created and admin.updated_at > datetime(2000, 1, 1)
