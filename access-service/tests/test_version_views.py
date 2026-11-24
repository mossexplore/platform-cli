import json
from datetime import timedelta
from sqlalchemy import select
from app.models import Admin, Audit, CallLog, Environment, Grant, now
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


def test_multi_environment_policy_preview_publish_edit_and_exceptions(system):
    app, client, _ = system
    with app.state.sessions() as db:
        for name, display_name in [('stage', '预发布'), ('stage-other', '另一环境')]:
            env = Environment(name=name, display_name=display_name, platform_origin='https://platform.example.com')
            db.add(env)
            db.flush()
            db.add(Grant(user_id=1, environment_id=env.id))
        db.commit()
    for env in ('prod', 'stage', 'stage-other'):
        assert call(client, environment=env).json()['allowed']
    assert call(client, business='other').json()['allowed']
    csrf = login(client)
    root = '/cli-permission/admin/versions'
    url = root + '/policies'
    data = {'csrf': csrf, 'name': 'Shared rollout', 'environment_scope': 'selected',
            'environment': ['stage', 'prod', 'stage'], 'business_id': 'selected',
            'minimum_version': '1.0.3', 'mode': 'enforce'}
    for invalid in ({'environment': []}, {'environment': ['prod', 'unknown']}, {'environment_scope': 'all'}):
        assert client.post(url, data={**data, **invalid, 'intent': 'publish'}).status_code == 400
    preview = client.post(url, data=data)
    assert preview.status_code == 200 and '其中 2 次会被拒绝' in preview.text
    assert 'prod、stage' in preview.text and preview.text.count('name="environment"') == 2
    assert call(client, environment='stage').json()['allowed']
    assert client.post(url, data={**data, 'intent': 'publish'}, follow_redirects=False).status_code == 303
    with app.state.sessions() as db:
        item = db.scalars(select(VersionPolicy)).one()
        assert item.environments == ['prod', 'stage']
        policy_id = item.id
    for env in ('prod', 'stage'):
        decision = call(client, environment=env).json()
        assert decision['reason'] == 'CLI_VERSION_TOO_OLD' and decision['policy_ids'] == [policy_id]
    assert call(client, environment='stage-other').json()['allowed']
    assert call(client, business='other', environment='stage').json()['allowed']
    html = client.get(root, params={'environment': 'stage'}).text
    assert '生产、预发布' in html and '共 1 条' in html
    assert html.count('"environments": ["prod", "stage"]') == 3
    assert '暂无匹配策略' in client.get(root, params={'environment': 'stage-other'}).text

    exception = {'csrf': csrf, 'policy_id': policy_id, 'environment': 'stage',
                 'business_id': 'selected', 'username': 'alice', 'minimum_version': '1.0.0',
                 'maximum_version': '1.0.2', 'expires_at': '2099-09-21T14:00:00', 'reason': '等待升级'}
    assert client.post(root + '/exceptions', data={**exception, 'environment': 'stage-other'}).status_code == 400
    assert client.post(root + '/exceptions', data=exception, follow_redirects=False).status_code == 303
    assert call(client, environment='stage').json()['allowed']
    assert not call(client).json()['allowed']

    edit_url = f'{url}/{policy_id}'
    edit = {**data, 'environment': ['stage-other']}
    response = client.post(edit_url, data=edit, headers={'accept': 'application/json'})
    assert response.status_code == 200
    assert '范围内 9 次检查，其中 2 次会被拒绝' in response.json()['preview_html']
    assert client.post(edit_url, data={**edit, 'intent': 'publish'}, follow_redirects=False).status_code == 303
    assert call(client).json()['allowed']
    assert call(client, environment='stage').json()['allowed']
    assert not call(client, environment='stage-other').json()['allowed']
    with app.state.sessions() as db:
        audit = db.scalar(select(Audit).where(Audit.action == 'version_policy.update'))
        detail = json.loads(audit.detail)
        assert detail['before']['environment'] == ['prod', 'stage']
        assert detail['after']['environment'] == ['stage-other']
    assert 'prod、stage' in client.get('/cli-permission/admin?tab=audit').text


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
