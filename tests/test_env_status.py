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


def capture_rows(runtime, decision=None):
    output = []
    def respond(settings, username, checks, business_id):
        if isinstance(decision, MlError) and not isinstance(decision, AccessDeniedError):
            raise decision
        return {'username': username, 'has_access': True if username else None,
                'environments': [{**item, 'result':
                    {'allowed': False, 'reason': decision.reason} if decision else
                    {'allowed': True, 'username': item['username'], 'environment': item['environment']}}
                    for item in checks]}
    with patch("wiserec_cli.commands.env.runtime_from_context", return_value=runtime), \
         patch("wiserec_cli.commands.env.print_result", side_effect=lambda rows, **_: output.append(rows)), \
         patch("wiserec_cli.env_access.query_environment_access", side_effect=respond) as check:
        list_environments(None)
    return output[0], check


def test_each_environment_checks_its_own_business_id(tmp_path):
    runtime = make_runtime(tmp_path)
    for name in ("dev", "test"):
        runtime.credentials.save(Credentials.create(name, "cookie", "csrf", "alice", 600))
        runtime.business.refresh(name, "alice", [Department("d", "D", (
            Tenant(name + "-business", "B", (), ()),
        ))], browser_business_id=name + "-business")
    rows, check = capture_rows(runtime)
    assert list(rows[0]) == ["当前在用环境", "环境标识", "管理台地址", "状态"]
    assert [row["状态"] for row in rows] == ["已开通", "已开通"]
    check.assert_called_once()
    assert [(item['environment'], item['business_id']) for item in check.call_args.args[2]] == [
        ("dev", "dev-business"), ("test", "test-business")]
    assert check.call_args.args[3] == 'dev-business'


def test_missing_local_context_does_not_check_or_switch_environment(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create("dev", "cookie", "csrf", "alice", 600))
    rows, check = capture_rows(runtime)
    assert [row["状态"] for row in rows] == ["未选择业务", "未登录"]
    assert runtime.config.current_name == "dev"
    check.assert_called_once()
    assert check.call_args.args[2] == []


def test_explicit_disable_and_missing_url_never_send_checks(tmp_path):
    for settings, expected in (({"enable": False}, "校验已关闭"), ({"url": ""}, "地址未配置")):
        runtime = make_runtime(tmp_path, settings)
        rows, check = capture_rows(runtime)
        assert [row["状态"] for row in rows] == [expected, expected]
        check.assert_not_called()


def test_denial_is_distinct_from_network_failure(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create("dev", "cookie", "csrf", "alice", 600))
    runtime.business.refresh("dev", "alice", [Department("d", "D", (
        Tenant("dev-business", "B", (), ()),
    ))], browser_business_id="dev-business")
    rows, check = capture_rows(runtime, AccessDeniedError("NOT_GRANTED", "not granted"))
    assert [row["状态"] for row in rows] == ["未开通", "未登录"]
    assert check.call_count == 1
    rows, _ = capture_rows(runtime, MlError("connection failed"))
    assert [row["状态"] for row in rows] == ["查询失败", "未登录"]


def test_tampered_selected_business_id_never_reaches_service(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create("dev", "cookie", "csrf", "alice", 600))
    runtime.business.refresh("dev", "alice", [Department("d", "D", (
        Tenant("dev-business", "B", (), ()),
    ))], browser_business_id="dev-business")
    data = json.loads(runtime.business.path.read_text())
    data["profiles"]["dev"]["selected"]["businessId"] = "wrong-business"
    runtime.business.path.write_text(json.dumps(data))
    rows, check = capture_rows(runtime)
    assert rows[0]["状态"] == "业务信息异常"
    check.assert_called_once()
    assert check.call_args.args[2] == []
    assert check.call_args.args[3] is None


def test_environment_list_displays_alias_but_matches_original_identifier(tmp_path):
    runtime = make_runtime(tmp_path)
    data = json.loads(runtime.config.path.read_text())
    data['profiles'][0]['alias'] = '开发环境'
    runtime.config.path.write_text(json.dumps(data))
    runtime = make_runtime_with_existing_config(runtime)
    rows, _ = capture_rows(runtime)
    assert rows[0]['环境标识'] == '开发环境'
    assert rows[0]['当前在用环境'] == '*'
    assert rows[1]['环境标识'] == 'test'
    runtime.config.use_profile('dev')
    assert runtime.config.current_name == 'dev'


def make_runtime_with_existing_config(runtime):
    return Runtime(config_path=runtime.config.path, credential_path=runtime.credentials.path,
                   business_path=runtime.business.path)
