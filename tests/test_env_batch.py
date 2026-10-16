"""环境列表通过一次真实 HTTP 请求取得汇总和各环境结果。"""
import json
from unittest.mock import patch

import httpx
import pytest
from test_env_status import make_runtime
from wiserec_cli.business import Department, Tenant
from wiserec_cli.env_access import environment_statuses, query_environment_access
from wiserec_cli.errors import MlError
from wiserec_cli.models import Credentials


def context(runtime, name, username):
    runtime.credentials.save(Credentials.create(name, 'cookie', 'csrf', username, 600))
    runtime.business.refresh(name, username, [Department('d', 'D', (
        Tenant(name+'-business', 'B', (), ()),))], browser_business_id=name+'-business')


def test_multiple_accounts_environments_and_summary_take_one_http_request(tmp_path):
    runtime = make_runtime(tmp_path)
    context(runtime, 'dev', 'alice')
    context(runtime, 'test', 'bob')
    requests = []
    def respond(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert payload['username'] == 'alice'
        assert request.headers['businessid'] == 'dev-business'
        assert [(item['username'], item['business_id']) for item in payload['environments']] == [
            ('alice', 'dev-business'), ('bob', 'test-business')]
        assert 'cookie' not in request.content.decode() and 'csrf' not in request.content.decode()
        return httpx.Response(200, json={'username': 'alice', 'has_access': True,
            'environments': [{**item, 'result': {'allowed': True, 'username': item['username'],
                'environment': item['environment']}} for item in reversed(payload['environments'])]})
    client = httpx.Client(transport=httpx.MockTransport(respond))
    with patch('wiserec_cli.env_access.httpx.Client', return_value=client), \
         patch('wiserec_cli.access_guidance.check_user_access') as summary:
        assert environment_statuses(runtime) == {'dev': '已开通', 'test': '已开通'}
    assert len(requests) == 1
    assert str(requests[0].url).endswith('/cli-permission/api/v1/access/environments')
    summary.assert_not_called()


def test_no_identity_and_no_eligible_environments_do_not_query(tmp_path):
    runtime = make_runtime(tmp_path)
    with patch('wiserec_cli.env_access.httpx.Client') as client:
        assert environment_statuses(runtime) == {'dev': '未登录', 'test': '未登录'}
        client.assert_not_called()


def test_summary_only_still_prompts_to_apply(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    with patch('wiserec_cli.env_access.query_environment_access', return_value={
        'username': 'alice', 'has_access': False, 'environments': []}) as query, \
         patch('wiserec_cli.env_access.console.print') as output:
        assert environment_statuses(runtime)['dev'] == '未选择业务'
    query.assert_called_once_with(runtime.config.access_control, 'alice', [], None)
    assert 'https://access.example.com/apply' in output.call_args.args[0]


def test_batch_unavailable_reports_failure_without_serial_fallback(tmp_path):
    runtime = make_runtime(tmp_path)
    context(runtime, 'dev', 'alice')
    requests = []
    def respond(request):
        requests.append(request)
        return httpx.Response(404)
    with patch('wiserec_cli.env_access.httpx.Client', return_value=httpx.Client(
        transport=httpx.MockTransport(respond))), patch('wiserec_cli.env_access.console.print') as output:
        assert environment_statuses(runtime)['dev'] == '查询失败'
    assert len(requests) == 1
    assert '更新权限服务' in output.call_args.args[0]
    assert '/apply' not in output.call_args.args[0]


@pytest.mark.parametrize('bad', ['missing', 'duplicate', 'username', 'business', 'decision', 'summary'])
def test_rejects_mixed_or_incomplete_batch_responses(bad):
    check = {'environment': 'dev', 'username': 'alice', 'platform_origin': 'https://dev.example.com', 'business_id': 'b'}
    item = {**check, 'result': {'allowed': True, 'username': 'alice', 'environment': 'dev'}}
    response = {'username': 'alice', 'has_access': True, 'environments': [item]}
    if bad == 'missing': response['environments'] = []
    if bad == 'duplicate': response['environments'].append(item)
    if bad == 'username': item['username'] = 'bob'
    if bad == 'business': item['business_id'] = 'other'
    if bad == 'decision': item['result']['username'] = 'bob'
    if bad == 'summary': response['has_access'] = 'true'
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=response)))
    with patch('wiserec_cli.env_access.httpx.Client', return_value=client), pytest.raises(MlError):
        query_environment_access({'url': 'https://access.example.com'}, 'alice', [check], 'b')


def test_version_restriction_is_reported_per_environment(tmp_path):
    runtime = make_runtime(tmp_path)
    context(runtime, 'dev', 'alice')
    context(runtime, 'test', 'alice')
    def respond(settings, username, checks, business_id):
        return {'username': username, 'has_access': True, 'environments': [
            {**item, 'result': {'allowed': False, 'reason': 'CLI_VERSION_TOO_OLD'} if item['environment'] == 'dev'
             else {'allowed': True, 'username': item['username'], 'environment': item['environment']}}
            for item in checks]}
    with patch('wiserec_cli.env_access.query_environment_access', side_effect=respond):
        assert environment_statuses(runtime) == {'dev': 'CLI版本受限', 'test': '已开通'}
