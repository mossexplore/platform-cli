import re
from sqlalchemy import select, func
from app.models import User, Grant, Environment, Audit
from test_service import system, login


def test_ungranted_people_and_combined_filters(system):
    app, client, _ = system
    with app.state.sessions() as db:
        db.add(User(username='bob', display_name='无授权人员'))
        db.commit()
    login(client)
    html = client.get('/cli-permission/admin?tab=users').text
    assert 'data-account="bob"' in html and '未授权' in html
    assert 'data-account="alice"' in html
    assert html.count('>人员与授权</a>') == 1
    assert '>人员管理</a>' not in html and '>访问授权</a>' not in html
    ids = re.findall(r'<dialog[^>]+id="([^"]+)"', html)
    assert len(ids) == len(set(ids))
    filtered = client.get('/cli-permission/admin?tab=users&grant_status=none&q=无授权').text
    assert 'data-account="bob"' in filtered and 'data-account="alice"' not in filtered
    active = client.get('/cli-permission/admin?tab=users&grant_status=active').text
    assert 'data-account="alice"' in active and 'data-account="bob"' not in active
    assert client.get('/cli-permission/admin?tab=users&grant_status=invalid').status_code == 400


def test_create_person_with_optional_grants_is_atomic(system):
    app, client, _ = system
    csrf = login(client)
    result = client.post('/cli-permission/admin/users', data={'csrf':csrf, 'username':'bob',
        'display_name':'Bob', 'enabled':'true', 'environments':['prod'],
        'expires_at':'2030-09-08T14:54:00', 'note':'创建时授权'})
    assert result.status_code == 200
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username=='bob'))
        grant = db.scalar(select(Grant).where(Grant.user_id==user.id))
        assert grant.enabled and grant.note == '创建时授权'
        assert grant.expires_at.isoformat() == '2030-09-08T06:54:00'
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action=='grants.save')) == 1
    for name, envs in [('bad', ['prod', 'missing'])]:
        assert client.post('/cli-permission/admin/users',data={'csrf':csrf,'username':name,'environments':envs}).status_code == 400
        with app.state.sessions() as db:
            assert db.scalar(select(User).where(User.username==name)) is None
    assert client.post('/cli-permission/admin/users',data={'csrf':csrf,'username':'no-grants','enabled':'true'}).status_code == 200
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username=='no-grants'))
        assert db.scalar(select(Grant).where(Grant.user_id==user.id)) is None
        db.scalar(select(Environment)).enabled = False
        db.commit()
    assert client.post('/cli-permission/admin/users',data={'csrf':csrf,'username':'disabled-env','environments':['prod']}).status_code == 400
    with app.state.sessions() as db:
        assert db.scalar(select(User).where(User.username=='disabled-env')) is None


def test_person_edit_preserves_grants_and_grant_updates_return_to_unified_page(system):
    app, client, _ = system
    csrf=login(client)
    assert client.post('/cli-permission/admin/users',data={'csrf':csrf,'item_id':1,'username':'alice','display_name':'Changed'}).status_code == 200
    with app.state.sessions() as db:
        assert db.get(Grant,1).enabled
        assert not db.get(User,1).enabled
    response=client.post('/cli-permission/admin/grants',data={'csrf':csrf,'item_id':1,'username':'alice','environment':'prod','enabled':'true'},follow_redirects=False)
    assert response.headers['location'] == '/cli-permission/admin?tab=users&saved=1'
    html=client.get('/cli-permission/admin?tab=users').text
    assert 'value="alice" readonly' in html
    assert 'grant-edit-1' in html and 'account-grants-1' in html and 'add-grants-1' in html


def test_single_edit_entry_contains_person_and_grant_controls(system):
    _, client, _ = system
    login(client)
    html = client.get('/cli-permission/admin?tab=users').text
    row = html.split('data-account="alice"')[1].split('</tr>')[0]
    assert row.count('<button') == 2
    assert 'aria-label="删除 alice"' in row
    assert 'aria-label="编辑 alice"' in row
    panel = html.split('<dialog class="drawer person-editor" id="account-grants-1"')[1].split('</dialog>')[0]
    assert '保存人员信息' in panel and '配置授权' in panel
    assert 'name="display_name"' in panel and 'name="enabled"' in panel
    assert 'grant-edit-1' in panel


def test_environment_summary_only_shows_effective_grants(system):
    from datetime import timedelta
    from app.models import now

    app, client, _ = system
    with app.state.sessions() as db:
        for name, env_enabled, granted, expires in [
            ('a-expiring', True, True, now() + timedelta(days=2)),
            ('b-disabled', False, True, None),
            ('c-revoked', True, False, None),
            ('d-expired', True, True, now() - timedelta(days=1)),
            ('e-ungranted', True, None, None),
        ]:
            env = Environment(name=name, display_name=name,
                              platform_origin='https://example.com', enabled=env_enabled)
            db.add(env)
            db.flush()
            if granted is not None:
                db.add(Grant(user_id=1, environment_id=env.id, enabled=granted, expires_at=expires))
        db.commit()
    login(client)
    html = client.get('/cli-permission/admin?tab=users').text
    row = html.split('data-account="alice"')[1].split('</tr>')[0]
    assert '>a-expiring</span>' in row and '>prod</span>' in row
    assert '· 即将到期</span>' not in row and '· 生效中</span>' not in row
    assert 'class="count"' not in row
    for name in ('b-disabled', 'c-revoked', 'd-expired', 'e-ungranted'):
        assert name not in row
    panel = html.split('id="account-grants-1"')[1].split('</dialog>')[0]
    for name in ('b-disabled', 'c-revoked', 'd-expired'):
        assert name in panel
    with app.state.sessions() as db:
        db.scalar(select(Grant).join(Environment).where(Environment.name == 'c-revoked')).enabled = True
        db.commit()
    row = client.get('/cli-permission/admin?tab=users').text.split('data-account="alice"')[1].split('</tr>')[0]
    assert '<span class="count">+1</span>' in row
    with app.state.sessions() as db:
        db.get(User, 1).enabled = False
        db.commit()
    row = client.get('/cli-permission/admin?tab=users').text.split('data-account="alice"')[1].split('</tr>')[0]
    assert '未授权' in row and 'class="count"' not in row
    assert 'prod' not in row and 'a-expiring' not in row
