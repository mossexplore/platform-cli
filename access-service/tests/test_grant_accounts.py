from sqlalchemy import select
from app.models import User, Environment, Grant
from test_service import system, login


def test_account_pagination_keeps_all_environments_together(system):
    app, client, _ = system
    with app.state.sessions() as db:
        alice = db.scalar(select(User).where(User.username == 'alice'))
        for i in range(22):
            env = Environment(name=f'env-{i:02}', display_name=f'环境 {i}', platform_origin='https://example.com')
            db.add(env)
            db.flush()
            db.add(Grant(user_id=alice.id, environment_id=env.id, enabled=i != 0))
        db.commit()
    login(client)
    response = client.get('/cli-permission/admin?tab=grants')
    assert response.status_code == 200
    assert response.text.count('data-account="alice"') == 1
    assert '23 个环境' in response.text
    assert '共 1 人 · 每页 10 人' in response.text
    assert response.text.count('aria-label="编辑 alice 的 ') == 23
    filtered = client.get('/cli-permission/admin?tab=grants&q=env-00&status=disabled').text
    assert 'data-account="alice"' in filtered
    assert '23 个环境' in filtered
    assert '全部环境授权' in filtered
    assert 'data-account=' not in client.get('/cli-permission/admin?tab=grants&page=2').text


def test_account_pages_do_not_repeat_users(system):
    app, client, _ = system
    with app.state.sessions() as db:
        env = db.scalar(select(Environment))
        for i in range(20):
            user = User(username=f'account-{i:02}')
            db.add(user)
            db.flush()
            db.add(Grant(user_id=user.id, environment_id=env.id))
        db.commit()
    login(client)
    first = client.get('/cli-permission/admin?tab=grants').text
    second = client.get('/cli-permission/admin?tab=grants&page=3').text
    assert first.count('data-account=') == 10
    assert 'data-account="alice"' not in first
    assert second.count('data-account=') == 1
    assert 'data-account="alice"' in second
    assert '共 21 人' in first
