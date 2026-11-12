import ssl
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from wiserec_cli.downloads import download_file, download_filename
from wiserec_cli.errors import ApiError


class DownloaderTest(unittest.TestCase):
    def test_download_disables_certificate_verification(self):
        real_client = httpx.Client
        with patch("wiserec_cli.downloads.httpx.Client", wraps=real_client) as client:
            download_file("https://files.example/log", "j", self.path,
                          transport=httpx.MockTransport(lambda r: self.response()))
        self.assertIs(client.call_args.kwargs["verify"], False)
        self.assertEqual(self.path.read_bytes(), b"log bytes")

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
        self.assertEqual(download_filename("", "j"), "j-logs.zip")
        self.assertEqual(download_filename('attachment; filename="train.log"', "j"), "train.log.zip")
        self.assertEqual(download_filename('attachment; filename="train.ZIP"', "j"), "train.ZIP")
        with patch("wiserec_cli.downloads.Path", wraps=Path) as paths:
            paths.side_effect = lambda value: self.path.parent / value
            target, _ = download_file("https://files.example/log", "j", transport=httpx.MockTransport(
                lambda r: self.response(headers={"content-disposition": 'attachment; filename="../../logs.zip"'})))
        self.assertEqual(target.name, "logs.zip")
        self.assertEqual(target.parent, self.path.parent)

    def test_existing_file_and_race_never_overwrite(self):
        self.path.write_bytes(b"original")
        self.path.with_name("log (1).zip").write_bytes(b"previous")
        saved, _ = download_file("https://files.example/log", "j", self.path,
                                 transport=httpx.MockTransport(lambda r: self.response()))
        self.assertEqual(saved.name, "log (2).zip")
        self.assertEqual(saved.read_bytes(), b"log bytes")
        self.assertEqual(self.path.with_name("log (1).zip").read_bytes(), b"previous")
        self.assertEqual(self.path.read_bytes(), b"original")
        other = self.path.parent / "race.log"
        def race(done, total):
            other.write_bytes(b"competing")
        saved, _ = download_file("https://files.example/log", "j", other, progress=race,
                                 transport=httpx.MockTransport(lambda r: self.response()))
        self.assertEqual(saved.name, "race (1).log")
        self.assertEqual(saved.read_bytes(), b"log bytes")
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
