import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wiserec_cli.errors import ConfigError
from wiserec_cli.access import access_enabled
from wiserec_cli.config import (
    ConfigManager,
    _install_packaged_config,
    _sync_packaged_config,
    default_config_path,
    reset_packaged_config,
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
                        "business_catalog_timeout": 15000,
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
        self.assertTrue(manager.auto_ping)
        self.assertEqual(manager.ping_interval_minutes, 10)
        self.assertEqual(manager.browser_channel, "msedge")
        self.assertEqual(manager.session_probe_timeout_ms, 2500)
        self.assertEqual(manager.login_timeout_ms, 120000)
        self.assertEqual(manager.business_catalog_timeout_ms, 15000)
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
        self.assertNotIn("enable", manager.access_control)
        self.assertNotIn("enabled", manager.access_control)
        self.assertTrue(access_enabled(manager.access_control))
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
                "wiserec_cli.config.Path.cwd",
                return_value=root / "working-directory",
            ):
                with patch(
                    "wiserec_cli.config.user_config_dir",
                    return_value=root / "ml",
                ):
                    path = default_config_path()

        self.assertEqual(path, root / "ml" / "config.json")
        self.assertTrue(path.exists())
        self.assertEqual(ConfigManager(path).current_name, "dev")

    def test_package_upgrade_preserves_selected_environment(self):
        destination = Path(self.temporary.name) / "ml" / "config.json"

        _sync_packaged_config(destination)

        self.assertEqual(ConfigManager(destination).current_name, "dev")
        manager = ConfigManager(destination)
        manager.use_profile("test")

        _sync_packaged_config(destination)
        self.assertEqual(ConfigManager(destination).current_name, "test")

        with patch("wiserec_cli.config.__version__", "999.0.0"):
            _sync_packaged_config(destination)
        self.assertEqual(ConfigManager(destination).current_name, "test")

    def test_package_update_preserves_manual_ping_settings(self):
        destination = Path(self.temporary.name) / "ml" / "config.json"
        _sync_packaged_config(destination)
        user_config = json.loads(destination.read_text(encoding="utf-8"))
        user_config["auth"].update(auto_ping=False, ping_interval_minutes=15)
        destination.write_text(json.dumps(user_config), encoding="utf-8")

        with patch("wiserec_cli.config.__version__", "999.0.0"):
            _sync_packaged_config(destination)
        manager = ConfigManager(destination)
        self.assertFalse(manager.auto_ping)
        self.assertEqual(manager.ping_interval_minutes, 15)

    def test_ping_settings_reject_invalid_values(self):
        baseline = json.loads(self.path.read_text(encoding="utf-8"))
        for settings in ({"auto_ping": "false"}, {"ping_interval_minutes": 0},
                         {"ping_interval_minutes": 21}, {"ping_interval_minutes": 10.5}):
            with self.subTest(settings=settings):
                config = json.loads(json.dumps(baseline))
                config["auth"].update(settings)
                self.path.write_text(json.dumps(config), encoding="utf-8")
                with self.assertRaisesRegex(Exception, "auth\\.(auto_ping|ping_interval_minutes)"):
                    ConfigManager(self.path)

    def test_installer_preserves_selection_but_updates_other_settings(self):
        root = Path(self.temporary.name) / "user-config"
        template = self.path.read_text()
        with patch("wiserec_cli.config.user_config_dir", return_value=root), \
             patch("wiserec_cli.config._packaged_config_text", return_value=template):
            destination = reset_packaged_config()
            ConfigManager(destination).use_profile("test")
            previous = json.loads(destination.read_text())
            previous["profiles"][1]["api_endpoint"] = "https://old.example.com"
            destination.write_text(json.dumps(previous))
            reset_packaged_config()
            manager = ConfigManager(destination)
            self.assertEqual(manager.current_name, "test")
            self.assertEqual(manager.current_profile().api_endpoint,
                             "https://test.example.com/dashboard")

    def test_failed_sync_preserves_config_and_marker(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        marker = destination.with_name(".installed-config.json.installed")
        template = self.path.read_text()
        with patch("wiserec_cli.config._packaged_config_text", return_value=template):
            _sync_packaged_config(destination)
            original_marker = marker.read_bytes()
            baseline = json.loads(template)
            missing = dict(baseline, current="removed")
            missing["profiles"] = baseline["profiles"] + [{
                "name": "removed", "api_endpoint": "https://removed.example.com"}]
            for previous in ("not json", "[]", '{}',
                             json.dumps(dict(baseline, current=123)),
                             json.dumps(dict(baseline, current="unknown")),
                             json.dumps(missing)):
                with self.subTest(previous=previous):
                    destination.write_text(previous)
                    with self.assertRaises(ConfigError):
                        _sync_packaged_config(destination, force=True)
                    self.assertEqual(destination.read_text(), previous)
                    self.assertEqual(marker.read_bytes(), original_marker)

    def test_same_version_reinstall_preserves_selection(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        template = self.path.read_text()
        with patch("wiserec_cli.config._packaged_config_text", return_value=template):
            with patch("wiserec_cli.config._package_install_stamp", return_value="install-1"):
                _sync_packaged_config(destination)
                ConfigManager(destination).use_profile("test")
                before = destination.read_bytes()
                _sync_packaged_config(destination)
                self.assertEqual(destination.read_bytes(), before)
            with patch("wiserec_cli.config._package_install_stamp", return_value="install-2"):
                _sync_packaged_config(destination)
                self.assertEqual(ConfigManager(destination).current_name, "test")

    def test_changed_template_default_does_not_switch_existing_user(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        template = self.path.read_text()
        with patch("wiserec_cli.config._packaged_config_text", return_value=template):
            _sync_packaged_config(destination)
        updated = json.loads(template)
        updated["current"] = "test"
        with patch("wiserec_cli.config._packaged_config_text", return_value=json.dumps(updated)):
            _sync_packaged_config(destination)
            self.assertEqual(ConfigManager(destination).current_name, "dev")
            fresh = destination.with_name("fresh.json")
            _sync_packaged_config(fresh)
            self.assertEqual(ConfigManager(fresh).current_name, "test")

    def test_invalid_candidate_does_not_replace_config(self):
        original = self.path.read_bytes()
        template = json.loads(original)
        template["api"]["verify_ssl"] = "invalid"
        with patch("wiserec_cli.config._packaged_config_text", return_value=json.dumps(template)):
            with self.assertRaises(ConfigError):
                _sync_packaged_config(self.path, force=True)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.path.with_name(".config.json.installed").exists())

    def test_profile_alias_is_optional_and_validated(self):
        data = json.loads(self.path.read_text())
        self.assertEqual(ConfigManager(self.path).current_profile().alias, 'dev')
        data['profiles'][0]['alias'] = '开发环境'
        self.path.write_text(json.dumps(data))
        self.assertEqual(ConfigManager(self.path).current_profile().alias, '开发环境')
        for invalid in ('', '   ', None, 123):
            data['profiles'][0]['alias'] = invalid
            self.path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ConfigError, 'profile.alias'):
                ConfigManager(self.path)


if __name__ == "__main__":
    unittest.main()
