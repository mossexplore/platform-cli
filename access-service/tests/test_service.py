import re
from datetime import timedelta
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import create_app
from app.manage import migrate
from app.models import Admin, Audit, Environment, Grant, User, now
from app.security import password_hash, expiry, display_time
from app.settings import Settings


@pytest.fixture
def system(tmp_path):
    captured = []
    def identity(request):
        captured.append(request)
        return httpx.Response(200, json={'result': {'code': 0, 'username': 'alice'}})
    app = create_app(Settings('sqlite:///' + str(tmp_path / 'test.db'), secure_cookie=False),
                     httpx.MockTransport(identity))
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        db.add(Admin(username='admin', password_hash=password_hash('password-123456')))
        user = User(username='alice', display_name='Alice')
        env = Environment(name='prod', display_name='生产', platform_origin='https://platform.example.com')
        db.add_all([user, env])
        db.flush()
        db.add(Grant(user_id=user.id, environment_id=env.id))
        db.commit()
    with TestClient(app) as client:
        yield app, client, captured
    app.state.engine.dispose()


def check(client, **overrides):
    body = {'environment': 'prod', 'platform_origin': 'https://platform.example.com'}
    body.update(overrides)
    return client.post('/api/v1/access/check', json=body,
                       headers={'x-platform-cookie': 'secret-cookie', 'x-platform-csrf': 'secret-csrf', 'businessid': 'selected'})


def login(client):
    page = client.get('/login')
    csrf = re.search('name="csrf" value="([^"]+)"', page.text)[1]
    result = client.post('/login', data={'username': 'admin', 'password': 'password-123456', 'csrf': csrf})
    assert result.status_code == 200
    assert 'CLI 权限管理' in result.text
    return re.search('name="csrf" value="([^"]+)"', result.text)[1]


def test_live_identity_headers_and_spoofed_username(system):
    app, client, requests = system
    response = check(client, username='admin')
    assert response.json() == {'allowed': True, 'username': 'alice', 'environment': 'prod'}
    assert str(requests[0].url) == 'https://platform.example.com/ai/user/info'
    assert requests[0].headers['businessid'] == 'selected'
    assert requests[0].headers['cookie'] == 'secret-cookie'
    with app.state.sessions() as db:
        assert not db.scalars(select(Audit)).all()


@pytest.mark.parametrize('model,field,value,reason', [
    (User, 'enabled', False, 'USER_DISABLED'),
    (Grant, 'enabled', False, 'NOT_GRANTED'),
    (Grant, 'expires_at', now() - timedelta(seconds=1), 'GRANT_EXPIRED'),
    (Environment, 'enabled', False, 'ENVIRONMENT_DISABLED'),
])
def test_revocation_immediate(system, model, field, value, reason):
    app, client, _ = system
    assert check(client).json()['allowed'] is True
    with app.state.sessions() as db:
        setattr(db.scalar(select(model)), field, value)
        db.commit()
    response = check(client).json()
    assert response['allowed'] is False
    assert response['reason'] == reason


def test_unknown_account_and_environment(system):
    app, client, requests = system
    assert check(client, environment='unknown').json()['allowed'] is False
    assert check(client, platform_origin='https://evil.example.com').json()['reason'] == 'ENVIRONMENT_MISMATCH'
    assert not requests
    app.state.identity_transport = httpx.MockTransport(lambda req: httpx.Response(200, json={'result': {'code': 0, 'username': 'mallory'}}))
    assert check(client).json()['reason'] == 'USER_DISABLED'


@pytest.mark.parametrize('status,payload,expected', [(401, {}, 401), (302, {}, 401), (500, {}, 503),
    (200, {'result': {'code': 1}}, 401), (200, {'result': {'code': 0}}, 503), (200, [], 503)])
def test_bad_identity_fails_closed(system, status, payload, expected):
    app, client, _ = system
    app.state.identity_transport = httpx.MockTransport(lambda req: httpx.Response(status, json=payload))
    assert check(client).status_code == expected


def test_identity_network_error_sanitized(system):
    app, client, _ = system
    def fail(req):
        raise httpx.ConnectError('secret-cookie')
    app.state.identity_transport = httpx.MockTransport(fail)
    response = check(client)
    assert response.status_code == 503
    assert 'secret-cookie' not in response.text


def test_admin_requires_login_and_csrf(system):
    app, client, _ = system
    assert client.get('/admin', follow_redirects=False).status_code == 303
    assert client.post('/admin/users', data={'username': 'bob', 'csrf': 'x'}).status_code == 401
    csrf = login(client)
    assert client.post('/admin/users', data={'username': 'bob', 'csrf': 'wrong'}).status_code == 403
    assert client.post('/admin/users', data={'username': 'bob', 'csrf': csrf, 'enabled': 'true'}).status_code == 200
    with app.state.sessions() as db:
        assert db.scalar(select(User).where(User.username == 'bob')).enabled
        audit = db.scalars(select(Audit).where(Audit.action == 'users.save')).one()
        assert 'bob' in audit.detail
        assert 'password' not in audit.detail
    assert client.post('/admin/users', data={'username': 'bob', 'csrf': csrf}).status_code == 409
    assert client.post('/logout', data={'csrf': csrf}, follow_redirects=False).status_code == 303
    assert client.get('/admin', follow_redirects=False).status_code == 303


def test_admin_grant_form_timezone_and_revoke(system):
    app, client, _ = system
    csrf = login(client)
    result = client.post('/admin/grants', data={'csrf': csrf, 'item_id': 1, 'username': 'alice',
        'environment': 'prod', 'expires_at': '2030-09-08T14:54', 'note': 'test', 'enabled': 'true'})
    assert result.status_code == 200
    with app.state.sessions() as db:
        item = db.get(Grant, 1)
        assert item.expires_at.isoformat() == '2030-09-08T06:54:00'
    assert '2030-09-08T14:54' in result.text
    result = client.post('/admin/grants', data={'csrf': csrf, 'item_id': 1, 'username': 'alice', 'environment': 'prod'})
    assert result.status_code == 200
    assert check(client).json()['reason'] == 'NOT_GRANTED'


def test_environment_form_and_disabled_admin(system):
    app, client, _ = system
    csrf = login(client)
    for origin in ['ftp://example.com', 'https://u:p@example.com', 'https://example.com/path']:
        assert client.post('/admin/environments', data={'csrf': csrf, 'name': 'dev', 'display_name': '开发', 'platform_origin': origin}).status_code == 400
    assert client.post('/admin/environments', data={'csrf': csrf, 'name': 'dev', 'display_name': '开发', 'platform_origin': 'https://dev.example.com', 'enabled': 'true'}).status_code == 200
    with app.state.sessions() as db:
        db.get(Admin, 1).enabled = False
        db.commit()
    assert client.post('/admin/users', data={'csrf': csrf, 'username': 'bob'}).status_code == 401


def test_login_rate_limit(system):
    _, client, _ = system
    csrf = re.search('name="csrf" value="([^"]+)"', client.get('/login').text)[1]
    for _ in range(10):
        assert client.post('/login', data={'csrf': csrf, 'username': 'nobody', 'password': 'bad'}).status_code == 401
    assert client.post('/login', data={'csrf': csrf, 'username': 'admin', 'password': 'password-123456'}).status_code == 429


def test_health_migration_and_html_escaping(system):
    app, client, _ = system
    migrate(app.state.engine, app.state.sessions)
    assert client.get('/healthz').json()['status'] == 'ok'
    csrf = login(client)
    client.post('/admin/users', data={'csrf': csrf, 'username': '<script>alert(1)</script>'})
    response = client.get('/admin')
    assert '<script>alert(1)</script>' not in response.text
    assert '&lt;script&gt;' in response.text
    for tab in ['users', 'environments', 'grants', 'audit']:
        assert client.get('/admin', params={'tab': tab}).status_code == 200
    assert "frame-ancestors 'none'" in response.headers['content-security-policy']
    assert display_time(expiry('2026-09-08T14:54:36')) == '2026-09-08 14:54:36'


@pytest.mark.parametrize('scheme', ['http', 'https'])
def test_environment_origin_preserves_scheme_through_identity_check(system, scheme):
    app, client, captured = system
    csrf = login(client)
    platform = scheme + '://platform.example.com:8080'
    result = client.post('/admin/environments', data={'csrf': csrf, 'item_id': 1,
        'name': 'prod', 'display_name': '生产', 'platform_origin': platform + '/', 'enabled': 'true'})
    assert result.status_code == 200
    assert check(client, platform_origin=platform).json()['allowed']
    assert str(captured[-1].url) == platform + '/ai/user/info'
    assert captured[-1].headers['businessid'] == 'selected'
    opposite = ('https' if scheme == 'http' else 'http') + '://platform.example.com:8080'
    assert check(client, platform_origin=opposite).json()['reason'] == 'ENVIRONMENT_MISMATCH'
