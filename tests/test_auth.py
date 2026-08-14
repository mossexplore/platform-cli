import json
import tempfile
import unittest
from pathlib import Path

from wisemlops_cli.auth import AuthManager
from wisemlops_cli.config import ConfigManager
from wisemlops_cli.credentials import CredentialStore
from wisemlops_cli.models import Credentials


class FakeBrowserAuthenticator:
    def __init__(self, credentials, store):
        self.credentials = credentials
        self.store = store
        self.calls = 0

    def login(self, **_):
        self.calls += 1
        self.store.save(self.credentials)
        return self.credentials


class AuthManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "current": "dev",
                    "auth": {"expires_in_seconds": 1800},
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
        self.config = ConfigManager(config_path)
        self.store = CredentialStore(root / "credentials.json")

    def tearDown(self):
        self.temporary.cleanup()

    def test_expired_credentials_are_refreshed_and_saved(self):
        expired = Credentials(
            profile="dev",
            cookie="old-cookie",
            csrftoken="old-csrf",
            username="old-user",
            acquired_at=1,
            expires_at=2,
        )
        refreshed = Credentials.create(
            profile="dev",
            cookie="new-cookie",
            csrftoken="new-csrf",
            username="new-user",
            ttl_seconds=1800,
        )
        self.store.save(expired)

        manager = AuthManager(self.config, self.store)
        fake_browser = FakeBrowserAuthenticator(refreshed, self.store)
        manager.browser = fake_browser
        result = manager.ensure_credentials()

        self.assertEqual(result.cookie, "new-cookie")
        self.assertEqual(fake_browser.calls, 1)
        self.assertEqual(self.store.load("dev").cookie, "new-cookie")

    def test_valid_credentials_are_reused(self):
        valid = Credentials.create(
            profile="dev",
            cookie="valid-cookie",
            csrftoken="valid-csrf",
            username="jack",
            ttl_seconds=1800,
        )
        self.store.save(valid)
        manager = AuthManager(self.config, self.store)
        fake_browser = FakeBrowserAuthenticator(valid, self.store)
        manager.browser = fake_browser

        result = manager.ensure_credentials()

        self.assertEqual(result.cookie, "valid-cookie")
        self.assertEqual(fake_browser.calls, 0)


if __name__ == "__main__":
    unittest.main()
