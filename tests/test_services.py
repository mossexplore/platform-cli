import unittest

from wisemlops_cli.services.mep import MepService
from wisemlops_cli.services.user import UserService


class FakeClient:
    def __init__(self):
        self.calls = []

    def request(self, method, path, json_body=None):
        self.calls.append((method, path, json_body))
        return {"success": True}


class ServiceTest(unittest.TestCase):
    def test_mep_query_uses_expected_endpoint_and_body(self):
        client = FakeClient()
        result = MepService(client).query_config("mep_service_access_type")
        self.assertEqual(result, {"success": True})
        self.assertEqual(
            client.calls,
            [
                (
                    "POST",
                    "/ai/backend/mep/config/queryConfig",
                    {"key": "mep_service_access_type"},
                )
            ],
        )

    def test_user_info_uses_expected_endpoint(self):
        client = FakeClient()
        UserService(client).info()
        self.assertEqual(client.calls, [("GET", "/ai/user/info", None)])


if __name__ == "__main__":
    unittest.main()
