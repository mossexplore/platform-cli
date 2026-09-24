from datetime import datetime
from html import unescape
import json
import re
from urllib.parse import parse_qs, urlsplit
from app.models import CallLog
from test_service import system, login


def record(db, *, actor, command, timestamp, allowed=True, reason='ALLOWED', environment='prod', business_id='selected'):
    db.add(CallLog(actor=actor, command=command, environment=environment,
        business_id=business_id, source_ip='127.0.0.1', allowed=allowed,
        reason=reason, created_at=datetime.fromisoformat(timestamp)))


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
    assert all(name in response.text for name in ('命令分布', '调用趋势', '调用次数分布', '调用次数排行'))
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
