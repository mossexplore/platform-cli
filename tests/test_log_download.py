import inspect
import json
import ssl
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from typer.testing import CliRunner

from wisemlops_cli.cli import app
from wisemlops_cli.downloads import download_file, download_filename
from wisemlops_cli.errors import ApiError
from wisemlops_cli.services.train import TrainService
import test_client


class LogServiceTest(unittest.TestCase):
    def test_direct_user_ids_encoded_query_and_headers(self):
        requests = []
        def handler(request):
            requests.append(request)
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/ai/backend/mtp/traintask/downloadLogUrl")
            self.assertEqual(dict(request.url.params), {
                "jobId": "job & id", "taskId": " task-id ", "businessId": "mep",
                "isApplicantPromise": "true",
            })
            self.assertEqual(request.headers["businessid"], "mep")
            return httpx.Response(200, json={"result": {"code": 0, "des": "success", "url": "https://files.example/log"}})
        with test_client.PlatformClientTest().create_client(handler) as client:
            self.assertEqual(TrainService(client).get_log_url(" task-id ", "job & id"), "https://files.example/log")
        self.assertEqual(len(requests), 1)

    def test_invalid_ids_are_forwarded_and_server_error_is_reported(self):
        for task_id, job_id in (("missing-task", "missing-job"), ("", "")):
            calls = []
            def request(*args, **kwargs):
                calls.append(kwargs)
                return {"result": {"code": 1234, "des": "记录不存在"}}
            client = SimpleNamespace(business_id="b", request=request)
            with self.assertRaisesRegex(ApiError, "code=1234，des=记录不存在"):
                TrainService(client).get_log_url(task_id, job_id)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["params"]["taskId"], task_id)
            self.assertEqual(calls[0]["params"]["jobId"], job_id)

    def test_url_requires_exact_success_and_https(self):
        results = [{"code": 1, "des": "denied"}, {"code": 0, "des": "ok", "url": "https://host/log"},
                   {"code": False, "des": "success", "url": "https://host/log"}]
        results += [{"code": 0, "des": "success", "url": url} for url in
                    (None, "", "http://host/log", "https://", "https://user:password@host/log")]
        for result in results:
            responses = iter([{"result": result}])
            client = SimpleNamespace(business_id="b", request=lambda *a, **kw: next(responses))
            with self.subTest(result=result), self.assertRaisesRegex(ApiError, "code=.*des="):
                TrainService(client).get_log_url("t", "j")


class DownloaderTest(unittest.TestCase):
    def test_network_error_reports_type_message_and_underlying_cause(self):
        def handler(request):
            try:
                raise ssl.SSLCertVerificationError("certificate verify failed: unable to get local issuer certificate")
            except ssl.SSLCertVerificationError as cause:
                raise httpx.ConnectError("TLS connection failed", request=request) from cause
        with self.assertRaises(ApiError) as caught:
            download_file("https://files.example/log", "j", self.path,
                          transport=httpx.MockTransport(handler))
        message = str(caught.exception)
        self.assertIn("ConnectError", message)
        self.assertIn("TLS connection failed", message)
        self.assertIn("SSLCertVerificationError", message)
        self.assertIn("unable to get local issuer certificate", message)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_connection_error_without_cause_is_preserved(self):
        def handler(request):
            raise httpx.ConnectError("[Errno 61] Connection refused", request=request)
        with self.assertRaisesRegex(ApiError, "ConnectError.*Connection refused"):
            download_file("https://files.example/log", "j", self.path,
                          transport=httpx.MockTransport(handler))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "log.zip"

    def response(self, body=b"log bytes", **kwargs):
        return httpx.Response(200, stream=httpx.ByteStream(body), **kwargs)

    def test_download_stream_progress_and_no_credentials_on_redirects(self):
        seen = []
        def handler(request):
            seen.append(request)
            for header in ("cookie", "csrftoken", "businessid", "ai-businessid", "authorization"):
                self.assertNotIn(header, request.headers)
            if len(seen) == 1:
                return httpx.Response(302, headers={"location": "https://other.example/log", "set-cookie": "session=secret; Domain=.example"})
            return self.response(headers={"content-length": "9"})
        progress = []
        path, size = download_file("https://files.example/log?signature=secret", "j", self.path,
                                   transport=httpx.MockTransport(handler), progress=lambda *args: progress.append(args))
        self.assertEqual(path.read_bytes(), b"log bytes")
        self.assertEqual(size, 9)
        self.assertEqual(progress[-1], (9, 9))
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_default_filename_and_traversal(self):
        self.assertEqual(download_filename('attachment; filename="../../logs.zip"', "j"), "logs.zip")
        self.assertEqual(download_filename("attachment; filename*=UTF-8''%E6%97%A5%E5%BF%97.zip", "j"), "日志.zip")
        self.assertEqual(download_filename("", "j"), "j-logs")
        with patch("wisemlops_cli.downloads.Path", wraps=Path) as paths:
            paths.side_effect = lambda value: self.path.parent / value
            target, _ = download_file("https://files.example/log", "j", transport=httpx.MockTransport(
                lambda r: self.response(headers={"content-disposition": 'attachment; filename="../../logs.zip"'})))
        self.assertEqual(target.name, "logs.zip")
        self.assertEqual(target.parent, self.path.parent)

    def test_existing_file_and_race_never_overwrite(self):
        self.path.write_bytes(b"original")
        with self.assertRaises(ApiError):
            download_file("https://files.example/log", "j", self.path,
                          transport=httpx.MockTransport(lambda r: self.response()))
        self.assertEqual(self.path.read_bytes(), b"original")
        other = self.path.parent / "race.log"
        def race(done, total):
            other.write_bytes(b"competing")
        with self.assertRaises(ApiError):
            download_file("https://files.example/log", "j", other, progress=race,
                          transport=httpx.MockTransport(lambda r: self.response()))
        self.assertEqual(other.read_bytes(), b"competing")
        self.assertFalse(list(self.path.parent.glob("*.part")))

    def test_errors_and_incomplete_download_leave_no_file_or_signed_url(self):
        class Broken(httpx.SyncByteStream):
            def __iter__(self):
                yield b"partial"
                raise httpx.ReadError("https://files.example/log?signature=secret")
        for handler in (lambda r: httpx.Response(403),
                        lambda r: httpx.Response(200, stream=Broken()),
                        lambda r: self.response(headers={"content-length": "100"}),
                        lambda r: httpx.Response(302, headers={"location": "http://files.example/log"}),
                        lambda r: httpx.Response(302, headers={"location": "/loop"})):
            with self.subTest(handler=handler):
                with self.assertRaises(ApiError) as caught:
                    download_file("https://files.example/log?signature=secret", "j", self.path,
                                  transport=httpx.MockTransport(handler))
                self.assertNotIn("signature=secret", str(caught.exception))
                if "ReadError" in str(caught.exception):
                    self.assertIn("<下载地址>", str(caught.exception))
                self.assertEqual(list(self.path.parent.iterdir()), [])


class DownloadCommandTest(unittest.TestCase):
    def test_json_summary_and_file_validation(self):
        def authenticated(operation):
            print("认证提示", flush=True)
            return "https://files.example/log?signature=secret"
        runtime = SimpleNamespace(authenticated_call=authenticated,
            config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format="json")))
        options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
        runner = CliRunner(**options)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "log.zip"
            with patch("wisemlops_cli.cli.Runtime", return_value=runtime), patch(
                "wisemlops_cli.commands.train.runtime_from_context", return_value=runtime
            ), patch("wisemlops_cli.commands.train.download_file", return_value=(path, 12)) as download:
                result = runner.invoke(app, ["train", "history", "logs", "download", "t", "j", "--file", str(path)])
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual(json.loads(result.stdout), {"taskId": "t", "jobId": "j", "path": str(path), "bytes": 12, "status": "downloaded"})
                self.assertIn("https://files.example/log?signature=secret", result.stderr)
                self.assertNotIn("signature=secret", result.stdout)
                self.assertIn("认证提示", result.stderr)
                path.write_text("existing")
                result = runner.invoke(app, ["train", "history", "logs", "download", "t", "j", "--file", str(path)])
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(download.call_count, 1)
