"""版本准入、旧客户端兼容、管理审计、网关边界及迁移回归。"""
import json
from datetime import timedelta
import pytest
from sqlalchemy import select, text
from app.models import Admin, Audit, CallLog, Grant, SchemaVersion, now
from app.migrations import migrate, SCHEMA_VERSION
from app.version_models import VersionPolicy, VersionException
from app.version_policy import version_tuple
from test_service import system, login, check


def policy(app, **values):
    with app.state.sessions() as db:
        item = VersionPolicy(name='test-policy', created_by='admin', **{
            'mode': 'enforce', 'minimum_version': '1.0.3', **values})
        db.add(item)
        db.commit()
        return item.id


def call(client, version=None, business='selected', protocol=None, gateway=False, **body):
    headers = {'businessid': business}
    if version is not None:
        headers['x-cli-version'] = version
    if protocol is not None:
        headers['x-cli-protocol-version'] = protocol
    if gateway:
        headers['authorization'] = 'Bearer ' + 's' * 32
    return client.post('/cli-permission/api/v1/' + ('gateway/check' if gateway else 'access/check'),
        headers=headers, json={'username': 'alice', 'environment': 'prod',
            'platform_origin': 'https://platform.example.com', **body})


@pytest.mark.parametrize('version,allowed,reason', [
    (None, False, 'CLI_VERSION_TOO_OLD'), ('1.0.2', False, 'CLI_VERSION_TOO_OLD'),
    ('1.0.3', True, None), ('1.0.10', True, None), ('2.0.0', True, None),
    ('', False, 'CLI_VERSION_INVALID'), ('v1.0.3', False, 'CLI_VERSION_INVALID'),
    ('1.0.3rc1', False, 'CLI_VERSION_INVALID'), ('01.0.3', False, 'CLI_VERSION_INVALID'),
    ('x' * 100, False, 'CLI_VERSION_INVALID')])
def test_version_gate_and_logs(system, version, allowed, reason):
    app, client, _ = system
    policy(app)
    result = call(client, version).json()
    assert result['allowed'] is allowed
    if reason:
        assert result['reason'] == reason
    with app.state.sessions() as db:
        row = db.scalar(select(CallLog))
        assert row.cli_version == ('1.0.0' if version is None else version[:64])
        assert row.version_source == ('legacy_default' if version is None else 'reported')
        assert json.loads(row.version_decision)['allowed'] is allowed


def test_missing_all_identifiers_defaults_and_no_policy_compatibility(system):
    app, client, _ = system
    assert check(client).json() == {'allowed': True, 'username': 'alice', 'environment': 'prod'}
    policy(app, minimum_version='1.0.0')
    assert call(client).json()['allowed']
    assert version_tuple('1.0.10') > version_tuple('1.0.9')


@pytest.mark.parametrize('mode,allowed,warning', [('observe', True, False), ('warn', True, True), ('enforce', False, False)])
def test_modes(system, mode, allowed, warning):
    app, client, _ = system
    policy(app, mode=mode, recommended_version='1.0.5')
    result = call(client).json()
    assert result['allowed'] is allowed
    assert result.get('version_policy', result)['warning'] is warning


def test_scope_strictest_future_and_protocol(system):
    app, client, _ = system
    policy(app, minimum_version='1.0.1')
    policy(app, environment='prod', business_id='selected', minimum_version='1.0.5')
    policy(app, environment='dev', minimum_version='9.0.0')
    policy(app, minimum_version='8.0.0', effective_at=now() + timedelta(days=1))
    assert not call(client, '1.0.3').json()['allowed']
    assert call(client, '1.0.3', business='another').json()['allowed']
    assert call(client, '1.0.5', protocol='2').json()['reason'] == 'CLI_PROTOCOL_UNSUPPORTED'


def test_exception_is_scoped_expires_and_cannot_bypass_block_or_grants(system):
    app, client, _ = system
    pid = policy(app, blocked_versions='["1.0.1"]')
    with app.state.sessions() as db:
        db.add(VersionException(policy_id=pid, environment='prod', business_id='selected', username='alice',
            minimum_version='1.0.0', maximum_version='1.0.2', expires_at=now() + timedelta(hours=1),
            reason='migration', created_by='admin'))
        db.commit()
    assert call(client).json()['allowed']
    assert not call(client, business='another').json()['allowed']
    assert call(client, '1.0.1').json()['reason'] == 'CLI_VERSION_BLOCKED'
    with app.state.sessions() as db:
        db.get(Grant, 1).enabled = False
        db.commit()
    assert call(client).json()['reason'] == 'NOT_GRANTED'
    with app.state.sessions() as db:
        db.get(Grant, 1).enabled = True
        db.get(VersionException, 1).expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert not call(client).json()['allowed']


def test_gateway_requires_secret_even_when_version_missing(system):
    app, client, _ = system
    assert call(client, gateway=True).status_code == 503
    app.state.settings.gateway_token = 's' * 32
    endpoint = '/cli-permission/api/v1/gateway/check'
    body = {'username': 'alice', 'environment': 'prod', 'platform_origin': 'https://platform.example.com'}
    assert client.post(endpoint, headers={'businessid': 'selected'}, json=body).status_code == 401
    policy(app)
    response = call(client, gateway=True)
    assert response.status_code == 403 and response.json()['code'] == 'CLI_VERSION_TOO_OLD'
    assert call(client, '1.0.3', gateway=True).status_code == 200
    with app.state.sessions() as db:
        assert all(row.check_source == 'gateway' for row in db.scalars(select(CallLog)))


def test_admin_preview_publish_revoke_and_audit(system):
    app, client, _ = system
    call(client)
    assert client.get('/cli-permission/admin/versions', follow_redirects=False).status_code == 303
    csrf = login(client)
    data = {'csrf': csrf, 'name': 'prod rollout', 'minimum_version': '1.0.3', 'mode': 'enforce'}
    endpoint = '/cli-permission/admin/versions/policies'
    assert client.post(endpoint, data={**data, 'csrf': 'bad'}).status_code == 403
    preview = client.post(endpoint, data=data)
    assert preview.status_code == 200 and '其中 1 次会被拒绝' in preview.text
    assert call(client).json()['allowed']
    assert client.post(endpoint, data={**data, 'intent': 'publish'}).status_code == 200
    assert not call(client).json()['allowed']
    assert client.post('/cli-permission/admin/versions/policies/1/toggle', data={'csrf': csrf, 'enabled': 'false'}).status_code == 200
    assert call(client).json()['allowed']
    assert client.post('/cli-permission/admin/versions/policies/1/toggle', data={'csrf': csrf, 'enabled': 'true'}).status_code == 200
    assert not call(client).json()['allowed']
    with app.state.sessions() as db:
        assert len(db.scalars(select(Audit).where(Audit.action.like('version_policy.%'))).all()) == 3
    html = client.get('/cli-permission/admin/versions?view=usage').text
    assert '1.0.0' in html and '旧客户端默认' in html
    assert '暂无匹配记录' in client.get('/cli-permission/admin/calls?cli_version=9.0.0').text


def test_only_disabled_policy_can_be_deleted_and_history_is_kept(system):
    app, client, _ = system
    policy_id = policy(app)
    with app.state.sessions() as db:
        db.add(VersionException(policy_id=policy_id, environment='prod', business_id='selected',
            username='alice', minimum_version='1.0.0', maximum_version='1.0.2',
            expires_at=now() + timedelta(days=1), reason='等待升级', created_by='admin'))
        db.commit()
    csrf = login(client)
    path = f'/cli-permission/admin/versions/policies/{policy_id}/delete'
    assert call(client).json()['allowed']  # Existing exception still allows the old version.
    assert f'data-open="policy-delete-{policy_id}"' not in client.get('/cli-permission/admin/versions').text
    assert client.post(path, data={'csrf': csrf, 'confirmation': 'yes'}).status_code == 400
    assert client.post(f'/cli-permission/admin/versions/policies/{policy_id}/toggle',
        data={'csrf': csrf, 'enabled': 'false'}).status_code == 200
    page = client.get('/cli-permission/admin/versions?view=policies&status=disabled').text
    assert f'data-open="policy-delete-{policy_id}"' in page
    assert client.post(path, data={'csrf': 'wrong', 'confirmation': 'yes'}).status_code == 403
    assert client.post(path, data={'csrf': csrf, 'confirmation': 'YES'}).status_code == 400
    response = client.post(path, data={'csrf': csrf, 'confirmation': 'yes'})
    assert response.status_code == 200 and '策略已删除' in response.text
    assert 'test-policy' not in client.get('/cli-permission/admin/versions?view=policies').text
    assert 'test-policy' in client.get('/cli-permission/admin/versions?view=exceptions').text
    assert '删除版本策略' in client.get('/cli-permission/admin?tab=audit').text
    with app.state.sessions() as db:
        assert db.get(VersionPolicy, policy_id).deleted_at is not None
        assert not db.scalar(select(VersionException).where(VersionException.policy_id == policy_id)).enabled
        audit = db.scalar(select(Audit).where(Audit.action == 'version_policy.delete'))
        detail = json.loads(audit.detail)
        assert detail['before']['name'] == 'test-policy'
        assert detail['revoked_exception_ids'] == [1]
    assert client.post(path, data={'csrf': csrf, 'confirmation': 'yes'}).status_code == 404
    assert client.post(f'/cli-permission/admin/versions/policies/{policy_id}/toggle',
        data={'csrf': csrf, 'enabled': 'true'}).status_code == 404


@pytest.mark.parametrize('overrides', [
    {'minimum_version':'1.0'}, {'recommended_version':'0.1.0'}, {'blocked_versions':'bad'},
    {'upgrade_url':'javascript:alert(1)'}, {'mode':'bad'}, {'business_id':'biz'},
    {'environment':'missing'}, {'recommended_version':'1.0.3','blocked_versions':'1.0.3'}])
def test_invalid_admin_policy(system, overrides):
    _, client, _ = system
    csrf = login(client)
    result = client.post('/cli-permission/admin/versions/policies', data={
        'csrf':csrf, 'name':'test', 'minimum_version':'1.0.3', 'intent':'publish', **overrides})
    assert result.status_code == 400


def test_regular_admin_cannot_change_versions(system):
    app, client, _ = system
    csrf = login(client)
    with app.state.sessions() as db:
        db.get(Admin, 1).role = 'admin'
        db.commit()
    assert client.get('/cli-permission/admin/versions').status_code == 200
    assert client.post('/cli-permission/admin/versions/policies', data={
        'csrf':csrf,'name':'bad','intent':'publish'}).status_code == 403
    assert client.post('/cli-permission/admin/versions/policies/1/delete', data={
        'csrf':csrf,'confirmation':'yes'}).status_code == 403


def test_v7_migration_preserves_logs_and_is_repeatable(system):
    app, client, _ = system
    call(client)
    VersionException.__table__.drop(app.state.engine)
    VersionPolicy.__table__.drop(app.state.engine)
    with app.state.engine.begin() as conn:
        for name in ('cli_version','version_source','protocol_version','installation_id','invocation_id',
                     'request_id','check_source','version_decision'):
            conn.execute(text(f'ALTER TABLE cli_call_logs DROP COLUMN {name}'))
        conn.execute(text('UPDATE schema_versions SET version=7'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        row = db.scalar(select(CallLog))
        assert row.actor == 'alice' and row.cli_version == '1.0.0'
        assert row.version_source == 'historical_default'
        assert db.get(SchemaVersion, SCHEMA_VERSION)
    assert call(client).json()['allowed']


def test_v9_migration_preserves_policies_and_adds_deletion_marker(system):
    app, _, _ = system
    policy_id = policy(app)
    with app.state.engine.begin() as conn:
        conn.execute(text('ALTER TABLE cli_version_policies DROP COLUMN deleted_at'))
        conn.execute(text('UPDATE schema_versions SET version=9'))
    migrate(app.state.engine, app.state.sessions)
    migrate(app.state.engine, app.state.sessions)
    with app.state.sessions() as db:
        assert db.get(SchemaVersion, SCHEMA_VERSION)
        item = db.get(VersionPolicy, policy_id)
        assert item.name == 'test-policy' and item.deleted_at is None


def test_duplicate_version_and_protocol_headers_do_not_bypass(system):
    app, client, _ = system
    policy(app)
    body = {'username': 'alice', 'environment': 'prod', 'platform_origin': 'https://platform.example.com'}
    for headers, reason in [
        ([('x-cli-version','1.0.3'),('x-cli-version','1.0.2')], 'CLI_VERSION_INVALID'),
        ([('x-cli-version','1.0.3'),('x-cli-protocol-version','1'),('x-cli-protocol-version','2')], 'CLI_PROTOCOL_UNSUPPORTED')]:
        response = client.post('/cli-permission/api/v1/access/check',
            headers=[('businessid','selected'), *headers], json=body)
        assert response.json()['reason'] == reason


def test_exception_admin_flow_and_time_conversion(system):
    app, client, _ = system
    policy(app)
    csrf = login(client)
    data = {'csrf':csrf, 'policy_id':1, 'environment':'prod', 'business_id':'selected',
        'username':'alice', 'minimum_version':'1.0.0', 'maximum_version':'1.0.2',
        'expires_at':'2099-09-21T14:00:00', 'reason':'等待升级窗口'}
    endpoint = '/cli-permission/admin/versions/exceptions'
    assert client.post(endpoint,data={**data,'csrf':'bad'}).status_code == 403
    assert client.post(endpoint,data={**data,'expires_at':'2000-01-01'}).status_code == 400
    assert client.post(endpoint,data={**data,'maximum_version':'0.0.1'}).status_code == 400
    assert client.post(endpoint,data=data).status_code == 200
    assert call(client).json()['allowed']
    with app.state.sessions() as db:
        assert db.get(VersionException,1).expires_at.isoformat() == '2099-09-21T06:00:00'
    assert client.post('/cli-permission/admin/versions/exceptions/1/revoke',data={'csrf':csrf}).status_code == 200
    assert not call(client).json()['allowed']


def test_observation_does_not_change_recommendation_and_strictest_upgrade_link_wins(system):
    app, client, _ = system
    policy(app, minimum_version='1.0.1', upgrade_url='https://example.com/global')
    policy(app, environment='prod', business_id='selected', minimum_version='1.0.5', upgrade_url='https://example.com/business')
    policy(app, mode='observe', minimum_version='9.0.0', recommended_version='9.0.0')
    response = call(client).json()
    assert response['minimum_version'] == response['recommended_version'] == '1.0.5'
    assert response['upgrade_url'] == 'https://example.com/business'


def test_version_page_and_preview_escape_content(system):
    _, client, _ = system
    csrf = login(client)
    data = {'csrf':csrf, 'name':'<script>alert(1)</script>', 'minimum_version':'1.0.3',
        'effective_at':'2099-09-21T14:00:00'}
    response = client.post('/cli-permission/admin/versions/policies',data=data)
    assert '&lt;script&gt;' in response.text and '<script>alert' not in response.text
    assert '2099-09-21 14:00:00' in response.text
    assert '>仅观察<' in response.text
