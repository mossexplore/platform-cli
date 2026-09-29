"""认证状态应反映当前业务选择及可读的剩余时间。"""

from dataclasses import replace
from unittest.mock import patch

from wiserec_cli.business import parse_business_list
from wiserec_cli.commands import auth
from wiserec_cli.models import Credentials

from test_runtime import RuntimeBusinessContextTest


def test_auth_status_uses_current_selection_and_minutes():
    fixture = RuntimeBusinessContextTest()
    fixture.setUp()
    try:
        credentials = fixture.runtime.auth.status()
        fixture.runtime.credentials.save(replace(credentials, business_id="old-tenant"))
        fixture.store.refresh("dev", "jack", parse_business_list([
            {"cn": "旧租户", "value": "old-tenant", "settleTenant": "cloud",
             "settleTenantName": '{"cn":"云平台部"}', "teamList": []},
            {"cn": "新租户", "value": "new-tenant", "settleTenant": "cloud",
             "settleTenantName": '{"cn":"云平台部"}', "teamList": []},
        ]))
        fixture.store.select("dev", "jack", tenant_id="new-tenant")
        with patch.object(auth, "runtime_from_context", return_value=fixture.runtime), \
             patch.object(auth, "print_result") as printed:
            auth.status(None)
        shown = printed.call_args.args[0]
        assert shown["businessId"] == "new-tenant"
        assert "business_id" not in shown
        assert "remaining_seconds" not in shown
        assert isinstance(shown["remaining_minutes"], int)
        assert shown["remaining_minutes"] > 0
        assert shown["timezone"] == "Asia/Shanghai"
        assert "T" not in shown["expires_at"]
    finally:
        fixture.tearDown()


def test_auth_status_without_selection_displays_dash():
    fixture = RuntimeBusinessContextTest()
    fixture.setUp()
    try:
        with patch.object(auth, "runtime_from_context", return_value=fixture.runtime), \
             patch.object(auth, "print_result") as printed:
            auth.status(None)
        assert printed.call_args.args[0]["businessId"] == "-"
    finally:
        fixture.tearDown()


def test_auth_status_shows_one_minute_while_still_valid():
    fixture = RuntimeBusinessContextTest()
    fixture.setUp()
    try:
        fixture.runtime.credentials.save(
            Credentials("dev", "cookie", "csrf", "jack", 1_700_000_000, 1_700_000_001)
        )
        with patch.object(auth, "runtime_from_context", return_value=fixture.runtime), \
             patch.object(auth, "print_result") as printed, \
             patch.object(auth.time, "time", return_value=1_700_000_000.5):
            auth.status(None)
        shown = printed.call_args.args[0]
        assert shown["status"] == "valid"
        assert shown["remaining_minutes"] == 1
    finally:
        fixture.tearDown()
