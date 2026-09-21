from datetime import timedelta
from sqlalchemy import select
from app.models import Admin, CallLog, now
from app.version_models import VersionPolicy, VersionException
from test_service import system, login
from test_version_policy import policy, call


def test_policy_list_pagination_filters_and_page_clamping(system):
    app, client, _ = system
    for i in range(12):
        policy(app, environment='prod' if i % 2 else '', enabled=bool(i % 2))
    login(client)
    result = client.get('/cli-permission/admin/versions')
    assert result.status_code == 200 and '共 12 条' in result.text
    assert result.text.count('class="text-button version-name"') == 10
    result = client.get('/cli-permission/admin/versions?view=policies&page=999')
    assert '第 2 / 2 页' in result.text
    assert result.text.count('class="text-button version-name"') == 2
    assert '共 6 条' in client.get('/cli-permission/admin/versions?status=active&environment=prod').text
    assert '暂无匹配策略' in client.get('/cli-permission/admin/versions?q=missing').text


def test_scheduled_policy_and_expired_exception_states(system):
    app, client, _ = system
    pid = policy(app, effective_at=now() + timedelta(days=1))
    with app.state.sessions() as db:
        db.add(VersionException(policy_id=pid,environment='prod',business_id='selected',username='alice',
            minimum_version='1.0.0',maximum_version='1.0.2',expires_at=now()-timedelta(seconds=1),reason='test',created_by='admin'))
        db.commit()
    login(client)
    result = client.get('/cli-permission/admin/versions?status=scheduled')
    assert '共 1 条' in result.text and '>待生效</span>' in result.text
    result = client.get('/cli-permission/admin/versions?view=exceptions&status=expired')
    assert '共 1 条' in result.text and '>已到期</span>' in result.text
    assert 'data-open="exception-revoke-1"' not in result.text


def test_usage_filters_denials_and_encoded_log_links(system):
    app, client, _ = system
    policy(app)
    call(client, business='team&ops')
    call(client, '1.0.3', business='team&ops')
    login(client)
    html = client.get('/cli-permission/admin/versions?view=usage&status=denied&business_id=team').text
    assert '旧客户端默认' in html and '共 1 条' in html
    assert 'business_id=team%26ops' in html
    assert '暂无匹配的版本使用记录' in client.get('/cli-permission/admin/versions?view=usage&q=9.9.9').text


def test_json_preview_validates_and_never_publishes(system):
    app, client, _ = system
    call(client)
    csrf = login(client)
    url = '/cli-permission/admin/versions/policies'
    headers = {'accept':'application/json'}
    data = {'csrf':csrf,'name':'<script>bad</script>','minimum_version':'1.0.3','mode':'enforce'}
    assert client.post(url,headers=headers,data={**data,'csrf':'wrong'}).status_code == 403
    assert client.post(url,headers=headers,data={**data,'minimum_version':'bad'}).status_code == 400
    result = client.post(url,headers=headers,data=data)
    assert result.status_code == 200
    html = result.json()['preview_html']
    assert '&lt;script&gt;' in html and '<script>' not in html
    assert '其中 1 次会被拒绝' in html
    with app.state.sessions() as db:
        assert db.scalar(select(VersionPolicy)) is None
    assert client.post(url,headers=headers,data={**data,'intent':'publish'},follow_redirects=False).status_code == 303


def test_regular_admin_gets_details_without_write_controls(system):
    app, client, _ = system
    policy(app)
    login(client)
    with app.state.sessions() as db:
        db.get(Admin,1).role='admin'
        db.commit()
    html = client.get('/cli-permission/admin/versions').text
    assert 'policy-detail-1' in html
    assert 'id="policy-create"' not in html
    assert 'data-copy-policy=' not in html
    assert 'id="exception-create"' not in html
    assert 'policy-toggle-1' not in html


def test_all_views_keep_shared_navigation_and_drawer_forms(system):
    _, client, _ = system
    login(client)
    for view in ['policies','usage','exceptions']:
        response=client.get('/cli-permission/admin/versions',params={'view':view})
        assert response.status_code==200
        assert 'class="version-tabs"' in response.text
        assert 'class="drawer version-drawer"' in response.text
        assert 'aria-labelledby="policy-create-title"' in response.text
    assert client.get('/cli-permission/admin/versions?view=invalid').status_code==422
