"""Environment permission status uses each profile's own identity and business selection."""
import json
from unittest.mock import patch

from wiserec_cli.access import AccessDeniedError
from wiserec_cli.business import Department, Tenant
from wiserec_cli.commands.env import list_environments
from wiserec_cli.errors import MlError
from wiserec_cli.models import Credentials
from wiserec_cli.runtime import Runtime


def make_runtime(tmp_path, access_control=None):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({
        "current": "dev",
        "access_control": access_control if access_control is not None else {"url": "https://access.example.com"},
        "profiles": [
            {"name": "dev", "api_endpoint": "https://dev.example.com/dashboard"},
            {"name": "test", "api_endpoint": "https://test.example.com/dashboard"},
        ],
    }))
    return Runtime(config_path=config, credential_path=tmp_path / "credentials.json",
                   business_path=tmp_path / "business.json")


def grants(runtime):
    return [{'environment': p.name, 'platform_origin': p.base_url} for p in runtime.config.profiles()]


def response(runtime, allowed=True):
    return {'username': 'alice', 'has_access': allowed, 'environments': [],
            'authorizations': grants(runtime) if allowed else []}


def test_four_statuses_and_current_account_only(tmp_path):
    from wiserec_cli.env_access import environment_statuses
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    runtime.business.refresh('dev', 'alice', [Department('d', 'D', (
        Tenant('dev-business', 'B', (), ()),))], browser_business_id='dev-business')
    with patch('wiserec_cli.env_access.query_environment_access', return_value=response(runtime)) as query:
        assert environment_statuses(runtime) == {'dev': '登录使用中', 'test': '已授权'}
        assert query.call_args.args[3] == 'dev-business'
        runtime.credentials.save(Credentials.create('test', 'cookie', 'csrf', 'alice', -10))
        assert environment_statuses(runtime)['test'] == '登录已过期'
        runtime.credentials.save(Credentials.create('test', 'cookie', 'csrf', 'bob', 600))
        assert environment_statuses(runtime)['test'] == '已授权'
        assert all(c['username'] == 'alice' for c in query.call_args.args[2])
    result = response(runtime)
    result['authorizations'] = result['authorizations'][:1]
    with patch('wiserec_cli.env_access.query_environment_access', return_value=result):
        assert environment_statuses(runtime)['test'] == '未授权'


def test_no_authorization_prints_error_without_table(tmp_path, capsys):
    import typer
    import pytest
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    with patch('wiserec_cli.commands.env.runtime_from_context', return_value=runtime), \
         patch('wiserec_cli.commands.env.print_result') as table, \
         patch('wiserec_cli.env_access.query_environment_access', return_value=response(runtime, False)), \
         pytest.raises(typer.Exit):
        list_environments(None)
    table.assert_not_called()
    assert 'https://access.example.com/apply' in capsys.readouterr().err


def test_columns_alias_and_highlight(tmp_path):
    runtime = make_runtime(tmp_path)
    data = json.loads(runtime.config.path.read_text())
    data['profiles'][0]['alias'] = '开发环境'
    runtime.config.path.write_text(json.dumps(data))
    runtime = Runtime(config_path=runtime.config.path, credential_path=runtime.credentials.path,
                      business_path=runtime.business.path)
    with patch('wiserec_cli.commands.env.runtime_from_context', return_value=runtime), \
         patch('wiserec_cli.commands.env.environment_statuses', return_value={'dev': '已授权', 'test': '未授权'}), \
         patch('wiserec_cli.commands.env.print_result') as output:
        list_environments(None)
    rows = output.call_args.args[0]
    assert list(rows[0]) == ['当前在用环境', '环境标识', '环境名', '管理台地址', '状态']
    assert rows[0]['环境标识'] == 'dev'
    assert rows[0]['环境名'] == '开发环境'
    assert output.call_args.kwargs['row_style'](rows[0]) == 'bold green'


def test_configuration_and_identity_errors_do_not_query(tmp_path):
    import pytest
    from wiserec_cli.env_access import environment_statuses
    for settings in ({'enable': False}, {'url': ''}, {'url': 'https://access.example.com'}):
        runtime = make_runtime(tmp_path, settings)
        with patch('wiserec_cli.env_access.query_environment_access') as query, pytest.raises(MlError):
            environment_statuses(runtime)
        query.assert_not_called()


def test_missing_business_or_tampered_selection_never_sent(tmp_path):
    from wiserec_cli.env_access import environment_statuses
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    with patch('wiserec_cli.env_access.query_environment_access', return_value=response(runtime)) as query:
        assert environment_statuses(runtime)['dev'] == '已授权'
        assert query.call_args.args[2:] == ([], None)


def test_tampered_business_is_not_sent(tmp_path):
    from wiserec_cli.env_access import environment_statuses
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    runtime.business.refresh('dev', 'alice', [Department('d', 'D', (
        Tenant('dev-business', 'B', (), ()),))], browser_business_id='dev-business')
    data = json.loads(runtime.business.path.read_text())
    data['profiles']['dev']['selected']['businessId'] = 'wrong-business'
    runtime.business.path.write_text(json.dumps(data))
    with patch('wiserec_cli.env_access.query_environment_access', return_value=response(runtime)) as query:
        assert environment_statuses(runtime)['dev'] == '已授权'
        assert query.call_args.args[2:] == ([], None)


def test_expired_login_without_authorization_is_unauthorized(tmp_path):
    from wiserec_cli.env_access import environment_statuses
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', -10))
    result = response(runtime)
    result['authorizations'] = result['authorizations'][1:]
    with patch('wiserec_cli.env_access.query_environment_access', return_value=result):
        assert environment_statuses(runtime) == {'dev': '未授权', 'test': '已授权'}


def test_old_service_or_malformed_authorizations_fail_explicitly(tmp_path):
    import pytest
    from wiserec_cli.env_access import environment_statuses
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create('dev', 'cookie', 'csrf', 'alice', 600))
    for value in (None, 'invalid', [{}], [grants(runtime)[0]] * 2):
        result = response(runtime)
        result['authorizations'] = value
        with patch('wiserec_cli.env_access.query_environment_access', return_value=result), pytest.raises(MlError):
            environment_statuses(runtime)
