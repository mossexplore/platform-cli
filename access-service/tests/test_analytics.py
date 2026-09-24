from datetime import datetime
from html import unescape
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
        'period': 'custom', 'begin': '2026-09-10T00:00:00', 'end': '2026-09-10T23:59:59'})
    assert response.status_code == 200
    cards = re.findall(r'<strong(?: class="analytics-danger")?>(\d+)<small>(次|人)</small></strong>', response.text)
    assert cards == [('2', '次'), ('1', '次'), ('1', '次'), ('2', '人')]
    assert '拒绝率 50.0%' in response.text
    assert 'ml train start' in response.text and 'ml train list' in response.text
    assert '未获得当前环境授权' in response.text
    assert '拒绝较多的环境' in response.text and '拒绝较多的命令' in response.text
    assert response.text.count('class="analytics-trend-row"') == 24
    assert '09-10 00:00，检查 2 次，拒绝 1 次' in response.text


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
        'period': 'custom', 'begin': '2026-09-09T19:00:00', 'end': '2026-09-09T20:00:00',
        'environment': 'prod', 'business_id': 'selected'})
    assert '<strong>3<small>次</small></strong>' in response.text
    command_link = unescape(re.search(r'href="([^"]+command_exact=[^"]+)"[^>]*>ml train list</a>', response.text)[1])
    parsed = parse_qs(urlsplit(command_link).query)
    assert parsed['command_exact'] == ['ml train list'] and parsed['business_id'] == ['selected']
    assert '2 条' in client.get(command_link).text
    reason_link = unescape(re.search(r'href="([^"]+reason=NOT_GRANTED[^"]*)"', response.text)[1])
    assert '1 条' in client.get(reason_link).text
    denied_command_link = unescape(re.search(r'href="([^"]+result=denied[^"]+command_exact=ml\+train\+list[^"]*)"', response.text)[1])
    assert '1 条' in client.get(denied_command_link).text
    point_link = unescape(re.search(r'class="analytics-trend-row"[^>]*href="([^"]+)"', response.text)[1])
    assert '3 条' in client.get(point_link).text


def test_dashboard_rejects_bad_ranges_and_escapes_command(system):
    app, client, _ = system
    login(client)
    for params in [
        {'period': 'other'},
        {'period': 'custom'},
        {'period': 'custom', 'begin': '2026-09-10T00:00', 'end': '2026-09-09T00:00'},
        {'period': 'custom', 'begin': '2026-01-01T00:00', 'end': '2026-09-09T00:00'},
    ]:
        assert client.get('/cli-permission/admin/analytics', params=params).status_code == 400
    with app.state.sessions() as db:
        record(db, actor='alice', command='<script>bad</script>', timestamp='2026-09-09T11:00:00')
        db.commit()
    response = client.get('/cli-permission/admin/analytics', params={
        'period': 'custom', 'begin': '2026-09-09T18:00', 'end': '2026-09-09T20:00'})
    assert response.status_code == 200
    assert '&lt;script&gt;bad&lt;/script&gt;' in response.text
    assert '<script>bad</script>' not in response.text
