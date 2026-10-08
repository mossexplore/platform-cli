"""服务列表和详情命令的请求契约与展示。"""

import inspect
import json
import unittest
from uuid import UUID
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

import test_runtime
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.service import display_value, render_page


class ServiceCommandTest(unittest.TestCase):
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
            return CliRunner(**options).invoke(app, ["service"] + arguments)

    def test_service_list_uses_selected_business_defaults_and_filters(self):
        item = {"serviceId": "a", "serviceName": "sample", "extra": {"kept": True}}

        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url),
                "https://dev.example.com/ai/backend/mep/services/queryList")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {
                "pageIndex": 2, "pageSize": 20, "inferenceType": None,
                "env": None, "tags": [], "serviceName": "demo", "selectService": None,
                "modelName": "model", "selectModelName": None,
                "modelVersion": "v1", "businessId": "mep",
                "teamId": "", "infraType": None, "owner": None, "status": None,
                "isAccess": None, "noAccessDays": None, "isLowLoad": None,
                "lowLoadDays": None, "noticeTime": [], "clusterId": None,
                "clusterBusinessId": "mep", "isCluster": None,
                "dailTestTaskStatus": None, "scaleFlag": None,
            })
            return httpx.Response(200, json={"result": {"code": 0,
                "count": 17, "services": [item]}})

        result = self.invoke(["list", "--page", "2", "--page-size", "20",
            "--name", "demo", "--model-name", "model", "--model-version", "v1",
            "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {"total": 17,
            "pageIndex": 2, "pageSize": 20, "items": [item]})

    def test_host_view_sends_fixed_filters_and_preserves_fields(self):
        item = {"deployId": "d", "health_status": 0, "memUsage": 0.28,
                "other": "kept"}

        def handler(request):
            self.assertEqual(request.url.path,
                "/ai/backend/mep/services/rtcContainer/queryServiceHostList")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {
                "businessId": "mep", "serviceId": "s", "status": "", "hostIp": "",
                "clusterName": "", "preheatStatus": "ALL", "quotaType": None,
                "pageIndex": 1, "pageSize": 10,
            })
            return httpx.Response(200, json={"result": {"code": 0,
                "count": 1, "data": [item]}})

        result = self.invoke(["host", "list", "s", "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout)["items"], [item])

    def test_deployment_view_displays_block_id_and_derived_columns(self):
        item = {"blockId": "b" * 36, "imageName": "repo/image",
                "imageVersion": "1.2", "cpuLimit": "2", "memoryLimit": "4",
                "gpuLimit": "0", "npuLimit": "1", "wiseEyeName": "Predict",
                "wiseEyeVersion": "1.9", "other": 123}

        def handler(request):
            self.assertEqual(request.url.path,
                "/ai/backend/mep/services/rtcContainer/queryDetail")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {"pageIndex": 1,
                "pageSize": 10, "serviceId": "s", "businessId": "mep"})
            return httpx.Response(200, json={"result": {"code": 0, "data": [item]}})

        result = self.invoke(["deployment", "list", "s", "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout)["items"], [item])
        self.assertEqual(display_value("blockId", item), "b" * 36)
        self.assertEqual(display_value("image", item), "repo/image 1.2")
        self.assertEqual(display_value("resourceSpec", item), "2C4G1NPU")
        self.assertEqual(display_value("framework", item), "Predict@1.9")

    def test_display_converts_status_usage_and_beijing_time(self):
        self.assertEqual(display_value("status", {"status": "1"}), "异常")
        self.assertEqual(display_value("status", {"status": 0}), "正常")
        self.assertEqual(display_value("health_status", {"health_status": 0}), "正常")
        self.assertEqual(display_value("health_status", {"health_status": 2}), "异常")
        self.assertEqual(display_value("cpuUsage", {"cpuUsage": 0.01}), "1.00%")
        self.assertEqual(display_value("memUsage", {"memUsage": 0.28}), "28.00%")
        self.assertEqual(display_value("gpuUsage", {"gpuUsage": -1.0}), "-")
        self.assertEqual(display_value("npuUsage", {"npuUsage": 0}), "0.00%")
        self.assertEqual(display_value("createTime", {"createTime": 1741940357000}),
                         "2025-03-14 16:19:17")
        self.assertEqual(display_value("update_time", {
            "update_time": "2026-09-08T06:54:36.000+00:00"}),
            "2026-09-08 14:54:36")
        self.assertEqual(display_value("owner", {}), "-")

    def test_first_id_column_is_fixed_36(self):
        from wiserec_cli.commands import service
        with patch.object(service.console, "print") as print_table:
            render_page("deployment", {"items": [{"blockId": "b" * 36}],
                "pageIndex": 1, "pageSize": 10}, "table")
        column = print_table.call_args_list[0].args[0].columns[0]
        self.assertEqual((column.width, column.min_width, column.max_width),
                         (36, 36, 36))
        self.assertTrue(column.no_wrap)

    def test_bad_response_is_not_treated_as_empty(self):
        for body in ({"code": 0, "services": []},
                     {"code": 0, "count": 0},
                     {"code": False, "count": 0, "services": []}):
            with self.subTest(body=body):
                result = self.invoke(["list"], lambda _request: httpx.Response(
                    200, json={"result": body}))
                self.assertNotEqual(result.exit_code, 0)

    def test_stale_selected_business_stops_before_request(self):
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"]["businessId"] = "stale"
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(["list"], lambda request: calls.append(request))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(calls, [])

    def test_log_file_list_sends_current_business_and_shows_values_unchanged(self):
        files = [{"fileSize": "168", "updateTime": "May 6 15:36",
                  "fileName": "[debug] interface.log", "extra": "kept"}]
        seen = []

        def handler(request):
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path,
                "/ai/backend/mep/services/rtcContainer/queryPodAdvanceLogFileList")
            self.assertEqual(request.headers["businessid"], "mep")
            body = json.loads(request.content)
            seen.append(body)
            self.assertEqual(body["version"], "1.0")
            UUID(body["meta"]["uuid"])
            self.assertEqual(body["data"], {
                "podStatus": 0, "businessId": "mep", "podName": "pod-1",
                "clusterName": "cluster-1", "serviceLogSearch": {"type": "rtc"},
                "belongingService": "",
            })
            return httpx.Response(200, json={"result": {"code": 0,
                "podLogFiles": files}})

        from wiserec_cli.commands import service
        with patch.object(service.console, "print") as printed:
            result = self.invoke(["host", "logs", "list", "pod-1",
                "--cluster", "cluster-1", "--type", "rtc"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(len(seen), 1)
        table = printed.call_args_list[0].args[0]
        self.assertEqual([column.header for column in table.columns],
                         ["日志文件大小", "修改时间", "日志文件名称"])
        self.assertEqual([column._cells[0].plain for column in table.columns],
                         ["168", "May 6 15:36", "[debug] interface.log"])

    def test_log_search_defaults_and_multiline_stdout(self):
        body_seen = []
        content = "first line\nsecond [INFO] line"

        def handler(request):
            self.assertEqual(request.url.path,
                "/ai/backend/mep/services/rtcContainer/queryPodAdvanceLog")
            self.assertEqual(request.headers["businessid"], "mep")
            body = json.loads(request.content)
            body_seen.append(body)
            UUID(body["meta"]["uuid"])
            self.assertEqual(body["data"], {
                "podStatus": 0, "businessId": "mep", "podName": "pod-1",
                "clusterName": "cluster-1", "serviceLogSearch": {
                    "type": "interface", "keywords": [], "line": 200,
                    "searchOrder": "tail", "logFileName": "interface.log",
                    "grepScope": "C", "grepLine": 0,
                }, "belongingService": "",
            })
            return httpx.Response(200, json={"result": {"code": 0,
                "data": {"content": content}}})

        result = self.invoke(["host", "logs", "search", "pod-1",
            "--cluster", "cluster-1", "--type", "interface",
            "--file", "interface.log"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.stdout, content + "\n")
        self.assertEqual(len(body_seen), 1)

    def test_log_search_passes_optional_values(self):
        def handler(request):
            search = json.loads(request.content)["data"]["serviceLogSearch"]
            self.assertEqual(search, {"type": "custom", "keywords": ["error", "timeout"],
                "line": 30, "searchOrder": "head", "logFileName": "app.log",
                "grepScope": "A", "grepLine": 2})
            return httpx.Response(200, json={"result": {"code": 0,
                "data": {"content": "match"}}})

        result = self.invoke(["host", "logs", "search", "pod-1",
            "--cluster", "cluster-1", "--type", "custom", "--file", "app.log",
            "--keyword", "error", "--keyword", "timeout", "--line", "30",
            "--search-order", "head", "--grep-scope", "A", "--grep-line", "2"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(result.stdout, "match\n")

    def test_log_errors_do_not_emit_success_output(self):
        for body in ({"code": 3, "des": "denied"},
                     {"code": 0, "data": {}},
                     {"code": 0, "data": {"content": None}}):
            with self.subTest(body=body):
                result = self.invoke(["host", "logs", "search", "pod-1",
                    "--cluster", "cluster-1", "--type", "interface",
                    "--file", "app.log"], lambda _request: httpx.Response(
                        200, json={"result": body}))
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(result.stdout, "")

    def test_log_commands_reject_stale_selected_business(self):
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"]["businessId"] = "stale"
        self.fixture.business_path.write_text(json.dumps(data))
        requests = []
        result = self.invoke(["host", "logs", "list", "pod-1",
            "--cluster", "cluster-1", "--type", "rtc"],
            lambda request: requests.append(request))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(requests, [])
