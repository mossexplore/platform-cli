import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from wisemlops_cli.auth import AuthManager, BrowserAuthenticator
from wisemlops_cli.config import ConfigManager
from wisemlops_cli.credentials import CredentialStore
from wisemlops_cli.models import Credentials, Profile


class FakeBrowserAuthenticator:
    def __init__(self, credentials, store):
        self.credentials = credentials
        self.store = store
        self.calls = 0

    def login(self, **_):
        self.calls += 1
        self.store.save(self.credentials)
        return self.credentials


class FakePage:
    def __init__(self):
        self.default_timeout = None

    def set_default_timeout(self, timeout):
        self.default_timeout = timeout

    def is_closed(self):
        return False


class FakePersistentContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.closed = False

    def close(self):
        self.closed = True


class FakePlaywright:
    def __init__(self, context):
        self.context = context
        self.launch_arguments = None
        self.chromium = self

    def launch_persistent_context(self, **kwargs):
        self.launch_arguments = kwargs
        return self.context


class FakePlaywrightManager:
    def __init__(self, playwright):
        self.playwright = playwright

    def __enter__(self):
        return self.playwright

    def __exit__(self, *_):
        return False


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
                    "browser": {
                        "profile_root": str(root / "browser-profiles"),
                    },
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

    def test_logout_can_remove_dedicated_browser_profile(self):
        profile_dir = self.config.browser_profile_dir("dev")
        profile_dir.mkdir(parents=True)
        (profile_dir / "state").write_text("session", encoding="utf-8")
        manager = AuthManager(self.config, self.store)

        manager.logout(forget_browser=True)

        self.assertFalse(profile_dir.exists())

    def test_successful_login_closes_persistent_edge_context(self):
        credentials = Credentials.create(
            profile="dev",
            cookie="complete-cookie",
            csrftoken="csrf-token",
            username="jack",
            ttl_seconds=1800,
        )
        context = FakePersistentContext()
        fake_playwright = FakePlaywright(context)
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.TimeoutError = TimeoutError
        sync_api.sync_playwright = lambda: FakePlaywrightManager(fake_playwright)
        playwright_package = types.ModuleType("playwright")
        playwright_package.sync_api = sync_api
        authenticator = BrowserAuthenticator(self.store)
        authenticator._capture_credentials = lambda **_: credentials
        profile_dir = self.config.browser_profile_dir("dev")

        with patch.dict(
            sys.modules,
            {
                "playwright": playwright_package,
                "playwright.sync_api": sync_api,
            },
        ):
            result = authenticator.login(
                profile=Profile(
                    name="dev",
                    api_endpoint="https://dev.example.com/dashboard",
                ),
                timeout_ms=30000,
                ttl_seconds=1800,
                user_data_dir=profile_dir,
                browser_channel="msedge",
                session_probe_timeout_ms=5000,
            )

        self.assertEqual(result.username, "jack")
        self.assertTrue(context.closed)
        self.assertEqual(
            fake_playwright.launch_arguments,
            {
                "user_data_dir": str(profile_dir),
                "channel": "msedge",
                "headless": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
