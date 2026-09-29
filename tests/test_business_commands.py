import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from wiserec_cli.business import BusinessStore, Department, Tenant, parse_business_list
from wiserec_cli.cli import app
from wiserec_cli.commands.business import console as business_console
from wiserec_cli.credentials import CredentialStore
from wiserec_cli.models import Credentials


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
            "wiserec_cli.credentials.user_config_dir",
            return_value=self.root,
        ), patch(
            "wiserec_cli.business.user_config_dir",
            return_value=self.root,
        ):
            return self.runner.invoke(
                app,
                ["--config", str(self.config_path), *arguments],
                input=input_value,
            )

    def add_search_departments(self):
        self.business_store.refresh("dev", "jack", (
            Department("cloud-main", "云平台部", (Tenant("mep", "测试MEP平台", (), ()),)),
            Department("algo", "算法中心", (Tenant("algorithm", "算法租户", (), ()),)),
            Department("cloud-ops", "云平台运维部", (Tenant("ops", "运维租户", (), ()),)),
        ))

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
            ["business", "use"], input_value="1\n1\n2\ny\n"
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

    def test_search_filters_department_name_and_keeps_next_steps(self):
        self.add_search_departments()
        result = self.invoke(
            ["business", "use", "--search", "运维"],
            input_value="1\n1\n1\ny\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("云平台运维部 [cloud-ops]", result.output)
        self.assertNotIn("算法中心", result.output)
        self.assertEqual(
            self.business_store.require_selection("dev", "jack").department_id,
            "cloud-ops",
        )
        self.assertEqual(
            self.business_store.require_selection("dev", "jack").tenant_id,
            "ops",
        )

    def test_search_matches_department_id_case_insensitively(self):
        self.add_search_departments()
        result = self.invoke(
            ["business", "use", "--search", " CLOUD-OPS "],
            input_value="1\n1\n1\ny\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("云平台运维部", result.output)
        self.assertNotIn("算法中心", result.output)

    def test_without_search_still_shows_all_departments(self):
        self.add_search_departments()
        result = self.invoke(["business", "use"], input_value="1\n1\n1\ny\n")

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("1. 云平台部", result.output)
        self.assertIn("2. 算法中心", result.output)
        self.assertIn("3. 云平台运维部", result.output)

    def test_back_from_tenant_and_team_changes_final_selection(self):
        self.add_search_departments()
        result = self.invoke(
            ["business", "use", "--search", "云平台"],
            input_value="1\nb\n2\n1\nb\n1\n1\ny\n",
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertGreaterEqual(result.output.count("云平台运维部 [cloud-ops]"), 2)
        self.assertNotIn("算法中心", result.output)
        selection = self.business_store.require_selection("dev", "jack")
        self.assertEqual(selection.department_id, "cloud-ops")
        self.assertEqual(selection.tenant_id, "ops")

    def test_back_from_confirmation_returns_to_team(self):
        result = self.invoke(
            ["business", "use"], input_value="1\n1\n1\nb\n2\ny\n"
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("请确认选择", result.output)
        self.assertEqual(
            self.business_store.require_selection("dev", "jack").team_id,
            "available-team",
        )

    def test_back_at_first_level_stays_on_department_list(self):
        result = self.invoke(
            ["business", "use"], input_value="b\n1\n1\n1\ny\n"
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("已经是第一级", result.output)
        self.assertEqual(result.output.count("请选择部门："), 2)

    def test_cancel_at_each_stage_keeps_previous_selection(self):
        self.business_store.select("dev", "jack", tenant_id="mep", team_id="available-team")
        original = self.business_store.selection("dev", "jack")
        original_credentials = CredentialStore(self.root / "credentials.json").load("dev")
        for answers in ("q\n", "1\nq\n", "1\n1\nq\n", "1\n1\n1\nq\n"):
            with self.subTest(answers=answers):
                result = self.invoke(["business", "use"], input_value=answers)
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertIn("已取消业务切换", result.output)
                self.assertEqual(self.business_store.selection("dev", "jack"), original)
                self.assertEqual(
                    CredentialStore(self.root / "credentials.json").load("dev"),
                    original_credentials,
                )

    def test_search_no_match_or_blank_does_not_change_selection(self):
        self.add_search_departments()
        self.business_store.select("dev", "jack", tenant_id="mep", department_id="cloud-main")
        original = self.business_store.selection("dev", "jack")
        for keyword in ("不存在的部门", "   "):
            with self.subTest(keyword=keyword):
                result = self.invoke(["business", "use", "--search", keyword])
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(self.business_store.selection("dev", "jack"), original)

    def test_search_cannot_be_combined_with_tenant_id(self):
        result = self.invoke([
            "business", "use", "--search", "云", "--tenant", "mep",
        ])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("不能与 --tenant 同时使用", result.output)

    def test_interactive_selection_displays_disabled_team_in_red(self):
        with patch(
            "wiserec_cli.commands.business.console.print",
            wraps=business_console.print,
        ) as print_mock:
            result = self.invoke(
                ["business", "use"], input_value="1\n1\n1\ny\n"
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
