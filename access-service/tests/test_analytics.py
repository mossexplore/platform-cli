from datetime import datetime
from decimal import Decimal
from html import unescape
import json
import re
from urllib.parse import parse_qs, urlsplit
from app.models import CallLog
from test_service import system, login


def record(db, *, actor, command, timestamp, allowed=True, reason='ALLOWED', environment='prod',
           business_id='selected', cli_version='1.0.0'):
    db.add(CallLog(actor=actor, command=command, environment=environment,
        business_id=business_id, source_ip='127.0.0.1', allowed=allowed,
        reason=reason, created_at=datetime.fromisoformat(timestamp), cli_version=cli_version))


def test_dashboard_requires_admin_and_aggregates_beijing_days(system):
    app, client, _ = system
    assert client.get('/cli-permission/admin/analytics', follow_redirects=False).status_code == 303
    with app.state.sessions() as db:
        record(db, actor='alice', command='ml train list', timestamp='2026-09-09T15:59:59')
        record(db, actor='alice', command='ml train list', timestamp='2026-09-09T16:00:00',
               allowed=False, reason='NOT_GRANTED')
        record(db, actor='bob', command='ml train start', timestamp='2026-09-09T16:15:00')
        record(db, actor='carol', command='ml train list', timestamp='2026-09-10T16:00:00')
        db.commit()
    login(client)
    response = client.get('/cli-permission/admin/analytics', params={
        'grain': 'day', 'begin': '2026-09-10T00:00:00', 'end': '2026-09-10T23:59:59'})
    assert response.status_code == 200
    cards = re.findall(r'<strong(?: class="analytics-danger")?>(\d+)<small>(次|人)</small></strong>', response.text)
    assert cards == [('2', '次'), ('1', '次'), ('1', '次'), ('2', '人')]
    assert '拒绝率 50.0%' in response.text
    assert 'ml train start' in response.text and 'ml train list' in response.text
    assert all(name not in response.text for name in ('拒绝较多的环境', '拒绝较多的命令', '拒绝原因'))
    assert 'id="analytics-advanced-filters" class="analytics-filter-advanced" hidden' in response.text
    assert 'data-toggle-analytics-filters' in response.text
    assert '数据分析' in response.text
    assert all(name in response.text for name in (
        '命令分布', '调用趋势', '调用次数分布', '调用次数排行', '版本分布', '调用环境情况'))
    assert response.text.count('<tr><td>09-10</td>') == 1
    assert '"label": "09-10"' in response.text


def test_dashboard_filters_and_drilldown_exactly_match_records(system):
    app, client, _ = system
    with app.state.sessions() as db:
        record(db, actor='ali', command='ml train list', timestamp='2026-09-09T11:00:00')
        record(db, actor='alice', command='ml train list', timestamp='2026-09-09T11:00:00',
               allowed=False, reason='NOT_GRANTED')
        record(db, actor='alice', command='ml train list extra', timestamp='2026-09-09T11:00:00')
        record(db, actor='alice', command='ml train list', timestamp='2026-09-09T12:00:01')
        db.commit()
    login(client)
    response = client.get('/cli-permission/admin/analytics', params={
        'grain': 'hour', 'begin': '2026-09-09T19:00:00', 'end': '2026-09-09T20:00:00',
        'environment': 'prod', 'business_id': 'selected'})
    assert '<strong>3<small>次</small></strong>' in response.text
    assert 'id="analytics-advanced-filters" class="analytics-filter-advanced" hidden' not in response.text
    assert 'aria-expanded="true">收起筛选</button>' in response.text
    command_link = unescape(re.search(r'href="([^"]+command_exact=[^"]+)"[^>]*>ml train list</a>', response.text)[1])
    parsed = parse_qs(urlsplit(command_link).query)
    assert parsed['command_exact'] == ['ml train list'] and parsed['business_id'] == ['selected']
    assert '2 条' in client.get(command_link).text
    denied_link = unescape(re.search(r'<a class="stat-card" href="([^"]+result=denied)"[^>]*><span>拒绝次数', response.text)[1])
    assert '1 条' in client.get(denied_link).text
    point_link = unescape(re.search(r'<tr><td>09-09 19:00</td>.*?<a href="([^"]+)"', response.text)[1])
    assert '3 条' in client.get(point_link).text


def test_dashboard_week_grain_groups_at_beijing_monday(system):
    app, client, _ = system
    with app.state.sessions() as db:
        record(db, actor='alice', command='ml train list', timestamp='2026-09-13T15:59:59')
        record(db, actor='alice', command='ml train list', timestamp='2026-09-13T16:00:00',
               allowed=False, reason='NOT_GRANTED')
        db.commit()
    login(client)
    response = client.get('/cli-permission/admin/analytics', params={
        'grain': 'week', 'begin': '2026-09-13T23:00:00', 'end': '2026-09-14T01:00:00'})
    assert response.status_code == 200
    chart = json.loads(unescape(re.search(r"data-analysis-chart='([^']+)'", response.text)[1]))
    assert chart['grain'] == '周'
    assert [(point['label'], point['total'], point['denied'], point['commands'])
            for point in chart['points']] == [
                ('09-07 周', 1, 0, [1]), ('09-14 周', 1, 1, [1])]
    assert chart['distribution'][0]['value'] == 2


def test_dashboard_renders_decimal_aggregates_from_mysql(system, monkeypatch):
    app, client, _ = system
    with app.state.sessions() as db:
        record(db, actor='alice', command='ml train list', timestamp='2026-09-09T16:00:00',
               allowed=False, reason='NOT_GRANTED')
        record(db, actor='bob', command='ml train start', timestamp='2026-09-10T16:00:00')
        db.commit()
    login(client)

    session_type = app.state.sessions.class_
    original_execute = session_type.execute

    class DecimalAggregateResult:
        def __init__(self, result, has_sum):
            self.result = result
            self.has_sum = has_sum

        def one(self):
            total, denied, users = self.result.one()
            return Decimal(total), Decimal(denied), Decimal(users)

        def all(self):
            rows = self.result.all()
            if self.has_sum:
                return [(key, Decimal(total), Decimal(denied))
                        for key, total, denied in rows]
            return [(*row[:-1], Decimal(row[-1])) for row in rows]

    def execute_with_decimal_sum(self, statement, *args, **kwargs):
        result = original_execute(self, statement, *args, **kwargs)
        sql = str(statement).lower()
        return DecimalAggregateResult(result, 'sum(' in sql) if (
            'cli_call_logs' in sql and ('sum(' in sql or 'count(' in sql)) else result

    monkeypatch.setattr(session_type, 'execute', execute_with_decimal_sum)
    response = client.get('/cli-permission/admin/analytics', params={
        'begin': '2026-09-10T00:00:00', 'end': '2026-09-11T23:59:59',
        'commands_top': 50, 'actors_top': 30})
    assert response.status_code == 200
    chart = json.loads(unescape(re.search(r"data-analysis-chart='([^']+)'", response.text)[1]))
    assert chart['points'][0]['total'] == 1
    assert chart['points'][0]['denied'] == 1
    assert chart['points'][0]['allowed'] == 0
    assert chart['points'][1]['denied'] == 0
    assert chart['points'][1]['allowed'] == 1
    assert all(type(item['value']) is int for item in chart['ranking'])
    assert all(type(item['value']) is int for item in chart['distribution'])
    assert all(type(item['value']) is int for item in chart['versions'])
    assert all(type(item['value']) is int for item in chart['environments'])
    assert chart['versions'] == [{'label': '1.0.0', 'value': 2, 'href': chart['versions'][0]['href']}]
    assert chart['environments'] == [{'label': 'prod', 'value': 2, 'href': chart['environments'][0]['href']}]
    assert '<strong class="analytics-danger">1<small>次</small></strong>' in response.text


def test_dashboard_versions_and_environments_full_distribution_and_drilldown(system):
    app, client, _ = system
    with app.state.sessions() as db:
        entries = [
            ('1.0.9.6', 'prod'), ('1.0.9.6', 'prod'), ('1.0.9.6', 'staging'),
            ('1.0.9.5', 'prod'), ('1.0.9.5', 'test'),
            ('1.0.9.4', 'test'),
            ('1.0.9.3', 'dev'),
            ('1.0.9.2', 'dev'),
            ('1.0.9.1', 'staging'),
            ('1.0.9.0', 'uat'),
            ('', ''),
        ]
        for cli_version, env in entries:
            record(db, actor='alice', command='ml train list', timestamp='2026-09-10T02:00:00',
                   environment=env, cli_version=cli_version)
        db.commit()
    login(client)
    params = {'grain': 'day', 'begin': '2026-09-10T00:00:00', 'end': '2026-09-10T23:59:59'}
    response = client.get('/cli-permission/admin/analytics', params=params)
    assert response.status_code == 200
    chart = json.loads(unescape(re.search(r"data-analysis-chart='([^']+)'", response.text)[1]))
    assert [(item['label'], item['value']) for item in chart['versions']] == [
        ('1.0.9.6', 3), ('1.0.9.5', 2), ('未知版本', 1), ('1.0.9.0', 1),
        ('1.0.9.1', 1), ('1.0.9.2', 1), ('1.0.9.3', 1), ('1.0.9.4', 1)]
    assert all(item['label'] != '其他版本' for item in chart['versions'])
    assert next(item['href'] for item in chart['versions'] if item['label'] == '未知版本') == ''
    version_href = next(item['href'] for item in chart['versions'] if item['label'] == '1.0.9.6')
    assert parse_qs(urlsplit(version_href).query)['cli_version'] == ['1.0.9.6']
    assert '3 条' in client.get(version_href).text

    assert [(item['label'], item['value']) for item in chart['environments']] == [
        ('prod', 3), ('dev', 2), ('staging', 2), ('test', 2), ('未知环境', 1), ('uat', 1)]
    assert next(item['href'] for item in chart['environments'] if item['label'] == '未知环境') == ''
    env_href = next(item['href'] for item in chart['environments'] if item['label'] == 'staging')
    assert parse_qs(urlsplit(env_href).query)['environment'] == ['staging']
    assert '2 条' in client.get(env_href).text

    filtered = client.get('/cli-permission/admin/analytics', params=dict(params, environment='prod'))
    filtered_chart = json.loads(unescape(re.search(r"data-analysis-chart='([^']+)'", filtered.text)[1]))
    assert [(item['label'], item['value']) for item in filtered_chart['versions']] == [
        ('1.0.9.6', 2), ('1.0.9.5', 1)]
    assert [(item['label'], item['value']) for item in filtered_chart['environments']] == [('prod', 3)]


def test_dashboard_rejects_bad_ranges_and_escapes_command(system):
    app, client, _ = system
    login(client)
    for params in [
        {'grain': 'other'},
        {'begin': '2026-09-09T00:00'},
        {'grain': 'day', 'begin': '2026-09-10T00:00', 'end': '2026-09-09T00:00'},
        {'grain': 'day', 'begin': '2026-01-01T00:00', 'end': '2026-09-09T00:00'},
        {'grain': 'hour', 'begin': '2026-09-01T00:00', 'end': '2026-09-20T00:00'},
    ]:
        assert client.get('/cli-permission/admin/analytics', params=params).status_code == 400
    with app.state.sessions() as db:
        record(db, actor='alice', command='<script>bad</script>', timestamp='2026-09-09T11:00:00')
        db.commit()
    response = client.get('/cli-permission/admin/analytics', params={
        'grain': 'day', 'begin': '2026-09-09T18:00', 'end': '2026-09-09T20:00'})
    assert response.status_code == 200
    assert '&lt;script&gt;bad&lt;/script&gt;' in response.text
    assert '<script>bad</script>' not in response.text
