import unittest

import httpx

from wisemlops_cli.client import PlatformClient
from wisemlops_cli.errors import AuthenticationError
from wisemlops_cli.models import Credentials, Profile


class PlatformClientTest(unittest.TestCase):
    def create_client(self, handler):
        return PlatformClient(
            profile=Profile(
                name="dev",
                api_endpoint="https://dev.example.com/dashboard",
            ),
            credentials=Credentials.create(
                profile="dev",
                cookie="session=abc; token=xyz",
                csrftoken="csrf-value",
                username="jack",
                ttl_seconds=1800,
            ),
            timeout_ms=30000,
            retry_times=3,
            verify_ssl=True,
            transport=httpx.MockTransport(handler),
        )

    def test_sends_complete_authentication_headers(self):
        def handler(request):
            self.assertEqual(request.headers["cookie"], "session=abc; token=xyz")
            self.assertEqual(request.headers["csrftoken"], "csrf-value")
            return httpx.Response(200, json={"username": "jack"})

        with self.create_client(handler) as client:
            result = client.request("GET", "/ai/user/info")
        self.assertEqual(result["username"], "jack")

    def test_authentication_status_triggers_refresh_signal(self):
        def handler(_):
            return httpx.Response(401, json={"message": "expired"})

        with self.create_client(handler) as client:
            with self.assertRaises(AuthenticationError):
                client.request("GET", "/ai/user/info")

    def test_redirect_triggers_refresh_signal(self):
        def handler(_):
            return httpx.Response(302, headers={"location": "/login"})

        with self.create_client(handler) as client:
            with self.assertRaises(AuthenticationError):
                client.request("GET", "/ai/user/info")


if __name__ == "__main__":
    unittest.main()
