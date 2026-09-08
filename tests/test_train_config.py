import inspect
import json
import unittest
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from wisemlops_cli.cli import app
from wisemlops_cli.client import PlatformClient
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

    def test_request_uses_current_business_file_and_preserves_string(self):
        calls = []
        for value in ("0096999", "  key=value & 中文  ", ""):
            def handler(request):
                calls.append(request)
                self.assertEqual(str(request.url), "https://dev.example.com/ai/backend/modelDev/modelTrain/updateNew")
                self.assertEqual(request.method, "POST")
                self.assertEqual(request.headers["businessid"], "mep")
                self.assertEqual(json.loads(request.content), {"data": {
                    "id": "task-id", "businessId": "mep", "name": "任务 a5555", "creator": "", "modifier": "",
                    "taskInfo": {"parameter": {"customizeConfig": value}, "updateUser": "jack"},
                }})
                return httpx.Response(200, json={"result": {"code": 0, "des": "success"}})
            result = self.invoke(["task-id", "--name", "任务 a5555", "--customize-config", value], handler)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertEqual(result.stdout, "更新训练任务自定义参数\n")
        self.assertEqual(len(calls), 3)

    def test_missing_or_wrong_business_username_never_falls_back_to_credentials(self):
        for username in (None, "", " ", "another-user"):
            data = json.loads(self.fixture.business_path.read_text())
            data["profiles"]["dev"]["username"] = username
            self.fixture.business_path.write_text(json.dumps(data))
            calls = []
            result = self.invoke(["t", "--name", "任务 a5555", "--customize-config", "v"], lambda r: calls.append(r))
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(calls, [])
            self.assertEqual(result.stdout, "")

    def test_invalid_args_and_missing_selection_do_not_send(self):
        for args in (["t", "--name", "n"], ["--name", "n", "--customize-config", "v"],
                     [" ", "--name", "n", "--customize-config", "v"],
                     ["t", "--customize-config", "v"]):
            calls = []
            result = self.invoke(args, lambda r: calls.append(r))
            self.assertNotEqual(result.exit_code, 0)
            self.assertEqual(calls, [])
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"] = None
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(["t", "--name", "任务 a5555", "--customize-config", "v"], lambda r: calls.append(r))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(calls, [])
        self.assertIn("ml business use", result.stderr)

    def test_response_requires_exact_success(self):
        for payload in ({}, {"result": {"code": 1, "des": "任务不存在"}},
                        {"result": {"code": 0, "des": "failed"}},
                        {"result": {"code": False, "des": "success"}},
                        {"result": {"code": "0", "des": "success"}}):
            result = self.invoke(["t", "--name", "任务 a5555", "--customize-config", "v"],
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
        result = self.invoke(["t", "--name", "任务 a5555", "--customize-config", "v"], handler)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.stdout, "")
