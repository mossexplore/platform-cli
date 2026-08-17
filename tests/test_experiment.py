import unittest

from wisemlops_cli.commands.offline import _table_items
from wisemlops_cli.errors import ApiError, BusinessError
from wisemlops_cli.services.experiment import ExperimentService


class FakeClient:
    def __init__(self, response, business_id="default"):
        self.response = response
        self.business_id = business_id
        self.calls = []

    def request(self, method, path, json_body=None, params=None, headers=None):
        self.calls.append((method, path, json_body, params, headers))
        return self.response


class ExperimentServiceTest(unittest.TestCase):
    def successful_response(self):
        return {
            "result": {
                "code": 0,
                "des": "ok",
                "data": [
                    {
                        "projectId": "hidden-id",
                        "projectName": "test-0817",
                        "description": "测试实验",
                        "createUser": "a123456",
                        "updateUser": "a654321",
                        "createTime": "2026-08-17T10:37:56",
                        "updateTime": "2026-08-17T11:00:00",
                        "configName": "12_1",
                    }
                ],
                "count": 1,
                "total": 21,
            }
        }

    def test_list_uses_required_and_supplied_query_parameters(self):
        client = FakeClient(self.successful_response(), business_id="mep")

        result = ExperimentService(client).list_projects(
            page_index=2,
            page_size=20,
            project_name="test",
            create_user="a123",
        )

        self.assertEqual(
            client.calls,
            [
                (
                    "GET",
                    "/ai/backend/experiment/project/list",
                    None,
                    {
                        "businessId": "mep",
                        "pageIndex": 2,
                        "pageSize": 20,
                        "projectName": "test",
                        "createUser": "a123",
                    },
                    {"businessid": "mep"},
                )
            ],
        )
        self.assertEqual(result["total"], 21)
        self.assertEqual(
            list(result["items"][0]),
            [
                "projectName",
                "description",
                "createUser",
                "updateUser",
                "createTime",
                "updateTime",
                "configName",
            ],
        )
        self.assertNotIn("projectId", result["items"][0])

    def test_optional_filters_are_omitted_by_default(self):
        client = FakeClient(self.successful_response())

        ExperimentService(client).list_projects()

        self.assertEqual(
            client.calls[0][3],
            {"businessId": "default", "pageIndex": 1, "pageSize": 10},
        )

    def test_table_contains_only_the_seven_required_columns(self):
        client = FakeClient(self.successful_response())
        result = ExperimentService(client).list_projects()

        rows = _table_items(result)

        self.assertEqual(
            list(rows[0]),
            [
                "实验名称",
                "描述",
                "创建者",
                "修改者",
                "创建时间",
                "更新时间",
                "运行配置模板",
            ],
        )
        self.assertNotIn("projectId", rows[0])

    def test_requires_business_selection(self):
        client = FakeClient(self.successful_response(), business_id="")

        with self.assertRaisesRegex(BusinessError, "ml business use"):
            ExperimentService(client).list_projects()

    def test_rejects_failed_business_response(self):
        client = FakeClient(
            {"result": {"code": 1001, "des": "无权限", "data": []}}
        )

        with self.assertRaisesRegex(ApiError, "无权限"):
            ExperimentService(client).list_projects()

    def test_rejects_non_list_data(self):
        client = FakeClient({"result": {"code": 0, "data": {}}})

        with self.assertRaisesRegex(ApiError, "不是数组"):
            ExperimentService(client).list_projects()


if __name__ == "__main__":
    unittest.main()
