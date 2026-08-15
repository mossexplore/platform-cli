import json
import sys
import tempfile
import types
import unittest
from collections import deque
from pathlib import Path
from unittest.mock import Mock, patch

from wisemlops_cli.auth import AuthManager, BrowserAuthenticator, _parse_user_info
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

    def goto(self, *_args, **_kwargs):
        return None


class FakePersistentContext:
    def __init__(self):
        self.pages = [FakePage()]
        self.closed = False
        self.listeners = {}

    def on(self, event, callback):
        self.listeners[event] = callback

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


class FakeResponse:
    ok = True

    def text(self):
        return json.dumps(
            {
                "result": {
                    "code": 0,
                    "des": "success",
                    "username": "123456",
                    "department": "技术部",
                    "cnName": "张三",
                }
            }
        )


class FakeRequestClient:
    def __init__(self):
        self.headers = None

    def get(self, _url, headers, timeout):
        self.headers = headers
        self.timeout = timeout
        return FakeResponse()


class FakeCredentialContext:
    def __init__(self):
        self.request = FakeRequestClient()
        self.pages = []

    def cookies(self, _url):
        return [
            {"name": "session", "value": "complete-session-cookie-value"},
            {"name": "route", "value": "backend-01"},
        ]


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
            cn_name="张三",
            department="技术部",
        )
        context = FakePersistentContext()
        fake_playwright = FakePlaywright(context)
        sync_api = types.ModuleType("playwright.sync_api")
        sync_api.TimeoutError = TimeoutError
        sync_api.sync_playwright = lambda: FakePlaywrightManager(fake_playwright)
        playwright_package = types.ModuleType("playwright")
        playwright_package.sync_api = sync_api
        authenticator = BrowserAuthenticator(self.store)
        authenticator._wait_for_credentials = Mock(
            side_effect=[None, credentials]
        )
        profile_dir = self.config.browser_profile_dir("dev")

        with patch.dict(
            sys.modules,
            {
                "playwright": playwright_package,
                "playwright.sync_api": sync_api,
            },
        ):
            with patch(
                "builtins.input",
                side_effect=AssertionError("不应等待回车"),
            ):
                with patch("builtins.print") as print_mock:
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
                        login_timeout_ms=300000,
                    )

        self.assertEqual(result.username, "jack")
        print_mock.assert_any_call("正在等待登录成功...")
        print_mock.assert_any_call("账号: jack")
        print_mock.assert_any_call("中文名: 张三")
        print_mock.assert_any_call("部门: 技术部")
        self.assertTrue(context.closed)
        self.assertEqual(authenticator._wait_for_credentials.call_count, 2)
        self.assertEqual(
            authenticator._wait_for_credentials.call_args_list[0].kwargs[
                "wait_timeout_ms"
            ],
            5000,
        )
        self.assertEqual(
            authenticator._wait_for_credentials.call_args_list[1].kwargs[
                "wait_timeout_ms"
            ],
            300000,
        )
        self.assertEqual(
            fake_playwright.launch_arguments,
            {
                "user_data_dir": str(profile_dir),
                "channel": "msedge",
                "headless": False,
            },
        )

    def test_automatic_capture_keeps_full_cookie_and_request_csrftoken(self):
        context = FakeCredentialContext()
        authenticator = BrowserAuthenticator(self.store)
        credentials = authenticator._wait_for_credentials(
            context=context,
            profile=Profile(
                name="dev",
                api_endpoint="https://dev.example.com/dashboard",
            ),
            user_info_url="https://dev.example.com/ai/user/info",
            ttl_seconds=1800,
            request_timeout_ms=30000,
            wait_timeout_ms=1000,
            captured_headers=deque(
                [{"CSRFToken": "independent-request-token"}]
            ),
        )

        self.assertIsNotNone(credentials)
        self.assertEqual(
            credentials.cookie,
            "session=complete-session-cookie-value; route=backend-01",
        )
        self.assertEqual(credentials.csrftoken, "independent-request-token")
        self.assertEqual(credentials.username, "123456")
        self.assertEqual(credentials.cn_name, "张三")
        self.assertEqual(credentials.department, "技术部")
        self.assertEqual(
            context.request.headers["cookie"],
            "session=complete-session-cookie-value; route=backend-01",
        )
        self.assertEqual(
            context.request.headers["csrftoken"],
            "independent-request-token",
        )

    def test_user_info_requires_success_result_code(self):
        self.assertIsNone(
            _parse_user_info(
                {
                    "result": {
                        "code": 1,
                        "des": "failed",
                        "username": "123456",
                        "department": "技术部",
                        "cnName": "张三",
                    }
                }
            )
        )


if __name__ == "__main__":
    unittest.main()
