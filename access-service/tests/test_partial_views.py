"""局部响应只返回目标表数据，权限验证、筛选和数值类型保持一致。"""
from decimal import Decimal
import re
from sqlalchemy import select
from app.models import User, Grant
from test_service import system, login
from test_analytics_rankings import seed, RANGE, PATH


def test_people_fragment_has_rows_pager_and_working_dialog_forms(system):
    app, client, _ = system
    with app.state.sessions() as db:
        for i in range(15):
            user = User(username=f'partial-{i:02}', display_name='姓名')
            db.add(user); db.flush()
            db.add(Grant(user_id=user.id, environment_id=1))
        db.commit()
    login(client)
    full = client.get('/cli-permission/admin?tab=users&page=2&q=partial')
    part = client.get('/cli-permission/admin?tab=users&page=2&q=partial', headers={'X-Fragment': 'people'})
    assert part.status_code == 200
    assert '<html' not in part.text and '<thead' not in part.text
    assert 'data-people-pager' in part.text and 'data-people-dialogs' in part.text
    assert re.findall(r'<tr data-account="([^"]+)"', part.text) == re.findall(r'<tr data-account="([^"]+)"', full.text)
    assert 'data-editor' in part.text and 'data-delete' in part.text
    assert 'page=1' in part.text and 'q=partial' in part.text
    assert 'data-analysis-chart' not in part.text


def test_partial_endpoints_still_require_admin_login(system):
    _, client, _ = system
    for path, fragment in [('/cli-permission/admin?tab=users', 'people'), (PATH, 'ranking-commands')]:
        response = client.get(path, headers={'X-Fragment': fragment}, follow_redirects=False)
        assert response.status_code == 303 and response.headers['location'].endswith('/login')


def test_ranking_fragment_avoids_other_tables_and_chart_queries(system, monkeypatch):
    app, client, _ = system
    seed(app); login(client)
    def unexpected(*args, **kwargs):
        raise AssertionError('Ranking-only requests must not rebuild charts')
    monkeypatch.setattr('app.analytics.trend_rows', unexpected)
    for kind, count in [('commands',20), ('actors',30)]:
        response = client.get(PATH, params=dict(RANGE, commands_top=20, actors_top=30),
                              headers={'X-Fragment': 'ranking-'+kind})
        assert response.status_code == 200
        assert response.context['total'] == 55 and type(response.context['total']) is int
        assert len(response.context[kind]) == count
        assert '<html' not in response.text and '<thead' not in response.text
        assert 'data-analysis-chart' not in response.text and 'data-ranking-rows' in response.text
        assert ('>张三</td>' in response.text) is (kind == 'actors')


def test_ranking_fragment_normalizes_mysql_decimal(system, monkeypatch):
    app, client, _ = system
    seed(app); login(client)
    session_type = app.state.sessions.class_
    scalar, execute = session_type.scalar, session_type.execute
    def mysql_scalar(self, statement, *args, **kwargs):
        if 'count(' in str(statement).lower(): return Decimal(55)
        return scalar(self, statement, *args, **kwargs)
    def mysql_execute(self, statement, *args, **kwargs):
        if 'group by' in str(statement).lower() and 'cli_call_logs.command' in str(statement):
            class Rows:
                def all(self): return [('ml example', Decimal(5))]
            return Rows()
        return execute(self, statement, *args, **kwargs)
    monkeypatch.setattr(session_type, 'scalar', mysql_scalar)
    monkeypatch.setattr(session_type, 'execute', mysql_execute)
    response = client.get(PATH, params=RANGE, headers={'X-Fragment':'ranking-commands'})
    assert response.status_code == 200
    assert type(response.context['total']) is int
    assert type(response.context['commands'][0][1]) is int
    assert '>5</td>' in response.text
