from sqlalchemy import select
from app.models import CallLog, Grant, SchemaVersion, User
from app.manage import migrate
from test_service import system, login, check


def test_records_reported_account_command_and_denial(system):
    app, client, _ = system
    headers = {'x-platform-cookie': 'DO_NOT_LOG_COOKIE', 'x-platform-csrf': 'DO_NOT_LOG_CSRF', 'businessid': 'selected'}
    body = {'environment': 'prod', 'platform_origin': 'https://platform.example.com',
            'command': 'ml train list', 'username': 'alice', 'password': 'DO_NOT_LOG_PASSWORD'}
    assert client.post('/cli-permission/api/v1/access/check', headers=headers, json=body).json()['allowed']
    with app.state.sessions() as db:
        db.get(Grant, 1).enabled = False
        db.commit()
    assert not client.post('/cli-permission/api/v1/access/check', headers=headers, json=body).json()['allowed']
    with app.state.sessions() as db:
        rows = db.scalars(select(CallLog).order_by(CallLog.id)).all()
        assert len(rows) == 2
        assert rows[0].actor == rows[1].actor == 'alice'
        assert rows[0].command == 'ml train list'
        assert rows[0].business_id == 'selected'
        assert rows[0].allowed and not rows[1].allowed
        assert rows[1].reason == 'NOT_GRANTED'
        values = str([vars(row) for row in rows])
        assert 'DO_NOT_LOG' not in values and 'forged' not in values


def test_unknown_reported_account_recorded(system):
    app, client, _ = system
    assert check(client, username='unknown').json()['reason'] == 'USER_DISABLED'
    with app.state.sessions() as db:
        row = db.scalar(select(CallLog))
        assert row.actor == 'unknown'
        assert row.command == 'unknown'
        assert row.reason == 'USER_DISABLED'


def test_log_query_requires_admin_and_filters_with_pagination(system):
    app, client, _ = system
    assert client.get('/cli-permission/admin/calls', follow_redirects=False).status_code == 303
    for _ in range(21):
        check(client)
    login(client)
    page = client.get('/cli-permission/admin/calls?username=alice&environment=prod&result=allowed')
    assert page.status_code == 200 and '21 条' in page.text and '下一页' in page.text
    assert '未验证' not in page.text.split('<tbody>')[1].split('</tbody>')[0]
    assert '暂无匹配记录' in client.get('/cli-permission/admin/calls?result=denied').text
    assert '暂无匹配记录' in client.get('/cli-permission/admin/calls?command=unmatched').text
    assert '暂无匹配记录' in client.get('/cli-permission/admin/calls?begin=2099-01-01T00:00').text
    assert client.get('/cli-permission/admin/calls?begin=2030-01-01&end=2020-01-01').status_code == 400
    assert '上一页' in client.get('/cli-permission/admin/calls?page=2').text


def test_v1_migration_preserves_users_and_creates_logs(system):
    app, client, _ = system
    CallLog.__table__.drop(app.state.engine)
    with app.state.sessions() as db:
        db.get(SchemaVersion, 6).version = 1
        db.commit()
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        assert db.get(SchemaVersion, 6)
        assert db.get(User, 1).username == 'alice'
        assert db.scalars(select(CallLog)).all() == []
    assert client.get('/cli-permission/healthz').json()['status'] == 'ok'


def test_log_write_failure_does_not_allow_access(system):
    app, client, _ = system
    CallLog.__table__.drop(app.state.engine)
    response = check(client)
    assert response.status_code == 503
    assert 'allowed' not in response.json()


def test_full_command_is_stored_and_escaped(system):
    app, client, _ = system
    command = 'ml train start "任务 <script>alert(1)</script>" --config "a b.json"'
    assert check(client, command='ml train start', full_command=command).json()['allowed']
    with app.state.sessions() as db:
        assert db.scalar(select(CallLog)).full_command == command
    login(client)
    html = client.get('/cli-permission/admin/calls').text
    assert '<th>完整命令</th>' in html
    assert '&lt;script&gt;' in html and '<script>alert(1)</script>' not in html
    assert check(client, full_command='x' * 8193).status_code == 422


def test_v3_migration_preserves_old_logs(system):
    from sqlalchemy import text
    app, client, _ = system
    check(client)
    with app.state.engine.begin() as connection:
        connection.execute(text('ALTER TABLE cli_call_logs DROP COLUMN full_command'))
        connection.execute(text('UPDATE schema_versions SET version=3'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        old = db.scalar(select(CallLog))
        assert old.actor == 'alice' and old.full_command is None
        assert db.get(SchemaVersion, 6)
    login(client)
    assert '未上报（旧客户端或历史记录）' in client.get('/cli-permission/admin/calls').text
