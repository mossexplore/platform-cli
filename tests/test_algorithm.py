"""算法仓 CLI 的请求、展示与下载边界。"""

import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from wiserec_cli.algorithm_download import download_algorithm
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.algorithm import _display
import test_runtime


class AlgorithmCommandTest(unittest.TestCase):
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
            return CliRunner(**options).invoke(app, ["algorithm"] + arguments)

    def test_list_uses_exact_defaults_business_and_filters(self):
        calls = []
        item = {"id": "a", "name": "example", "version": "1.0.0",
                "modifyTime": "2026-09-04T08:08:55.000Z", "extra": {"kept": True}}

        def handler(request):
            calls.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(str(request.url),
                             "https://dev.example.com/ai/backend/modelDev/algorithmWarehouse/list")
            self.assertEqual(request.headers["businessid"], "mep")
            body = json.loads(request.content)
            self.assertEqual(body["version"], "1.0")
            self.assertTrue(body["meta"]["uuid"])
            self.assertEqual(body["data"], {
                "businessId": "mep", "pageIndex": 2, "pageSize": 20,
                "algorithmName": "vision", "updater": "", "creator": "",
                "visualTag": "", "algorithmVersion": "", "tagsList": [],
                "bucketName": "bucket", "region": "", "algorithmPurpose": "",
                "enableFlag": "", "noticeTime": [], "beginTime": None,
                "endTime": None, "teamId": "",
            })
            return httpx.Response(200, json={"result": {"code": 0, "des": "success",
                "data": {"total": 930, "list": [item]}}})

        result = self.invoke(["list", "--page", "2", "--page-size", "20",
                              "--name", "vision", "--bucket-name", "bucket", "-o", "json"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(json.loads(result.stdout), {"total": 930,
            "pageIndex": 2, "pageSize": 20, "items": [item]})
        self.assertEqual(len(calls), 1)

    def test_display_converts_timezone_flags_and_size(self):
        self.assertEqual(_display("modifyTime", "2026-09-04T08:08:55.000Z"),
                         "2026-09-04 16:08:55")
        self.assertEqual(_display("modifyTime", "2026-09-04T08:08:55+02:00"),
                         "2026-09-04 14:08:55")
        self.assertEqual(_display("fileSize", 334872744), "319.36M")
        self.assertEqual(_display("fileSize", 1024 ** 3), "1.00G")
        self.assertEqual(_display("enableFlag", True), "否")
        self.assertEqual(_display("enableFlag", False), "是")
        self.assertEqual(_display("archiveToNspStatus", 1), "归档成功")
        self.assertEqual(_display("archiveToNspStatus", 0), "未归档")
        self.assertEqual(_display("enableFlag", None), "-")

    def test_download_gets_url_then_saves_without_forwarding_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "artifact.bin"
            existing = Path(directory) / "artifact.bin.zip"
            existing.write_bytes(b"old")
            requests = []

            def platform(request):
                requests.append(request)
                self.assertEqual(request.method, "GET")
                self.assertEqual(str(request.url),
                    "https://dev.example.com/ai/backend/mtp/algorithm/downloadurl?businessId=mep&algorithmId=abc")
                self.assertEqual(request.headers["businessid"], "mep")
                return httpx.Response(200, json={"result": {"code": 0,
                    "url": "https://files.example.com/signed?key=secret"}})

            def file_server(request):
                self.assertEqual(request.url.host, "files.example.com")
                for header in ("businessid", "cookie", "csrftoken", "authorization"):
                    self.assertNotIn(header, request.headers)
                return httpx.Response(200, headers={"content-type": "application/octet-stream"},
                                      stream=httpx.ByteStream(b"new-content"))

            def downloader(url, algorithm_id, file, **kwargs):
                return download_algorithm(url, algorithm_id, file,
                    transport=httpx.MockTransport(file_server), **kwargs)

            with patch("wiserec_cli.commands.algorithm.download_algorithm", side_effect=downloader):
                result = self.invoke(["download", "abc", "--file", str(destination)], platform)
            self.assertEqual(result.exit_code, 0, result.output)
            self.assertIn("算法仓下载链接：https://files.example.com/signed?key=secret", result.output)
            self.assertEqual(existing.read_bytes(), b"old")
            self.assertFalse(destination.exists())
            saved = Path(directory) / "artifact.bin (1).zip"
            self.assertEqual(saved.read_bytes(), b"new-content")
            self.assertIn(str(saved), result.output)
            self.assertEqual(len(requests), 1)

    def test_download_keeps_existing_zip_suffix(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "algorithm.ZIP"
            path, size = download_algorithm(
                "https://files.example.com/object", "abc", target,
                transport=httpx.MockTransport(lambda _request: httpx.Response(
                    200, headers={"content-type": "application/octet-stream"}, content=b"zip")),
            )
            self.assertEqual(path, target)
            self.assertEqual(path.read_bytes(), b"zip")
            self.assertEqual(size, 3)

    def test_download_rejects_invalid_url_before_file_request(self):
        def platform(_request):
            return httpx.Response(200, json={"result": {"code": 0,
                "url": "http://files.example.com/object"}})
        with patch("wiserec_cli.commands.algorithm.download_algorithm") as downloader:
            result = self.invoke(["download", "abc"], platform)
        self.assertNotEqual(result.exit_code, 0)
        downloader.assert_not_called()

    def test_incomplete_download_cleans_temporary_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "artifact.bin"
            response = lambda _request: httpx.Response(200, headers={
                "content-type": "application/octet-stream", "content-length": "20",
            }, content=b"short")
            with self.assertRaisesRegex(Exception, "不完整"):
                download_algorithm("https://files.example.com/object", "abc", target,
                                   transport=httpx.MockTransport(response))
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_clone_sends_logged_in_operator_and_accepts_code_zero(self):
        calls = []

        def handler(request):
            calls.append(request)
            self.assertEqual(request.method, "POST")
            self.assertEqual(request.url.path, "/ai/backend/modelDev/algorithmWarehouse/copy")
            self.assertEqual(request.headers["businessid"], "mep")
            self.assertEqual(json.loads(request.content), {"data": {
                "srcId": "source", "businessId": "mep", "operator": "jack",
                "tarName": "new", "tarVersion": "latest",
            }})
            return httpx.Response(200, json={"result": {"code": 0, "des": "created"}})

        result = self.invoke(["clone", "source", "--name", "new",
                              "--version", "latest", "--yes"], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("克隆算法仓source成功", result.output)
        self.assertEqual(len(calls), 1)

    def test_clone_auth_rejection_is_not_replayed(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(403, json={"message": "expired"})

        result = self.invoke(["clone", "source", "--name", "new",
                              "--version", "latest", "--yes"], handler)
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(len(calls), 1)

    def test_invalid_list_response_does_not_become_empty(self):
        for result_body in ({"code": 0, "data": {"list": []}},
                            {"code": 0, "data": {"total": 1}},
                            {"code": False, "data": {"total": 0, "list": []}}):
            with self.subTest(result_body=result_body):
                result = self.invoke(["list"], lambda _request: httpx.Response(
                    200, json={"result": result_body}))
                self.assertNotEqual(result.exit_code, 0)

    def test_stale_selected_business_stops_before_platform_request(self):
        data = json.loads(self.fixture.business_path.read_text())
        data["profiles"]["dev"]["selected"]["businessId"] = "stale-business"
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(["list"], lambda request: calls.append(request))
        self.assertNotEqual(result.exit_code, 0)
        self.assertEqual(calls, [])
        self.assertIn("selected.businessId", result.stderr)


if __name__ == "__main__":
    unittest.main()
