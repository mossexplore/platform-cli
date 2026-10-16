"""批量环境查询保留逐环境身份、业务、版本策略和调用记录。"""
import pytest
from datetime import datetime
from sqlalchemy import select
from app.models import CallLog, Environment, Grant, User
from test_service import system
from test_version_policy import policy


def check(environment='prod', username='alice', business='prod-business', origin='https://platform.example.com'):
    return {'username': username, 'environment': environment,
            'platform_origin': origin, 'business_id': business}


def query(client, checks, username='alice'):
    return client.post('/cli-permission/api/v1/access/environments',
        json={'username': username, 'environments': checks},
        headers={'businessid': 'header-must-not-override-items', 'X-CLI-Version': '1.0.7.1'})


def test_batch_preserves_each_identity_business_and_records(system):
    app, client, _ = system
    with app.state.sessions() as db:
        user = User(username='bob')
        env = Environment(name='dev', display_name='开发', platform_origin='https://dev.example.com')
        db.add_all([user, env]); db.flush()
        db.add(Grant(user_id=user.id, environment_id=env.id)); db.commit()
    response = query(client, [check(), check('dev', 'bob', 'dev-business', 'https://dev.example.com')])
    assert response.status_code == 200
    result = response.json()
    assert result['username'] == 'alice' and result['has_access'] is True
    assert [(item['environment'], item['username'], item['business_id'], item['result']['allowed'])
            for item in result['environments']] == [
                ('prod', 'alice', 'prod-business', True), ('dev', 'bob', 'dev-business', True)]
    with app.state.sessions() as db:
        logs = db.scalars(select(CallLog).order_by(CallLog.id)).all()
        assert [(row.actor, row.business_id, row.command) for row in logs] == [
            ('alice', 'prod-business', 'ml env list'), ('bob', 'dev-business', 'ml env list')]


def test_batch_preserves_business_scoped_version_policy(system):
    app, client, _ = system
    policy(app, environment='prod', business_id='prod-business', minimum_version='9.0.0')
    response = query(client, [check()]).json()
    assert response['has_access'] is True
    assert response['environments'][0]['result']['reason'] == 'CLI_VERSION_TOO_OLD'
    with app.state.sessions() as db:
        assert db.scalar(select(CallLog)).allowed is False


def test_call_timestamp_matches_mysql_second_precision(system, monkeypatch):
    app, client, _ = system
    timestamp = datetime(2026, 10, 16, 6, 0, 0, 999999)
    monkeypatch.setattr('app.access.now', lambda: timestamp)
    assert query(client, [check()]).status_code == 200
    with app.state.sessions() as db:
        assert db.scalar(select(CallLog)).created_at == timestamp.replace(microsecond=0)


def test_summary_and_unknown_environment_are_independent(system):
    _, client, _ = system
    response = query(client, [check('unknown')]).json()
    assert response['has_access'] is True
    assert response['environments'][0]['result']['reason'] == 'ENVIRONMENT_DISABLED'
    assert query(client, [], username='unknown').json() == {
        'username': 'unknown', 'has_access': False, 'environments': [], 'authorizations': []}
    response = query(client, [check()], username=None).json()
    assert response['username'] is None and response['has_access'] is None
    assert response['environments'][0]['result']['allowed'] is True


@pytest.mark.parametrize('checks', [[check(), check()], [check()]*101,
    [{**check(), 'business_id': ''}], [{**check(), 'business_id': 'bad\r\nheader'}]])
def test_bad_batches_are_rejected_before_recording(system, checks):
    app, client, _ = system
    assert query(client, checks).status_code == 422
    with app.state.sessions() as db:
        assert db.scalar(select(CallLog)) is None


@pytest.mark.parametrize('disabled', ['grant', 'environment', 'user', 'expired'])
def test_authorizations_only_include_effective_grants(system, disabled):
    app, client, _ = system
    assert query(client, []).json()['authorizations'] == [
        {'environment': 'prod', 'platform_origin': 'https://platform.example.com'}]
    with app.state.sessions() as db:
        if disabled == 'expired':
            db.scalar(select(Grant)).expires_at = datetime(2000, 1, 1)
        else:
            model = {'grant': Grant, 'environment': Environment, 'user': User}[disabled]
            db.scalar(select(model)).enabled = False
        db.commit()
    result = query(client, []).json()
    assert result['has_access'] is False
    assert result['authorizations'] == []
