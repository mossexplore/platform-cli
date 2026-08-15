import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from wisemlops_cli.business import BusinessStore, parse_business_list
from wisemlops_cli.cli import app
from wisemlops_cli.commands.business import console as business_console
from wisemlops_cli.credentials import CredentialStore
from wisemlops_cli.models import Credentials


class BusinessCommandTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config_path = self.root / "config.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "current": "dev",
                    "profiles": [
                        {
                            "name": "dev",
                            "api_endpoint": "https://dev.example.com/dashboard",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        CredentialStore(self.root / "credentials.json").save(
            Credentials.create(
                profile="dev",
                cookie="session=abc",
                csrftoken="csrf",
                username="jack",
                ttl_seconds=1800,
            )
        )
        self.business_store = BusinessStore(self.root / "business.json")
        self.business_store.refresh(
            "dev",
            "jack",
            parse_business_list(
                [
                    {
                        "cn": "测试MEP平台",
                        "value": "mep",
                        "settleTenant": "cloud",
                        "settleTenantName": json.dumps({"cn": "云平台部"}),
                        "teamList": [
                            {
                                "teamId": "available-team",
                                "businessId": "mep",
                                "cn": "可用团队",
                                "key": "mep-available-team",
                                "teamStatus": "available",
                            },
                            {
                                "teamId": "disabled-team",
                                "businessId": "mep",
                                "cn": "禁用团队",
                                "key": "mep-disabled-team",
                                "teamStatus": "disabled",
                            },
                        ],
                    }
                ]
            ),
            browser_business_id="mep",
        )
        self.runner = CliRunner()

    def tearDown(self):
        self.temporary.cleanup()

    def invoke(self, arguments, input_value=None):
        with patch(
            "wisemlops_cli.credentials.user_config_dir",
            return_value=self.root,
        ), patch(
            "wisemlops_cli.business.user_config_dir",
            return_value=self.root,
        ):
            return self.runner.invoke(
                app,
                ["--config", str(self.config_path), *arguments],
                input=input_value,
            )

    def test_uses_available_team_by_id(self):
        result = self.invoke(
            [
                "business",
                "use",
                "--tenant",
                "mep",
                "--team",
                "available-team",
            ]
        )

        self.assertEqual(result.exit_code, 0, result.output)
        for field in (
            "type（选择维度）",
            "department（部门）",
            "tenant（租户）",
            "team（团队）",
            "businessId",
        ):
            self.assertIn(field, result.output)
        for internal_field in ("department_id", "tenant_id", "team_id"):
            self.assertNotIn(internal_field, result.output)
        self.assertEqual(
            self.business_store.require_selection("dev", "jack").team_id,
            "available-team",
        )
        self.assertEqual(
            CredentialStore(self.root / "credentials.json")
            .load("dev")
            .business_id,
            "mep",
        )

    def test_tenant_selection_prints_only_five_important_fields(self):
        result = self.invoke(["business", "use", "--tenant", "mep"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("type（选择维度）", result.output)
        self.assertIn("tenant", result.output)
        self.assertIn("team（团队）", result.output)
        self.assertIn("-", result.output)
        self.assertNotIn("department_id", result.output)
        self.assertNotIn("tenant_id", result.output)
        self.assertNotIn("team_id", result.output)
        selection = self.business_store.require_selection("dev", "jack")
        self.assertEqual(selection.type, "tenant")
        self.assertEqual(selection.business_id, "mep")

    def test_interactive_selection_reaches_team(self):
        result = self.invoke(
            ["business", "use"], input_value="1\n1\n2\n"
        )

        self.assertEqual(result.exit_code, 0, result.output)
        department_line = next(
            line
            for line in result.output.splitlines()
            if "云平台部" in line
        )
        self.assertEqual(department_line.strip(), "1. 云平台部")
        tenant_line = next(
            line
            for line in result.output.splitlines()
            if "测试MEP平台" in line and "租户级" not in line
        )
        self.assertEqual(tenant_line.strip(), "1. 测试MEP平台")
        self.assertIn("请选择团队：", result.output)
        self.assertNotIn("请选择操作范围：", result.output)
        self.assertIn("可用团队", result.output)
        self.assertEqual(
            self.business_store.require_selection("dev", "jack").team_id,
            "available-team",
        )

    def test_interactive_selection_displays_disabled_team_in_red(self):
        with patch(
            "wisemlops_cli.commands.business.console.print",
            wraps=business_console.print,
        ) as print_mock:
            result = self.invoke(
                ["business", "use"], input_value="1\n1\n1\n"
            )

        self.assertEqual(result.exit_code, 0, result.output)
        disabled_call = next(
            call
            for call in print_mock.call_args_list
            if call.args and "禁用团队" in str(call.args[0])
        )
        self.assertIn("禁用团队（禁选）", disabled_call.args[0])
        self.assertNotIn("disabled-team", disabled_call.args[0])
        self.assertNotIn("disabled", disabled_call.args[0])
        self.assertEqual(disabled_call.kwargs.get("style"), "red")

        available_call = next(
            call
            for call in print_mock.call_args_list
            if call.args and "可用团队" in str(call.args[0])
        )
        self.assertEqual(available_call.args[0].strip(), "2. 可用团队")
        self.assertIsNone(available_call.kwargs.get("style"))

        tenant_call = next(
            call
            for call in print_mock.call_args_list
            if call.args and "租户级" in str(call.args[0])
        )
        self.assertEqual(tenant_call.kwargs.get("style"), "bold blue")

    def test_disabled_team_is_rejected(self):
        result = self.invoke(
            [
                "business",
                "use",
                "--tenant",
                "mep",
                "--team",
                "disabled-team",
            ]
        )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("不可选择", result.output)

    def test_department_only_is_rejected(self):
        result = self.invoke(
            ["business", "use", "--department", "cloud"]
        )

        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn("不能仅选择部门或团队", result.output)

    def test_list_displays_disabled_team(self):
        result = self.invoke(["business", "list"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("禁用团队", result.output)
        self.assertIn("禁选: disabled", result.output)


if __name__ == "__main__":
    unittest.main()
