from sqlalchemy import select
from app.models import Environment, Grant, Audit
from test_service import system, login, check


def add_env(app, name='dev', enabled=True):
    with app.state.sessions() as db:
        db.add(Environment(name=name, display_name=name, platform_origin='https://platform.example.com', enabled=enabled))
        db.commit()


def test_multi_environment_upsert_and_independent_revoke(system):
    app, client, _ = system
    add_env(app)
    csrf = login(client)
    payload = {'csrf': csrf, 'username': 'alice', 'environments': ['prod', 'dev', 'dev'], 'enabled': 'true'}
    assert client.post('/cli-permission/admin/grants/batch', data=payload).status_code == 200
    assert client.post('/cli-permission/admin/grants/batch', data=payload).status_code == 200
    assert check(client, environment='prod').json()['allowed']
    assert check(client, environment='dev').json()['allowed']
    with app.state.sessions() as db:
        assert len(db.scalars(select(Grant)).all()) == 2
        assert len(db.scalars(select(Audit).where(Audit.action == 'grants.batch_save')).all()) == 4
    payload['environments'] = ['dev']
    payload.pop('enabled')
    assert client.post('/cli-permission/admin/grants/batch', data=payload).status_code == 200
    assert check(client, environment='prod').json()['allowed']
    assert check(client, environment='dev').json()['reason'] == 'NOT_GRANTED'


def test_invalid_environment_batch_changes_nothing(system):
    app, client, _ = system
    add_env(app, enabled=False)
    csrf = login(client)
    for names in [['prod', 'missing'], ['prod', 'dev']]:
        assert client.post('/cli-permission/admin/grants/batch', data={'csrf': csrf, 'username': 'alice', 'environments': names}).status_code == 400
        assert check(client).json()['allowed']
    assert client.post('/cli-permission/admin/grants/batch', data={'csrf': csrf, 'username': 'alice'}).status_code == 422
    assert client.post('/cli-permission/admin/grants/batch', data={'csrf': 'bad', 'username': 'alice', 'environments': ['prod']}).status_code == 403
    page = client.get('/cli-permission/admin?tab=grants').text
    assert 'name="environments" value="prod"' in page
    assert 'name="environments" value="dev"' not in page
