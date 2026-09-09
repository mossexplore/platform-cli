import re
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from app.models import Admin, Audit, Base, SchemaVersion, Session, User, database
from app.migrations import migrate
from app.security import password_hash, password_matches
from test_service import system, login

ROOT = '/cli-permission'
MANAGERS = ROOT + '/admin/administrators'


def login_as(client, username, password):
    page = client.get(ROOT + '/login')
    csrf = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    response = client.post(ROOT + '/login', data={'csrf':csrf, 'username':username, 'password':password})
    assert response.status_code == 200, response.text
    return re.search('name="csrf" value="([^"]+)"', response.text)[1]


def create_admin(client, csrf, username='operator'):
    response = client.post(MANAGERS, data={'csrf':csrf, 'username':username, 'enabled':'true', 'role':'super_admin', 'password':'ignored-password'})
    assert response.status_code == 201, response.text
    return response


def test_generated_password_role_and_no_secret_leaks(system):
    app, client, _ = system
    csrf = login(client)
    first = create_admin(client, csrf)
    second = create_admin(client, csrf, 'operator2')
    password = first.json()['password']
    assert len(password) >= 24
    assert password != second.json()['password']
    assert 'no-store' in first.headers['cache-control']
    with app.state.sessions() as db:
        item = db.scalar(select(Admin).where(Admin.username == 'operator'))
        assert item.role == 'admin'
        assert password_matches(password, item.password_hash)
        assert not password_matches('ignored-password', item.password_hash)
        audit = db.scalar(select(Audit).where(Audit.action == 'administrators.create'))
        assert password not in audit.detail and item.password_hash not in audit.detail
        assert 'password' not in audit.detail
    page = client.get(MANAGERS).text
    assert password not in page and '复制账号和密码' in page
    assert 'nav-index' not in page


def test_regular_admin_cannot_manage_admins_but_can_manage_users(system):
    app, client, _ = system
    csrf = login(client)
    password = create_admin(client, csrf).json()['password']
    with TestClient(app) as operator:
        operator_csrf = login_as(operator, 'operator', password)
        page = operator.get(ROOT+'/admin').text
        assert '管理员管理' not in page
        assert operator.get(MANAGERS).status_code == 403
        for path, data in [(MANAGERS, {'username':'forged'}), (MANAGERS+'/1/status', {'enabled':'false'}), (MANAGERS+'/1/reset-password', {})]:
            assert operator.post(path, data={'csrf':operator_csrf, **data}).status_code == 403
        assert operator.post(ROOT+'/admin/users', data={'csrf':operator_csrf, 'username':'ordinary-user', 'enabled':'true'}).status_code == 200
        assert operator.post(ROOT+'/admin/grants', data={'csrf':operator_csrf, 'username':'alice', 'environment':'prod', 'item_id':1}).status_code == 200
    with app.state.sessions() as db:
        assert db.scalar(select(User).where(User.username=='ordinary-user'))
        assert not db.scalar(select(Admin).where(Admin.username=='forged'))


def test_disable_invalidates_sessions_and_enable_requires_new_login(system):
    app, client, _ = system
    csrf = login(client)
    password = create_admin(client, csrf).json()['password']
    with TestClient(app) as operator:
        login_as(operator, 'operator', password)
        response = client.post(MANAGERS+'/2/status', data={'csrf':csrf,'enabled':'false'})
        assert response.status_code == 200
        assert operator.get(ROOT+'/admin', follow_redirects=False).status_code == 303
        with app.state.sessions() as db:
            assert not db.get(Admin,2).enabled
            assert not db.scalars(select(Session).where(Session.admin_id==2)).all()
        assert client.post(MANAGERS+'/2/status', data={'csrf':csrf,'enabled':'true'}).status_code == 200
        assert operator.get(ROOT+'/admin', follow_redirects=False).status_code == 303
        login_as(operator, 'operator', password)


def test_reset_password_invalidates_old_password_and_sessions(system):
    app, client, _ = system
    csrf = login(client)
    password = create_admin(client, csrf).json()['password']
    with TestClient(app) as operator:
        login_as(operator,'operator', password)
        response = client.post(MANAGERS+'/2/reset-password', data={'csrf':csrf})
        assert response.status_code == 201
        replacement = response.json()['password']
        assert replacement != password
        assert operator.get(ROOT+'/admin', follow_redirects=False).status_code == 303
        with app.state.sessions() as db:
            assert password_matches(replacement, db.get(Admin,2).password_hash)
            assert not password_matches(password, db.get(Admin,2).password_hash)
        login_as(operator,'operator', replacement)


def test_super_admin_protection_csrf_and_duplicate(system):
    app, client, _ = system
    assert client.get(MANAGERS,follow_redirects=False).status_code == 303
    csrf = login(client)
    assert client.post(MANAGERS, data={'csrf':'wrong','username':'operator'}).status_code == 403
    assert client.post(MANAGERS+'/1/status', data={'csrf':csrf,'enabled':'false'}).status_code == 400
    assert client.post(MANAGERS+'/1/reset-password', data={'csrf':csrf}).status_code == 400
    assert client.post(MANAGERS, data={'csrf':csrf,'username':'   '}).status_code == 400
    create_admin(client, csrf)
    assert client.post(MANAGERS, data={'csrf':csrf,'username':'operator'}).status_code == 409
    assert client.post(MANAGERS+'/999/status', data={'csrf':csrf,'enabled':'true'}).status_code == 404
    with app.state.sessions() as db:
        assert db.get(Admin,1).enabled
        assert db.get(Admin,1).role == 'super_admin'


def test_role_is_rechecked_for_existing_session(system):
    app, client, _ = system
    csrf = login(client)
    with app.state.sessions() as db:
        db.get(Admin,1).role = 'admin'
        db.commit()
    assert client.get(MANAGERS).status_code == 403
    assert client.post(MANAGERS, data={'csrf':csrf,'username':'forged'}).status_code == 403


def test_v2_migration_preserves_existing_admins_and_defaults_new_accounts(tmp_path):
    engine, sessions = database('sqlite:///'+str(tmp_path/'legacy.db'))
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE admins (id INTEGER PRIMARY KEY, username VARCHAR(128) UNIQUE NOT NULL, password_hash VARCHAR(256) NOT NULL, enabled BOOLEAN NOT NULL)'))
        connection.execute(text("INSERT INTO admins VALUES (1, 'legacy', 'existing-hash', 1), (2, 'disabled', 'another-hash', 0)"))
    Base.metadata.create_all(engine)
    with sessions() as db:
        db.add(SchemaVersion(version=2))
        db.commit()
    migrate(engine, sessions)
    migrate(engine, sessions)
    with sessions() as db:
        assert db.get(SchemaVersion,3)
        assert db.get(Admin,1).role == 'super_admin'
        assert db.get(Admin,1).password_hash == 'existing-hash'
        assert db.get(Admin,2).role == 'super_admin' and not db.get(Admin,2).enabled
        item = Admin(username='new',password_hash='new-hash')
        db.add(item)
        db.commit()
        assert item.role == 'admin'
    engine.dispose()
