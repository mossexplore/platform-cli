import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wisemlops_cli.config import (
    ConfigManager,
    _install_packaged_config,
    _sync_packaged_config,
    default_config_path,
)


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
                        "login_timeout": 120000,
                        "profile_root": str(Path(self.temporary.name) / "profiles"),
                    },
                    "profiles": [
                        {
                            "name": "dev",
                            "api_endpoint": "https://dev.example.com/dashboard",
                            "output_format": "json",
                            "verify_ssl": False,
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
        self.assertFalse(manager.current_profile().verify_ssl)
        self.assertFalse(manager.verify_ssl)
        self.assertEqual(manager.auth_ttl_seconds, 60)
        self.assertEqual(manager.browser_channel, "msedge")
        self.assertEqual(manager.session_probe_timeout_ms, 2500)
        self.assertEqual(manager.login_timeout_ms, 120000)
        self.assertEqual(
            manager.browser_profile_dir("dev"),
            (Path(self.temporary.name) / "profiles").resolve() / "profile-dev",
        )

    def test_switches_and_persists_profile(self):
        manager = ConfigManager(self.path)
        manager.use_profile("test")
        reloaded = ConfigManager(self.path)
        self.assertEqual(reloaded.current_name, "test")
        self.assertTrue(reloaded.verify_ssl)

    def test_installs_packaged_config(self):
        destination = Path(self.temporary.name) / "ml" / "config.json"

        _install_packaged_config(destination)

        self.assertTrue(destination.exists())
        manager = ConfigManager(destination)
        self.assertEqual(manager.current_name, "dev")
        self.assertEqual(
            manager.current_profile().api_endpoint,
            "https://console-dev.cloudtest.cn/dashboard",
        )

    def test_default_path_bootstraps_user_config(self):
        root = Path(self.temporary.name)
        with patch.dict(
            os.environ,
            {"ML_CONFIG": ""},
        ):
            with patch(
                "wisemlops_cli.config.Path.cwd",
                return_value=root / "working-directory",
            ):
                with patch(
                    "wisemlops_cli.config.user_config_dir",
                    return_value=root / "ml",
                ):
                    path = default_config_path()

        self.assertEqual(path, root / "ml" / "config.json")
        self.assertTrue(path.exists())
        self.assertEqual(ConfigManager(path).current_name, "dev")

    def test_new_install_overwrites_config_once(self):
        destination = Path(self.temporary.name) / "ml" / "config.json"
        destination.parent.mkdir(parents=True)
        destination.write_text('{"current": "old"}\n', encoding="utf-8")

        _sync_packaged_config(destination)

        self.assertEqual(ConfigManager(destination).current_name, "dev")
        manager = ConfigManager(destination)
        manager.use_profile("test")

        _sync_packaged_config(destination)
        self.assertEqual(ConfigManager(destination).current_name, "test")

        with patch("wisemlops_cli.config.__version__", "0.3.19"):
            _sync_packaged_config(destination)
        self.assertEqual(ConfigManager(destination).current_name, "dev")


if __name__ == "__main__":
    unittest.main()
