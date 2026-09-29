"""数据集查询的请求契约和终端展示。"""

import inspect
import json
import unittest
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

import test_runtime
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands import dataset


class DatasetCommandTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_runtime.RuntimeBusinessContextTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.store.select("dev", "jack", tenant_id="mep")

    def invoke(self, arguments, handler):
        def client_factory(**kwargs):
            return PlatformClient(**kwargs, transport=httpx.MockTransport(handler))

        options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
        with patch("wiserec_cli.cli.Runtime", return_value=self.fixture.runtime), patch(
            "wiserec_cli.runtime.PlatformClient", side_effect=client_factory,
        ):
            return CliRunner(**options).invoke(app, ["dataset"] + arguments)

    def test_list_defaults_business_header_and_response_fields(self):
        item = {"dataSetId": "a" * 36, "dataSetName": "dog_cat", "extra": {"kept": True}}

        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://dev.example.com/ai/backend/mtp/dataSet/queryList")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {
                "pageIndex": 1, "pageSize": 10, "bucketName": None,
                "dataSetName": "", "dataSetId": "", "businessId": "mep", "teamId": "",
                "scene": "", "subScene": "", "dataSetType": "",
                "noticeTime": [], "updateNoticeTime": [], "origin": "",
                "notUsedDays": "", "subDatazoneId": "", "tags": "",
                "createUser": "", "updateUser": "", "expireStatus": None,
                "private": False, "isDeleted": "", "sharing": False,
                "inputName": "", "inputId": "", "region": "",
                "commonTabTitle": "", "algorithmVersion": "",
            })
            return httpx.Response(200, json={"result": {"code": 0,
                "totalSize": 24, "data": [item]}})

        result = self.invoke(["list", "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {"total": 24,
            "pageIndex": 1, "pageSize": 10, "items": [item]})

    def test_list_filters_are_sent_without_changing_other_defaults(self):
        def handler(request):
            body = json.loads(request.content)
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual({key: body[key] for key in (
                "pageIndex", "pageSize", "dataSetName", "createUser", "updateUser",
                "bucketName", "businessId", "teamId",
            )}, {"pageIndex": 2, "pageSize": 20, "dataSetName": "dog",
                "createUser": "alice", "updateUser": "bob", "bucketName": "bucket",
                "businessId": "mep", "teamId": ""})
            self.assertIsNone(body["expireStatus"])
            self.assertFalse(body["private"])
            return httpx.Response(200, json={"result": {"code": 0,
                "totalSize": 0, "data": []}})

        result = self.invoke(["list", "--page", "2", "--page-size", "20",
            "--dataset-name", "dog", "--create-user", "alice",
            "--update-user", "bob", "--bucket-name", "bucket"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("暂无数据集记录", result.output)
        self.assertIn("共 0 条", result.output)

    def test_detail_uses_selected_business_and_preserves_extra_fields(self):
        data = {"dataSetId": "source", "bucketFileId": "file-id",
                "businessId": "mep", "extra": [1, 2]}

        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url), "https://dev.example.com/ai/backend/mtp/dataSet/queryDetail")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {"dataSetId": "source",
                "businessId": "mep", "teamId": ""})
            return httpx.Response(200, json={"result": {"code": 0, "data": data}})

        result = self.invoke(["detail", "source", "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), data)

    def test_size_time_and_detail_id_rendering(self):
        self.assertEqual(dataset.display_value("fileSize", 22), "22B")
        self.assertEqual(dataset.display_value("fileSize", 1024), "1.00K")
        self.assertEqual(dataset.display_value("fileSize", 1024 ** 2), "1.00M")
        self.assertEqual(dataset.display_value("fileSize", 1024 ** 3), "1.00G")
        self.assertEqual(dataset.display_value("fileSize", None), "-")
        self.assertEqual(dataset.display_value("modifyTime", "2026-09-29 18:50:01"),
                         "2026-09-29 18:50:01")
        self.assertEqual(dataset.display_value("useTime", "2026-09-08T06:54:36.000+00:00"),
                         "2026-09-08 14:54:36")
        with patch.object(dataset.console, "print") as printer:
            dataset.render_detail({"dataSetId": "source", "bucketFileId": "file-id"}, "table")
        table = printer.call_args_list[0].args[0]
        self.assertEqual(str(table.columns[1]._cells[6]), "file-id")

    def test_first_list_id_column_is_fixed_36(self):
        with patch.object(dataset.console, "print") as printer:
            dataset.render_list({"items": [{"dataSetId": "a" * 36}],
                "pageIndex": 1, "pageSize": 10, "total": 1}, "table")
        column = printer.call_args_list[0].args[0].columns[0]
        self.assertEqual((column.width, column.min_width, column.max_width), (36, 36, 36))
        self.assertTrue(column.no_wrap)

    def test_invalid_response_is_not_treated_as_empty_or_success(self):
        for result_body in ({"code": 0, "data": []},
                            {"code": 0, "totalSize": 0},
                            {"code": False, "totalSize": 0, "data": []},
                            {"code": 9, "des": "denied", "totalSize": 0, "data": []}):
            with self.subTest(result_body=result_body):
                result = self.invoke(["list"], lambda _request: httpx.Response(
                    200, json={"result": result_body}))
                self.assertNotEqual(result.exit_code, 0)
        result = self.invoke(["detail", "source"], lambda _request: httpx.Response(
            200, json={"result": {"code": 0}}))
        self.assertNotEqual(result.exit_code, 0)

    def test_stale_business_selection_stops_before_request(self):
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"]["businessId"] = "stale"
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(["detail", "source"], lambda request: calls.append(request))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(calls, [])
        self.assertIn("selected.businessId", result.stderr)
