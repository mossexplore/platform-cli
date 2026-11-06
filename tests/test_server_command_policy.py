"""服务端拒绝独立于本地策略；离线快照不会用于执行放行。"""
import json
from types import SimpleNamespace
from unittest.mock import patch
import httpx
import pytest
from wiserec_cli.models import Profile
from wiserec_cli.access import check_access
from wiserec_cli.access import AccessDeniedError
from wiserec_cli.server_command_policy import remember, load


def test_server_denial_without_local_command_policy(tmp_path):
    profile = Profile('prod', 'https://platform.example.com')
    settings = dict(enable=True, url='https://access.example/cli-permission')
    result = {'allowed': False, 'reason': 'COMMAND_DISABLED', 'username': 'alice', 'environment': 'prod',
              'command_policy': {'environment': 'prod', 'platform_origin': profile.base_url,
                                 'revision': 1, 'deny': ['ml jupyter files upload']}}
    def handler(request):
        assert json.loads(request.content)['command'] == 'ml jupyter files upload'
        return httpx.Response(200, json=result)
    with patch('wiserec_cli.access.create_client', side_effect=lambda **kw: httpx.Client(transport=httpx.MockTransport(handler))), \
         patch('wiserec_cli.server_command_policy.user_config_dir', return_value=tmp_path):
        with pytest.raises(AccessDeniedError, match='已由管理员禁止执行'):
            check_access(settings, profile, SimpleNamespace(username='alice'), SimpleNamespace(business_id='b'),
                         command='ml jupyter files upload')
        assert load(settings, profile)['deny'] == ['ml jupyter files upload']
        assert load(settings, Profile('other', profile.api_endpoint)) is None
        assert load(dict(settings, url='https://different.example'), profile) is None


def test_snapshot_identity_validation_and_cached_policy_not_execution_gate(tmp_path):
    from wiserec_cli.command_policy import require_command
    profile = Profile('prod', 'https://platform.example.com')
    with patch('wiserec_cli.server_command_policy.user_config_dir', return_value=tmp_path):
        remember({}, profile, {'command_policy': {'environment': 'wrong', 'revision': 1, 'deny': []}})
        assert load({}, profile) is None
        remember({}, profile, {'command_policy': {'environment': 'prod', 'platform_origin': profile.base_url,
                  'revision': 5, 'deny': ['ml jupyter files upload']}})
        assert load({}, profile)['revision'] == 5
        # 展示缓存不能替代实时鉴权，解除禁令后不能被旧快照永久拦截。
        require_command(profile, 'jupyter files upload')


def test_tree_displays_cached_server_policy_without_login(tmp_path):
    from pathlib import Path
    from typer.testing import CliRunner
    from wiserec_cli.cli import app
    from wiserec_cli.config import ConfigManager
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'prod', 'access_control': {'url': 'https://access.example'},
          'profiles': [{'name': 'prod', 'api_endpoint': 'https://platform.example.com'}]}))
    manager = ConfigManager(config)
    with patch('wiserec_cli.server_command_policy.user_config_dir', return_value=tmp_path):
        remember(manager.access_control, manager.current_profile(), {'command_policy': {
            'environment': 'prod', 'platform_origin': 'https://platform.example.com', 'revision': 1,
            'deny': ['ml jupyter files upload']}})
        with patch('wiserec_cli.auth.AuthManager.ensure_credentials', side_effect=AssertionError('must not login')):
            result = CliRunner().invoke(app, ['--config', str(config), 'tree', '--all'])
        assert result.exit_code == 0, result.output
        assert '[当前环境禁用]' in result.output


def test_business_gateway_denial_is_not_authentication_expiry():
    import test_client
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(403, json={'allowed': False, 'reason': 'COMMAND_DISABLED'})
    with test_client.PlatformClientTest().create_client(handler) as client:
        with pytest.raises(AccessDeniedError, match='网关拒绝命令'):
            client.request('GET', '/protected')
    assert len(calls) == 1
