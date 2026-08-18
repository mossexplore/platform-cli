import unittest

from wisemlops_cli.commands.mtp import (
    _config_items,
    _environment_item,
    _items,
    _metric_items,
)
from wisemlops_cli.errors import ApiError
from wisemlops_cli.services.swanboard import SwanBoardService


class FakeClient:
    def __init__(self, responses, business_id="default"):
        self.responses = responses if isinstance(responses, list) else [responses]
        self.business_id = business_id
        self.calls = []

    def request(self, method, path, json_body=None, params=None, headers=None):
        self.calls.append((method, path, json_body, params, headers))
        return self.responses.pop(0)


class SwanBoardServiceTest(unittest.TestCase):
    def list_response(self, data):
        return {"result": {"code": 0, "des": "success", "data": data, "count": 1}}

    def test_list_projects_uses_required_body_and_header(self):
        client = FakeClient(self.list_response([{"name": "board"}]), business_id="mep")

        result = SwanBoardService(client).list_projects(2, 20, "team", "a123")

        self.assertEqual(result["count"], 1)
        self.assertEqual(
            client.calls,
            [
                (
                    "POST",
                    "/ai/backend/mtp/swanboard/project/list",
                    {
                        "pageNum": 2,
                        "pageSize": 20,
                        "businessId": "mep",
                        "teamId": "team",
                        "creator": "a123",
                    },
                    None,
                    {"businessid": "mep"},
                )
            ],
        )

    def test_list_namespaces_uses_project_id_in_path_and_query(self):
        client = FakeClient(self.list_response([{"namespaceId": "namespace"}]))

        SwanBoardService(client).list_namespaces("project-id")

        self.assertEqual(
            client.calls[0],
            (
                "GET",
                "/ai/backend/mtp/swanboard/namespace/query/project-id",
                None,
                {"projectId": "project-id", "teamId": "", "businessId": "default"},
                {"businessid": "default"},
            ),
        )

    def test_list_experiments_reads_nested_list(self):
        client = FakeClient(
            self.list_response(
                {"list": [{"experimentId": "experiment"}], "total": 1, "pageNum": 1, "pageSize": 20, "totalPages": 1}
            )
        )

        result = SwanBoardService(client).list_experiments("project", "namespace")

        self.assertEqual(result["items"], [{"experimentId": "experiment"}])
        self.assertEqual(result["total"], 1)
        self.assertEqual(
            client.calls[0][2],
            {"projectId": "project", "teamId": "", "businessId": "default", "namespaceId": "namespace"},
        )

    def test_feature_environment_metric_and_config_requests(self):
        client = FakeClient(
            [
                self.list_response([]),
                {"result": {"code": 0, "data": {}}},
                {"result": {"code": 0, "data": {"tagName": "loss"}}},
                {"result": {"code": 0, "data": {}}},
            ]
        )
        service = SwanBoardService(client)

        service.list_features("experiment", 2, 20)
        service.get_environment("experiment")
        service.get_metric_stats("experiment", "loss")
        service.get_config("experiment")

        self.assertEqual(client.calls[0][1], "/ai/backend/mtp/swanboard/experiment/experiment/feature")
        self.assertEqual(client.calls[0][3]["pageIndex"], 2)
        self.assertEqual(client.calls[1][1], "/ai/backend/mtp/swanboard/label/experiment/experiment")
        self.assertEqual(client.calls[2][1], "/ai/backend/mtp/swanboard/tag/experiment/experiment/loss/stats")
        self.assertEqual(client.calls[3][1], "/ai/backend/mtp/swanboard/experiment/experiment/config")

    def test_rejects_failed_response(self):
        client = FakeClient({"result": {"code": 1001, "des": "无权限", "data": []}})

        with self.assertRaisesRegex(ApiError, "无权限"):
            SwanBoardService(client).list_projects()


class SwanBoardOutputTest(unittest.TestCase):
    def test_project_table_puts_project_id_before_project_name(self):
        rows = _items(
            {"items": [{"projectId": "project-id", "name": "board"}]},
            [("项目id", "projectId"), ("项目名称", "name")],
        )

        self.assertEqual(list(rows[0]), ["项目id", "项目名称"])
        self.assertEqual(rows[0]["项目id"], "project-id")

    def test_namespace_table_puts_name_after_project_id(self):
        rows = _items(
            {
                "items": [
                    {
                        "namespaceId": "namespace-id",
                        "projectId": "project-id",
                        "namespaceName": "namespace-name",
                    }
                ]
            },
            [
                ("项目空间id", "namespaceId"),
                ("实验id", "projectId"),
                ("实验名称", "namespaceName"),
            ],
        )

        self.assertEqual(list(rows[0]), ["项目空间id", "实验id", "实验名称"])
        self.assertEqual(rows[0]["实验名称"], "namespace-name")

    def test_environment_output_uses_required_fields(self):
        result = _environment_item(
            {"python": "3.9.18", "cpu": {"brand": "Intel"}, "memory": "122", "requirements": ["anyio==4.4.0", "httpx==0.27"]}
        )

        self.assertEqual(
            result,
            {"Python版本": "3.9.18", "系统硬件CPU": "Intel", "系统硬件Memory": "122", "Python库名称": "anyio==4.4.0\nhttpx==0.27"},
        )

    def test_metric_and_config_output_formats_values(self):
        self.assertEqual(
            _metric_items([{"tagName": "loss", "max": 0.657802, "min": 0.048979, "avg": 0.090533}]),
            [{"指标名称": "loss", "最大值": "0.6578", "最小值": "0.0490", "平均值": "0.0905"}],
        )
        self.assertEqual(
            _config_items({"learning_rate": {"value": 0.01}, "epochs": {"value": 50}}),
            [{"配置项": "learning_rate", "值": 0.01}, {"配置项": "epochs", "值": 50}],
        )


if __name__ == "__main__":
    unittest.main()
