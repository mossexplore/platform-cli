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
    with patch("wiserec_cli.commands.env.runtime_from_context", return_value=runtime), \
         patch("wiserec_cli.commands.env.print_result", side_effect=lambda rows, **_: output.append(rows)), \
         patch("wiserec_cli.commands.env.check_access", side_effect=decision) as check:
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
    assert list(rows[0]) == ["current", "name", "api_endpoint", "access_status", "output_format", "verify_ssl"]
    assert [row["access_status"] for row in rows] == ["已开通", "已开通"]
    assert [(call.args[1].name, call.args[3].business_id) for call in check.call_args_list] == [
        ("dev", "dev-business"), ("test", "test-business")]
    assert all(call.kwargs["command"] == "ml env list" for call in check.call_args_list)


def test_missing_local_context_does_not_check_or_switch_environment(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create("dev", "cookie", "csrf", "alice", 600))
    rows, check = capture_rows(runtime)
    assert [row["access_status"] for row in rows] == ["未选择业务", "未登录"]
    assert runtime.config.current_name == "dev"
    check.assert_not_called()


def test_explicit_disable_and_missing_url_never_send_checks(tmp_path):
    for settings, expected in (({"enable": False}, "校验已关闭"), ({"url": ""}, "地址未配置")):
        runtime = make_runtime(tmp_path, settings)
        rows, check = capture_rows(runtime)
        assert [row["access_status"] for row in rows] == [expected, expected]
        check.assert_not_called()


def test_denial_is_distinct_from_network_failure(tmp_path):
    runtime = make_runtime(tmp_path)
    runtime.credentials.save(Credentials.create("dev", "cookie", "csrf", "alice", 600))
    runtime.business.refresh("dev", "alice", [Department("d", "D", (
        Tenant("dev-business", "B", (), ()),
    ))], browser_business_id="dev-business")
    rows, check = capture_rows(runtime, AccessDeniedError("NOT_GRANTED", "not granted"))
    assert [row["access_status"] for row in rows] == ["未开通", "未登录"]
    assert check.call_count == 1
    rows, _ = capture_rows(runtime, MlError("connection failed"))
    assert [row["access_status"] for row in rows] == ["查询失败", "未登录"]


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
    assert rows[0]["access_status"] == "业务信息异常"
    check.assert_not_called()
