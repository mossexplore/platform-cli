"""用户授权查询必须覆盖全部环境，仅有效授权返回 JSON true。"""
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import create_app
from app.manage import migrate
from app.models import Environment, Grant, User, now
from app.settings import Settings


@pytest.fixture
def system(tmp_path):
    app = create_app(Settings('sqlite:///' + str(tmp_path / 'summary.db'), secure_cookie=False))
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        user = User(username='alice')
        env = Environment(name='other', display_name='其他环境', platform_origin='https://other.example.com')
        db.add_all([user, env])
        db.flush()
        db.add(Grant(user_id=user.id, environment_id=env.id))
        db.commit()
    with TestClient(app) as client:
        yield app, client
    app.state.engine.dispose()


def query(client, username='alice'):
    return client.post('/cli-permission/api/v1/access/summary', json={'username': username})


def test_any_environment_counts_without_business_or_current_environment(system):
    _, client = system
    response = query(client)
    assert response.status_code == 200
    assert response.json() == {'username': 'alice', 'has_access': True}
    assert query(client, 'unknown').json()['has_access'] is False
    assert query(client, 'ALICE').json()['has_access'] is False


@pytest.mark.parametrize('model,field,value', [
    (User, 'enabled', False), (Environment, 'enabled', False),
    (Grant, 'enabled', False), (Grant, 'expires_at', now() - timedelta(seconds=1)),
])
def test_inactive_or_expired_grants_do_not_count(system, model, field, value):
    app, client = system
    with app.state.sessions() as db:
        setattr(db.scalar(select(model)), field, value)
        db.commit()
    assert query(client).json()['has_access'] is False


def test_no_grant_and_future_expiry(system):
    app, client = system
    with app.state.sessions() as db:
        grant = db.scalar(select(Grant))
        grant.expires_at = now() + timedelta(days=1)
        db.commit()
    assert query(client).json()['has_access'] is True
    with app.state.sessions() as db:
        db.delete(db.scalar(select(Grant)))
        db.commit()
    assert query(client).json()['has_access'] is False


@pytest.mark.parametrize('username', [None, '', '   ', 123, 'a' * 129])
def test_invalid_identity_rejected(system, username):
    _, client = system
    assert query(client, username).status_code == 422


def test_valid_grant_in_another_environment_overrides_expired_one(system):
    app, client = system
    with app.state.sessions() as db:
        db.scalar(select(Grant)).expires_at = now() - timedelta(days=1)
        env = Environment(name='second', display_name='第二环境', platform_origin='https://second.example.com')
        db.add(env)
        db.flush()
        db.add(Grant(user_id=db.scalar(select(User.id)), environment_id=env.id))
        db.commit()
    assert query(client).json()['has_access'] is True
