import inspect
import json
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


JOB = {"jobId": "j", "taskId": "t", "businessId": "record-business", "taskName": "任务 & name"}


class LogServiceTest(unittest.TestCase):
    def test_record_mapping_encoded_query_and_headers(self):
        requests = []
        def handler(request):
            requests.append(request)
            if request.method == "POST":
                self.assertEqual(json.loads(request.content)["taskId"], "t")
                return httpx.Response(200, json={"result": {"code": 0, "count": 1, "jobs": [JOB]}})
            self.assertEqual(request.url.path, "/ai/backend/mtp/traintask/downloadLogUrl")
            self.assertEqual(dict(request.url.params), {
                "jobId": "j", "taskId": "t", "businessId": "record-business",
                "target": "任务 & name", "isApplicantPromise": "true",
            })
            self.assertEqual(request.headers["businessid"], "record-business")
            return httpx.Response(200, json={"result": {"code": 0, "des": "success", "url": "https://files.example/log"}})
        with test_client.PlatformClientTest().create_client(handler) as client:
            self.assertEqual(TrainService(client).get_log_url("t", "j"), "https://files.example/log")
        self.assertEqual(len(requests), 2)

    def test_invalid_records_stop_before_url_request(self):
        for records in ([], [dict(JOB, taskId="other")], [dict(JOB, businessId=None)],
                        [dict(JOB, taskName="")], [JOB, JOB]):
            with self.subTest(records=records):
                calls = []
                def request(*args, **kwargs):
                    calls.append(args)
                    return {"result": {"code": 0, "count": len(records), "jobs": records}}
                client = SimpleNamespace(business_id="b", request=request)
                with self.assertRaises(ApiError):
                    TrainService(client).get_log_url("t", "j")
                self.assertEqual(len(calls), 1)

    def test_url_requires_exact_success_and_https(self):
        results = [{"code": 1, "des": "denied"}, {"code": 0, "des": "ok", "url": "https://host/log"},
                   {"code": False, "des": "success", "url": "https://host/log"}]
        results += [{"code": 0, "des": "success", "url": url} for url in
                    (None, "", "http://host/log", "https://", "https://user:password@host/log")]
        for result in results:
            responses = iter([{"result": {"code": 0, "count": 1, "jobs": [JOB]}}, {"result": result}])
            client = SimpleNamespace(business_id="b", request=lambda *a, **kw: next(responses))
            with self.subTest(result=result), self.assertRaisesRegex(ApiError, "code=.*des="):
                TrainService(client).get_log_url("t", "j")


class DownloaderTest(unittest.TestCase):
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
                self.assertNotIn("signature=secret", result.stdout + result.stderr)
                self.assertIn("认证提示", result.stderr)
                path.write_text("existing")
                result = runner.invoke(app, ["train", "history", "logs", "download", "t", "j", "--file", str(path)])
                self.assertNotEqual(result.exit_code, 0)
                self.assertEqual(download.call_count, 1)
