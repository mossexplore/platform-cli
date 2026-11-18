"""只有成功访问平台才能延长本地认证空闲时间。"""

import unittest
from unittest.mock import patch

import httpx

from wiserec_cli.client import PlatformClient
from wiserec_cli.errors import ApiError
from wiserec_cli.models import Credentials

from test_runtime import RuntimeBusinessContextTest


class AuthenticationActivityTest(unittest.TestCase):
    def setUp(self):
        self.fixture = RuntimeBusinessContextTest()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.fixture.store.select("dev", "jack", tenant_id="mep")
        self.runtime = self.fixture.runtime
        self.runtime.credentials.save(
            Credentials.create("dev", "session=abc", "csrf", "jack", 60)
        )

    def call_with_transport(self, operation, handler):
        def factory(**kwargs):
            return PlatformClient(**kwargs, transport=httpx.MockTransport(handler))
        with patch("wiserec_cli.runtime.PlatformClient", side_effect=factory):
            return self.runtime.authenticated_call(operation)

    def test_successful_platform_request_extends_idle_time(self):
        before = self.runtime.credentials.load("dev").expires_at
        result = self.call_with_transport(
            lambda client: client.request("GET", "/ai/user/info"),
            lambda _: httpx.Response(200, json={"result": {"code": 0}}),
        )
        self.assertEqual(result["result"]["code"], 0)
        self.assertGreater(self.runtime.credentials.load("dev").expires_at,
                           before + 1000)

    def test_permission_only_command_and_external_download_do_not_extend(self):
        before = self.runtime.credentials.load("dev").expires_at
        self.call_with_transport(lambda _client: None, lambda _: None)
        self.assertEqual(self.runtime.credentials.load("dev").expires_at, before)
        self.call_with_transport(
            lambda client: client.request("GET", "https://files.example.com/archive"),
            lambda _: httpx.Response(200, json={"download": "ok"}),
        )
        self.assertEqual(self.runtime.credentials.load("dev").expires_at, before)

    def test_failed_request_does_not_extend(self):
        before = self.runtime.credentials.load("dev").expires_at
        with self.assertRaises(ApiError):
            self.call_with_transport(
                lambda client: client.request("GET", "/ai/backend/fail"),
                lambda _: httpx.Response(503),
            )
        self.assertEqual(self.runtime.credentials.load("dev").expires_at, before)
        self.call_with_transport(
            lambda client: client.request("GET", "/ai/backend/fail"),
            lambda _: httpx.Response(200, json={"result": {"code": 9}}),
        )
        self.assertEqual(self.runtime.credentials.load("dev").expires_at, before)

    def test_successful_platform_stream_extends_after_consumption(self):
        before = self.runtime.credentials.load("dev").expires_at

        def download(client):
            with client.stream("GET", "/ai/backend/download") as response:
                return b"".join(response.iter_bytes())

        content = self.call_with_transport(
            download, lambda _: httpx.Response(200, content=b"archive"),
        )
        self.assertEqual(content, b"archive")
        self.assertGreater(self.runtime.credentials.load("dev").expires_at,
                           before + 1000)

    def test_successful_request_counts_even_if_later_request_fails(self):
        before = self.runtime.credentials.load("dev").expires_at

        def operation(client):
            client.request("GET", "/ai/backend/first")
            client.request("GET", "/ai/backend/second")

        def handler(request):
            if request.url.path.endswith("/first"):
                return httpx.Response(200, json={"result": {"code": 0}})
            return httpx.Response(503)

        with self.assertRaises(ApiError):
            self.call_with_transport(operation, handler)
        self.assertGreater(self.runtime.credentials.load("dev").expires_at,
                           before + 1000)
