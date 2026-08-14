import json
import tempfile
import unittest
from pathlib import Path

from wisemlops_cli.config import ConfigManager


class ConfigManagerTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "config.json"
        self.path.write_text(
            json.dumps(
                {
                    "current": "dev",
                    "api": {
                        "timeout": 10000,
                        "retry_times": 2,
                        "verify_ssl": True,
                    },
                    "auth": {"expires_in_seconds": 60},
                    "browser": {
                        "channel": "msedge",
                        "session_probe_timeout": 2500,
                        "profile_root": str(Path(self.temporary.name) / "profiles"),
                    },
                    "profiles": [
                        {
                            "name": "dev",
                            "api_endpoint": "https://dev.example.com/dashboard",
                            "output_format": "json",
                        },
                        {
                            "name": "test",
                            "api_endpoint": "https://test.example.com/dashboard",
                            "output_format": "table",
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_loads_current_profile_and_auth_ttl(self):
        manager = ConfigManager(self.path)
        self.assertEqual(manager.current_profile().name, "dev")
        self.assertEqual(manager.current_profile().base_url, "https://dev.example.com")
        self.assertEqual(manager.auth_ttl_seconds, 60)
        self.assertEqual(manager.browser_channel, "msedge")
        self.assertEqual(manager.session_probe_timeout_ms, 2500)
        self.assertEqual(
            manager.browser_profile_dir("dev"),
            (Path(self.temporary.name) / "profiles").resolve() / "profile-dev",
        )

    def test_switches_and_persists_profile(self):
        manager = ConfigManager(self.path)
        manager.use_profile("test")
        reloaded = ConfigManager(self.path)
        self.assertEqual(reloaded.current_name, "test")


if __name__ == "__main__":
    unittest.main()
