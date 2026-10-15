import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import User
from test_service import system, login
from test_analytics import record

PATH = '/cli-permission/admin/analytics'
RANGE = {'begin': '2026-09-10T00:00:00', 'end': '2026-09-10T23:59:59'}


def seed(app):
    with app.state.sessions() as db:
        for i in range(55):
            record(db, actor=f'user-{i:02}', command=f'command-{i:02}', timestamp='2026-09-10T01:00:00')
        db.add(User(username='user-00', display_name='张三', enabled=False))
        db.add(User(username='user-01', display_name=''))
        db.commit()


@pytest.mark.parametrize('limit', [10, 20, 30, 50])
def test_independent_limits_stable_ties_and_chart_unchanged(system, limit):
    app, client, _ = system
    seed(app)
    login(client)
    original = client.get(PATH, params=RANGE)
    response = client.get(PATH, params=dict(RANGE, commands_top=limit, actors_top=20))
    assert response.status_code == 200
    context = response.context
    assert len(context['commands']) == limit and len(context['actors']) == 20
    assert [name for name, _ in context['commands']] == [f'command-{i:02}' for i in range(limit)]
    assert context['chart'] == original.context['chart']
    assert context['total'] == 55 and '>1.8%</td>' in response.text
    response = client.get(PATH, params=dict(RANGE, commands_top=20, actors_top=limit))
    assert len(response.context['actors']) == limit and len(response.context['commands']) == 20
    assert 'form="analytics-filter-form"' in response.text
    assert '<option value="50"' in response.text


def test_names_are_current_missing_names_do_not_remove_logs_and_filters_still_apply(system):
    app, client, _ = system
    seed(app)
    login(client)
    response = client.get(PATH, params=dict(RANGE, actors_top=30, environment='prod', business_id='selected', username='user-0'))
    assert len(response.context['actors']) == 10
    assert response.context['actor_names'] == {'user-00': '张三', 'user-01': ''}
    assert '<th>用户名</th><th>姓名</th>' in response.text
    assert '>张三</td>' in response.text and '>—</td>' in response.text
    with app.state.sessions() as db:
        db.scalar(select(User).where(User.username == 'user-00')).display_name = '新姓名'
        db.commit()
    assert '>新姓名</td>' in client.get(PATH, params=RANGE).text


@pytest.mark.parametrize('params', [{'commands_top': 11}, {'actors_top': 0}, {'actors_top': 100000}, {'commands_top': 'bad'}])
def test_invalid_limits_rejected(system, params):
    _, client, _ = system
    login(client)
    assert client.get(PATH, params=params).status_code in (400, 422)


def test_empty_mysql_sum_none_remains_numeric(system, monkeypatch):
    app, client, _ = system
    login(client)
    session_type = app.state.sessions.class_
    original = session_type.execute
    class EmptyAggregate:
        def one(self):
            return Decimal(0), None, Decimal(0)
    def execute(self, statement, *args, **kwargs):
        sql = str(statement).lower()
        if 'sum(' in sql and 'distinct' in sql:
            return EmptyAggregate()
        return original(self, statement, *args, **kwargs)
    monkeypatch.setattr(session_type, 'execute', execute)
    response = client.get(PATH, params=dict(RANGE, commands_top=50, actors_top=50))
    assert response.status_code == 200
    assert response.context['total'] == response.context['rejected'] == response.context['users'] == 0
    assert type(response.context['total']) is int
    json.dumps(response.context['chart'])
    assert 'colspan="4"' in response.text
