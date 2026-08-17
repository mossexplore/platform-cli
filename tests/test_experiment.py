import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from wisemlops_cli.commands.offline import (
    _clone_result,
    _table_items,
    clone_experiment,
)
from wisemlops_cli.errors import ApiError, BusinessError
from wisemlops_cli.services.experiment import ExperimentService


class FakeClient:
    def __init__(
        self,
        response,
        business_id="default",
        username="b456789",
    ):
        self.responses = response if isinstance(response, list) else [response]
        self.business_id = business_id
        self.username = username
        self.calls = []

    def request(self, method, path, json_body=None, params=None, headers=None):
        self.calls.append((method, path, json_body, params, headers))
        return self.responses.pop(0)


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
                "projectId",
                "projectName",
                "description",
                "createUser",
                "updateUser",
                "createTime",
                "updateTime",
                "configName",
            ],
        )
        self.assertEqual(result["items"][0]["projectId"], "hidden-id")

    def test_optional_filters_are_omitted_by_default(self):
        client = FakeClient(self.successful_response())

        ExperimentService(client).list_projects()

        self.assertEqual(
            client.calls[0][3],
            {"businessId": "default", "pageIndex": 1, "pageSize": 10},
        )

    def test_table_displays_project_id_as_first_column(self):
        client = FakeClient(self.successful_response())
        result = ExperimentService(client).list_projects()

        rows = _table_items(result)

        self.assertEqual(
            list(rows[0]),
            [
                "projectId",
                "实验名称",
                "描述",
                "创建者",
                "修改者",
                "创建时间",
                "更新时间",
                "运行配置模板",
            ],
        )
        self.assertEqual(rows[0]["projectId"], "hidden-id")

    def project_detail(self):
        return {
            "projectId": "source-id",
            "projectName": "源实验",
            "configId": "config-id",
            "configName": "zs_1",
            "serviceChannel": "wiserecengineservice",
            "clusterName": "require-VM,require-NvLink",
            "description": "源描述",
            "businessId": "default",
            "teamId": "test_dev",
            "region": "cn-north-4",
            "subDomain": "sub-domain-id",
            "createUser": "old-user",
            "updateUser": "old-user",
            "runtimeConfigInfo": {"ignored": True},
        }

    def test_get_project_uses_id_query_and_required_business_header(self):
        client = FakeClient(
            {"result": {"code": 0, "des": "ok", "data": self.project_detail()}}
        )

        detail = ExperimentService(client).get_project("source-id")

        self.assertEqual(detail["projectName"], "源实验")
        self.assertEqual(
            client.calls,
            [
                (
                    "GET",
                    "/ai/backend/experiment/project/source-id",
                    None,
                    {"businessId": "default"},
                    {"businessid": "default"},
                )
            ],
        )

    def test_build_clone_request_only_replaces_name_and_users(self):
        client = FakeClient({}, username="b456789")

        body = ExperimentService(client).build_clone_request(
            self.project_detail(),
            "源实验_clone",
            "fixed-uuid",
        )

        self.assertEqual(body["version"], "1.0")
        self.assertEqual(body["meta"], {"uuid": "fixed-uuid"})
        self.assertEqual(
            body["data"],
            {
                "projectId": "",
                "projectName": "源实验_clone",
                "description": "源描述",
                "businessId": "default",
                "region": "cn-north-4",
                "subDomain": "sub-domain-id",
                "serviceChannel": "wiserecengineservice",
                "teamId": "test_dev",
                "clusterName": "require-VM,require-NvLink",
                "configId": "config-id",
                "configName": "zs_1",
                "createUser": "b456789",
                "updateUser": "b456789",
            },
        )
        self.assertNotIn("runtimeConfigInfo", body["data"])

    def test_create_project_posts_synchronously_with_business_header(self):
        response = {
            "result": {
                "code": 0,
                "des": "ok",
                "data": {"projectId": "new-id"},
            }
        }
        client = FakeClient(response)
        service = ExperimentService(client)
        body = service.build_clone_request(
            self.project_detail(),
            "源实验_clone",
            "fixed-uuid",
        )

        result = service.create_project(body)

        self.assertEqual(result, response)
        self.assertEqual(
            client.calls,
            [
                (
                    "POST",
                    "/ai/backend/experiment/project",
                    body,
                    None,
                    {"businessid": "default"},
                )
            ],
        )

    def test_get_project_rejects_cross_business_detail(self):
        detail = self.project_detail()
        detail["businessId"] = "another-business"
        client = FakeClient(
            {"result": {"code": 0, "des": "ok", "data": detail}}
        )

        with self.assertRaisesRegex(BusinessError, "不属于当前业务上下文"):
            ExperimentService(client).get_project("source-id")

    def test_clone_result_extracts_new_project_id(self):
        result = _clone_result(
            {
                "result": {
                    "code": 0,
                    "des": "ok",
                    "data": {"projectId": "new-id"},
                }
            },
            "source-id",
            "源实验_clone",
            "fixed-uuid",
        )

        self.assertEqual(result["projectId"], "new-id")
        self.assertEqual(result["sourceProjectId"], "source-id")

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


class ExperimentCloneCommandTest(unittest.TestCase):
    def project_detail_response(self):
        return {
            "result": {
                "code": 0,
                "des": "ok",
                "data": {
                    "projectId": "source-id",
                    "projectName": "源实验",
                    "configId": "config-id",
                    "configName": "zs_1",
                    "serviceChannel": "wiserecengineservice",
                    "clusterName": "require-VM",
                    "description": "",
                    "businessId": "default",
                    "teamId": "test_dev",
                    "region": "cn-north-4",
                    "subDomain": "sub-domain-id",
                },
            }
        }

    def runtime_for(self, client):
        return SimpleNamespace(
            authenticated_call=lambda operation: operation(client),
            config=SimpleNamespace(
                current_profile=lambda: SimpleNamespace(output_format="table")
            ),
        )

    def test_dry_run_only_queries_detail(self):
        client = FakeClient(self.project_detail_response())

        with patch(
            "wisemlops_cli.commands.offline.runtime_from_context",
            return_value=self.runtime_for(client),
        ), patch("wisemlops_cli.commands.offline.print_result") as printer:
            clone_experiment(
                Mock(),
                "source-id",
                project_name="源实验_clone",
                yes=False,
                dry_run=True,
                output="json",
            )

        self.assertEqual(len(client.calls), 1)
        rendered = printer.call_args.args[0]
        self.assertTrue(rendered["dryRun"])
        self.assertEqual(rendered["request"]["data"]["projectName"], "源实验_clone")

    def test_yes_executes_detail_and_create_with_one_uuid(self):
        client = FakeClient(
            [
                self.project_detail_response(),
                {
                    "result": {
                        "code": 0,
                        "des": "ok",
                        "data": {"projectId": "new-id"},
                    }
                },
            ]
        )

        with patch(
            "wisemlops_cli.commands.offline.runtime_from_context",
            return_value=self.runtime_for(client),
        ), patch("wisemlops_cli.commands.offline.print_result") as printer:
            clone_experiment(
                Mock(),
                "source-id",
                project_name="源实验_clone",
                yes=True,
                dry_run=False,
                output="json",
            )

        self.assertEqual(len(client.calls), 2)
        request_uuid = client.calls[1][2]["meta"]["uuid"]
        rendered = printer.call_args.args[0]
        self.assertEqual(rendered["uuid"], request_uuid)
        self.assertEqual(rendered["projectId"], "new-id")


if __name__ == "__main__":
    unittest.main()
