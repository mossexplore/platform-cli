import json
import tempfile
import unittest
from pathlib import Path

from wisemlops_cli.business import BusinessStore, parse_business_list
from wisemlops_cli.errors import BusinessError


def business_list(team_status="available"):
    return [
        {
            "cn": "测试MEP平台",
            "en": "mep",
            "value": "mep",
            "settleTenant": "WiseCloudBigData",
            "settleTenantName": json.dumps(
                {"en": "WiseCloud&BigData Platform", "cn": "云平台部"}
            ),
            "serviceIdList": [
                {"serviceId": "com.ab.wisemlopsmepservice"}
            ],
            "teamList": [
                {
                    "businessId": "mep",
                    "teamId": "asdasd",
                    "name": json.dumps(
                        {"en": "sadasda(asdasd)", "cn": "asdasda"}
                    ),
                    "cn": "asdasda",
                    "key": "mep-asdasd",
                    "teamStatus": team_status,
                },
                {
                    "businessId": "mep",
                    "teamId": "blocked",
                    "cn": "禁用团队",
                    "key": "mep-blocked",
                    "teamStatus": "disabled",
                },
            ],
        },
        {
            "cn": "另一个服务",
            "value": "other",
            "settleTenant": "WiseCloudBigData",
            "settleTenantName": json.dumps({"cn": "云平台部"}),
            "teamList": [],
        },
    ]


class BusinessStoreTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = BusinessStore(
            Path(self.temporary.name) / "business.json"
        )
        self.catalog = parse_business_list(json.dumps(business_list()))

    def tearDown(self):
        self.temporary.cleanup()

    def test_parses_and_groups_three_level_catalog(self):
        self.assertEqual(len(self.catalog), 1)
        department = self.catalog[0]
        self.assertEqual(department.name, "云平台部")
        self.assertEqual([item.id for item in department.tenants], ["mep", "other"])
        tenant = department.tenants[0]
        self.assertEqual(tenant.service_ids, ("com.ab.wisemlopsmepservice",))
        self.assertEqual(tenant.teams[0].name, "asdasda")
        self.assertTrue(tenant.teams[0].selectable)
        self.assertFalse(tenant.teams[1].selectable)

    def test_department_name_falls_back_to_top_level_cn(self):
        catalog = parse_business_list(
            [
                {
                    "cn": "顶层中文名称",
                    "value": "service-a",
                    "settleTenant": "department-a",
                    "settleTenantName": json.dumps({"cn": "", "en": ""}),
                    "teamList": [],
                }
            ]
        )

        self.assertEqual(catalog[0].name, "顶层中文名称")

    def test_department_name_does_not_fall_back_to_settle_tenant(self):
        with self.assertRaisesRegex(BusinessError, "没有有效的租户信息"):
            parse_business_list(
                [
                    {
                        "cn": "",
                        "value": "service-a",
                        "settleTenant": "department-a",
                        "settleTenantName": json.dumps(
                            {"cn": "", "en": ""}
                        ),
                        "teamList": [],
                    }
                ]
            )

    def test_department_grouping_does_not_use_settle_tenant(self):
        catalog = parse_business_list(
            [
                {
                    "cn": "服务A",
                    "value": "service-a",
                    "settleTenant": "same-value",
                    "settleTenantName": json.dumps({"cn": "部门A"}),
                    "teamList": [],
                },
                {
                    "cn": "服务B",
                    "value": "service-b",
                    "settleTenant": "same-value",
                    "settleTenantName": json.dumps({"cn": "部门B"}),
                    "teamList": [],
                },
                {
                    "cn": "服务C",
                    "value": "service-c",
                    "settleTenantName": json.dumps({"cn": "部门C"}),
                    "teamList": [],
                },
            ]
        )

        self.assertEqual(
            [(item.id, item.name) for item in catalog],
            [("部门A", "部门A"), ("部门B", "部门B"), ("部门C", "部门C")],
        )

    def test_refresh_uses_browser_tenant_and_can_select_team(self):
        selection = self.store.refresh(
            "dev", "jack", self.catalog, browser_business_id="mep"
        )
        self.assertEqual(selection.type, "tenant")
        selected_team = self.store.select(
            "dev", "jack", tenant_id="mep", team_id="asdasd"
        )
        self.assertEqual(selected_team.type, "team")
        self.assertEqual(selected_team.business_id, "mep")
        stored = json.loads(self.store.path.read_text(encoding="utf-8"))
        self.assertNotIn(
            "effective_business_id", stored["profiles"]["dev"]["selected"]
        )
        self.assertEqual(
            stored["profiles"]["dev"]["selected"]["businessId"], "mep"
        )
        self.assertNotIn("effective_business_id", json.dumps(stored))
        self.assertNotIn('"business_id"', json.dumps(stored))

    def test_incompatible_file_is_rejected_and_refresh_rebuilds_it(self):
        self.store.path.write_text(
            json.dumps(
                {
                    "version": 1,
                    "profiles": {
                        "dev": {
                            "selected": {
                                "effective_business_id": "mep-asdasd"
                            }
                        }
                    },
                }
            ),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(BusinessError, "版本不兼容"):
            self.store.catalog("dev", "jack")
        self.assertEqual(self.store.updated_at("dev"), 0)
        self.assertIn(
            "effective_business_id",
            self.store.path.read_text(encoding="utf-8"),
        )

        self.store.refresh("dev", "jack", self.catalog, "mep")
        rebuilt = self.store.path.read_text(encoding="utf-8")
        self.assertNotIn("effective_business_id", rebuilt)
        self.assertIn('"businessId": "mep"', rebuilt)

    def test_unavailable_team_cannot_be_selected(self):
        self.store.refresh("dev", "jack", self.catalog)
        with self.assertRaisesRegex(BusinessError, "不可选择"):
            self.store.select(
                "dev", "jack", tenant_id="mep", team_id="blocked"
            )

    def test_refresh_invalidates_team_that_becomes_unavailable(self):
        self.store.refresh("dev", "jack", self.catalog)
        self.store.select("dev", "jack", tenant_id="mep", team_id="asdasd")
        changed = parse_business_list(
            json.dumps(business_list(team_status="disabled"))
        )
        self.assertIsNone(self.store.refresh("dev", "jack", changed))
        with self.assertRaisesRegex(BusinessError, "尚未选择"):
            self.store.require_selection("dev", "jack")

    def test_catalog_is_bound_to_login_account(self):
        self.store.refresh("dev", "jack", self.catalog)
        with self.assertRaisesRegex(BusinessError, "其他账号"):
            self.store.catalog("dev", "alice")

    def test_invalid_business_list_is_rejected(self):
        with self.assertRaisesRegex(BusinessError, "有效的 JSON"):
            parse_business_list("not-json")


if __name__ == "__main__":
    unittest.main()
