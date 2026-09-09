from datetime import timedelta
from sqlalchemy import select
from app.models import User, Environment, Grant, Audit, now
from app.admin_views import overview, audit_detail
from test_service import system, login


def test_effective_grant_counts_and_filters(system):
    app, client, _ = system
    login(client)
    with app.state.sessions() as db:
        grant = db.scalar(select(Grant))
        grant.expires_at = now() + timedelta(days=2)
        db.commit()
        assert overview(db) == {'users': 1, 'environments': 1, 'active': 1, 'expiring': 1}
    assert '授权列表 <span class="count">1 条' in client.get('/admin?tab=grants&status=expiring').text
    with app.state.sessions() as db:
        db.scalar(select(User)).enabled = False
        db.commit()
        assert overview(db)['active'] == 0
        assert overview(db)['expiring'] == 0
    assert '授权列表 <span class="count">0 条' in client.get('/admin?tab=grants&status=active').text
    assert '人员已停用' in client.get('/admin?tab=grants&status=disabled').text


def test_name_and_environment_search(system):
    _, client, _ = system
    login(client)
    assert '人员列表 <span class="count">1 条' in client.get('/admin?tab=users&q=Alice').text
    assert '环境列表 <span class="count">1 条' in client.get('/admin?tab=environments&q=生产').text
    assert '授权列表 <span class="count">1 条' in client.get('/admin?tab=grants&q=prod').text
    assert client.get('/admin?tab=users&status=expired').status_code == 400


def test_search_pagination_keeps_status(system):
    app, client, _ = system
    login(client)
    with app.state.sessions() as db:
        db.add_all(User(username=f'person-{i}') for i in range(21))
        db.commit()
    page = client.get('/admin?tab=users&q=person&status=enabled').text
    assert 'status=enabled&page=2' in page
    page2 = client.get('/admin?tab=users&q=person&status=enabled&page=2').text
    assert '人员列表 <span class="count">21 条' in page2


def test_expired_grant_and_environment_disabled(system):
    app, client, _ = system
    login(client)
    with app.state.sessions() as db:
        db.scalar(select(Grant)).expires_at = now() - timedelta(seconds=5)
        db.commit()
    assert '已过期' in client.get('/admin?tab=grants&status=expired').text
    with app.state.sessions() as db:
        db.scalar(select(Environment)).enabled = False
        db.commit()
    assert '环境已停用' in client.get('/admin?tab=grants&status=disabled').text


def test_audit_changes_are_readable_and_escaped(system):
    app, client, _ = system
    csrf = login(client)
    client.post('/admin/users', data={'csrf': csrf, 'item_id':1, 'username':'alice', 'display_name':'<script>bad</script>'})
    response = client.get('/admin?tab=audit')
    assert '变更前' in response.text and '变更后' in response.text
    assert '&lt;script&gt;bad&lt;/script&gt;' in response.text
    assert '<script>bad</script>' not in response.text
    with app.state.sessions() as db:
        entry = db.scalar(select(Audit).where(Audit.action == 'users.save'))
        change = next(row for row in audit_detail(entry)['changes'] if row['field'] == '启用状态')
        assert change == {'field':'启用状态', 'before':'启用', 'after':'停用'}
