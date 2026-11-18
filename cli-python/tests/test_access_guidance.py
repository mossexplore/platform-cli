"""用户授权提示的真实 HTTP 序列化与命令调用路径。"""
from unittest.mock import patch

import httpx
import pytest

from test_env_status import make_runtime
from wiserec_cli.access_guidance import check_user_access, show_access_guidance
from wiserec_cli.commands.auth import login
from wiserec_cli.commands.env import list_environments, show_environment, use_environment
from wiserec_cli.errors import MlError
from wiserec_cli.models import Credentials
from wiserec_cli.business import Department, Tenant


def transport(result, status=200, captured=None):
    def handle(request):
        if captured is not None:
            captured.append(request)
        return httpx.Response(status, json=result)
    return httpx.Client(transport=httpx.MockTransport(handle))


@pytest.mark.parametrize('has_access', [True, False])
def test_query_serializes_identity_and_uses_configured_url(has_access):
    captured = []
    client = transport({'username': 'alice', 'has_access': has_access}, captured=captured)
    with patch('wiserec_cli.access_guidance.httpx.Client', return_value=client) as factory:
        assert check_user_access({'url': 'https://permissions.example.com/cli-permission/'},
                                 'alice', 'dev-business') is has_access
    request = captured[0]
    assert str(request.url) == 'https://permissions.example.com/cli-permission/api/v1/access/summary'
    assert request.headers['businessid'] == 'dev-business'
    assert request.read() == b'{"username":"alice"}'
    assert factory.call_args.kwargs['trust_env'] is False


@pytest.mark.parametrize('result,status', [({}, 200), ({'username': 'bob', 'has_access': True}, 200),
    ({'username': 'alice', 'has_access': 'false'}, 200), ({}, 404), ({}, 503)])
def test_failed_query_does_not_claim_user_has_no_access(result, status):
    with patch('wiserec_cli.access_guidance.httpx.Client', return_value=transport(result, status)):
        with pytest.raises(MlError):
            check_user_access({'url': 'https://permissions.example.com'}, 'alice')


def test_guidance_uses_current_business_and_exact_application_message(tmp_path):
    runtime = make_runtime(tmp_path)
    credentials = Credentials.create('dev', 'cookie', 'csrf', 'alice', 600)
    runtime.credentials.save(credentials)
    runtime.business.refresh('dev', 'alice', [Department('d', 'D', (
        Tenant('dev-business', 'B', (), ()),))], browser_business_id='dev-business')
    with patch('wiserec_cli.access_guidance.check_user_access', return_value=False) as query, \
         patch('wiserec_cli.access_guidance.msg.info') as output:
        assert show_access_guidance(runtime) is False
    assert query.call_args.args == (runtime.config.access_control, 'alice', 'dev-business')
    output.assert_called_once_with(
        '请打开https://access.example.com/apply进行CLI权限申请（若地址无法打开，将*.hwcloudtest.cn加入代理排除），权限通过后方可执行CLI命令',
        )


def test_guidance_does_not_use_another_environments_account(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('test', 'cookie', 'csrf', 'bob', 600))
    with patch('wiserec_cli.access_guidance.check_user_access') as query:
        assert show_access_guidance(runtime) is False
        query.assert_not_called()


def test_valid_access_without_business_selection(tmp_path):
    runtime = make_runtime(tmp_path)
    credentials = Credentials.create('dev', 'cookie', 'csrf', 'alice', 600)
    with patch('wiserec_cli.access_guidance.check_user_access', return_value=True) as query:
        assert show_access_guidance(runtime, credentials) is True
    assert query.call_args.args[-1] is None


@pytest.mark.parametrize('command', [show_environment, use_environment])
def test_all_environment_commands_query_user_access(tmp_path, command):
    runtime = make_runtime(tmp_path)
    with patch('wiserec_cli.commands.env.runtime_from_context', return_value=runtime), \
         patch('wiserec_cli.commands.env.show_access_guidance', return_value=False) as guidance, \
         patch('wiserec_cli.commands.env.ping.auto_start') as ping:
        command(None, 'dev') if command is use_environment else command(None)
    guidance.assert_called_once_with(runtime)
    ping.assert_not_called()


@pytest.mark.parametrize('has_access', [True, False])
def test_login_queries_returned_identity_before_auto_ping(tmp_path, has_access):
    runtime = make_runtime(tmp_path)
    credentials = Credentials.create('dev', 'cookie', 'csrf', 'alice', 600)
    with patch('wiserec_cli.commands.auth.runtime_from_context', return_value=runtime), \
         patch.object(runtime.auth, 'login', return_value=credentials), \
         patch('wiserec_cli.commands.auth.show_access_guidance', return_value=has_access) as guidance, \
         patch('wiserec_cli.commands.auth.ping.auto_start') as ping:
        login(None, False)
    guidance.assert_called_once_with(runtime, credentials)
    assert ping.call_count == int(has_access)


def test_network_failure_is_not_an_application_prompt():
    with patch('wiserec_cli.access_guidance.httpx.Client', side_effect=httpx.ConnectError('offline')):
        with pytest.raises(MlError, match='无法查询用户授权'):
            check_user_access({'url': 'https://permissions.example.com'}, 'alice')


def test_disabled_access_never_queries_or_prompts(tmp_path):
    runtime = make_runtime(tmp_path, {'enable': False})
    with patch('wiserec_cli.access_guidance.check_user_access') as query:
        assert show_access_guidance(runtime) is True
        query.assert_not_called()


def test_catalog_without_selected_business_still_queries(tmp_path):
    runtime = make_runtime(tmp_path)
    credentials = Credentials.create('dev', 'cookie', 'csrf', 'alice', 600)
    runtime.business.refresh('dev', 'alice', [Department('d', 'D', (
        Tenant('one', 'One', (), ()), Tenant('two', 'Two', (), ()),))])
    with patch('wiserec_cli.access_guidance.check_user_access', return_value=True) as query:
        assert show_access_guidance(runtime, credentials) is True
    assert query.call_args.args[-1] is None


def test_old_accounts_business_does_not_block_new_accounts_query(tmp_path):
    runtime = make_runtime(tmp_path)
    credentials = Credentials.create('dev', 'cookie', 'csrf', 'new-user', 600)
    runtime.business.refresh('dev', 'old-user', [Department('d', 'D', (
        Tenant('old-business', 'B', (), ()),))], browser_business_id='old-business')
    with patch('wiserec_cli.access_guidance.check_user_access', return_value=False) as query:
        assert show_access_guidance(runtime, credentials) is False
    assert query.call_args.args[1:] == ('new-user', None)
