import json
import tempfile
import unittest
from pathlib import Path

from wisemlops_cli.business import BusinessStore, parse_business_list
from wisemlops_cli.credentials import CredentialStore
from wisemlops_cli.errors import BusinessError
from wisemlops_cli.models import Credentials
from wisemlops_cli.runtime import Runtime


class RuntimeBusinessContextTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.config_path = root / "config.json"
        self.credential_path = root / "credentials.json"
        self.business_path = root / "business.json"
        self.config_path.write_text(
            json.dumps(
                {
                    "current": "dev",
                    "profiles": [
                        {
                            "name": "dev",
                            "api_endpoint": "https://dev.example.com/dashboard",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        CredentialStore(self.credential_path).save(
            Credentials.create(
                profile="dev",
                cookie="session=abc",
                csrftoken="csrf",
                username="jack",
                ttl_seconds=1800,
            )
        )
        self.store = BusinessStore(self.business_path)
        self.store.refresh(
            "dev",
            "jack",
            parse_business_list(
                [
                    {
                        "cn": "测试MEP平台",
                        "value": "mep",
                        "settleTenant": "cloud",
                        "settleTenantName": json.dumps({"cn": "云平台部"}),
                        "teamList": [],
                    }
                ]
            ),
        )
        self.runtime = Runtime(
            config_path=self.config_path,
            credential_path=self.credential_path,
            business_path=self.business_path,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_business_call_requires_tenant_or_team(self):
        with self.assertRaisesRegex(BusinessError, "ml business use"):
            self.runtime.authenticated_call(lambda _client: None)

    def test_business_call_injects_selected_business_id(self):
        self.store.select("dev", "jack", tenant_id="mep")

        business_id = self.runtime.authenticated_call(
            lambda client: client._client.headers["ai-businessId"]
        )

        self.assertEqual(business_id, "mep")


if __name__ == "__main__":
    unittest.main()
