import inspect
import json
import unittest
from copy import deepcopy
from unittest.mock import Mock, patch

import httpx
from typer.testing import CliRunner

from wisemlops_cli.cli import app
from wisemlops_cli.client import PlatformClient
from wisemlops_cli.services.train import TrainService
import test_runtime


class TrainConfigCommandTest(unittest.TestCase):
    def setUp(self):
        self.fixture = test_runtime.RuntimeBusinessContextTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.store.select("dev", "jack", tenant_id="mep")
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["other"] = {"username": "wrong-user", "selected": {"businessId": "wrong-business"}}
        self.fixture.business_path.write_text(json.dumps(data))

    def invoke(self, args, handler):
        def client_factory(**kwargs):
            return PlatformClient(**kwargs, transport=httpx.MockTransport(handler))
        options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
        with patch("wisemlops_cli.cli.Runtime", return_value=self.fixture.runtime), patch(
            "wisemlops_cli.runtime.PlatformClient", side_effect=client_factory
        ):
            return CliRunner(**options).invoke(app, ["train", "config", "update"] + args)

    def detail(self):
        return {"result": {"code": 0, "des": "success", "data": {
            "name": "任务 a5555", "taskInfo": {"parameter": {
                "customizeConfig": "old", "other": [1, {"a": True}]},
                "updateUser": "old-user", "extra": {"nested": None}},
        }}}

    def test_request_uses_current_business_file_and_preserves_string(self):
        calls = []
        for value in ("0096999", "  key=value & 中文  ", ""):
            def handler(request):
                calls.append(request)
                if request.url.path.endswith("/detailNew"):
                    self.assertEqual(request.method, "POST")
                    self.assertEqual(request.headers["businessid"], "mep")
                    self.assertEqual(json.loads(request.content), {"data": {"id": "task-id", "businessId": "mep", "teamId": ""}})
                    return httpx.Response(200, json=self.detail())
                self.assertEqual(str(request.url), "https://dev.example.com/ai/backend/modelDev/modelTrain/updateNew")
                self.assertEqual(request.method, "POST")
                self.assertEqual(request.headers["businessid"], "mep")
                self.assertEqual(json.loads(request.content), {"data": {
                    "id": "task-id", "businessId": "mep", "name": "任务 a5555", "creator": "", "modifier": "",
                    "taskInfo": {"parameter": {"customizeConfig": value, "other": [1, {"a": True}]}, "updateUser": "jack", "extra": {"nested": None}},
                }})
                return httpx.Response(200, json={"result": {"code": 0, "des": "success"}})
            result = self.invoke(["task-id", "--customize-config", value], handler)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(result.stdout, "更新训练任务自定义参数成功！\n")
        self.assertEqual(len(calls), 6)

    def test_missing_or_wrong_business_username_never_falls_back_to_credentials(self):
        for username in (None, "", " ", "another-user"):
            data = json.loads(self.fixture.business_path.read_text())
            data["profiles"]["dev"]["username"] = username
            self.fixture.business_path.write_text(json.dumps(data))
            calls = []
            result = self.invoke(["t", "--customize-config", "v"], lambda r: calls.append(r))
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(calls, [])
            self.assertEqual(result.stdout, "")

    def test_invalid_args_and_missing_selection_do_not_send(self):
        for args in (["t"], ["--customize-config", "v"],
                     [" ", "--customize-config", "v"],
                     ["t", "--name", "n", "--customize-config", "v"]):
            calls = []
            result = self.invoke(args, lambda r: calls.append(r))
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(calls, [])
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"] = None
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(["t", "--customize-config", "v"], lambda r: calls.append(r))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(calls, [])
        self.assertIn("ml business use", result.stderr)

    def test_response_requires_exact_success(self):
        for payload in ({}, {"result": {"code": 1, "des": "任务不存在"}},
                        {"result": {"code": 0, "des": "failed"}},
                        {"result": {"code": False, "des": "success"}},
                        {"result": {"code": "0", "des": "success"}}):
            result = self.invoke(["t", "--customize-config", "v"],
                                 lambda r: httpx.Response(200, json=payload))
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "")
            if "result" in payload:
                self.assertIn(f"code={payload['result']['code']}", result.stderr)
                self.assertIn(f"des={payload['result']['des']}", result.stderr)

    def test_network_error_is_not_replayed(self):
        calls = []
        def handler(request):
            calls.append(request)
            raise httpx.ReadTimeout("response lost")
        result = self.invoke(["t", "--customize-config", "v"], handler)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.stdout, "")

    def test_update_failure_is_reported_after_successful_detail(self):
        for failure in ({"result": {"code": 1, "des": "更新被拒绝"}},
                        {"result": {"code": 0, "des": "failed"}}, None):
            calls = []
            def handler(request):
                calls.append(request)
                if request.url.path.endswith("/detailNew"):
                    return httpx.Response(200, json=self.detail())
                if failure is None:
                    raise httpx.ReadTimeout("response lost")
                return httpx.Response(200, json=failure)
            result = self.invoke(["t", "--customize-config", "v"], handler)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(len(calls), 2)

    def test_malformed_detail_prevents_update(self):
        for data in ({}, {"name": "n"}, {"name": "n", "taskInfo": None},
                     {"taskInfo": {}}, {"name": "n", "taskInfo": {"parameter": []}}):
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(200, json={"result": {"code": 0, "des": "success", "data": data}})
            result = self.invoke(["t", "--customize-config", "v"], handler)
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(len(calls), 1)

    def test_detail_is_copied_and_missing_parameter_is_created(self):
        for info in ({}, {"parameter": None}, self.detail()["result"]["data"]["taskInfo"]):
            original = deepcopy(info)
            client = Mock(business_id="mep")
            client.request.side_effect = [
                {"result": {"code": 0, "des": "success", "data": {"name": "n", "taskInfo": info}}},
                {"result": {"code": 0, "des": "success"}},
            ]
            TrainService(client).update_config("t", "0099", "jack")
            sent = client.request.call_args.kwargs["json_body"]["data"]
            self.assertEqual(sent["name"], "n")
            self.assertEqual(sent["taskInfo"]["parameter"]["customizeConfig"], "0099")
            self.assertEqual(sent["taskInfo"]["updateUser"], "jack")
            self.assertEqual(info, original)
