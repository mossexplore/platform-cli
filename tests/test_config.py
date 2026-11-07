import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wiserec_cli.errors import ConfigError
from wiserec_cli.config import ConfigManager, default_config_path
from wiserec_cli.install_config import install_config, reset_packaged_config


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

    def test_runtime_reads_existing_user_config_without_package(self):
        root = Path(self.temporary.name)
        unrelated = root / "elsewhere"
        unrelated.mkdir()
        (unrelated / "config.json").write_text('{"current": "wrong"}')
        with patch.dict(os.environ, {"ML_CONFIG": str(unrelated / "config.json")}), \
             patch("wiserec_cli.config.Path.cwd", return_value=unrelated), \
             patch("wiserec_cli.config.user_config_dir", return_value=root), \
             patch("wiserec_cli.install_config.packaged_config_text", side_effect=AssertionError):
            self.assertEqual(default_config_path(), self.path)
            self.assertEqual(ConfigManager().current_name, "dev")

    def test_runtime_does_not_create_missing_user_config(self):
        self.path.unlink()
        with patch("wiserec_cli.config.user_config_dir", return_value=self.path.parent):
            with self.assertRaisesRegex(ConfigError, "配置文件不存在"):
                ConfigManager()
        self.assertFalse(self.path.exists())

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

    def test_installer_preserves_only_current_on_every_install(self):
        root = Path(self.temporary.name) / "user-config"
        template = self.path.read_text()
        with patch("wiserec_cli.install_config.user_config_dir", return_value=root), \
             patch("wiserec_cli.install_config.packaged_config_text", return_value=template):
            destination = reset_packaged_config()
            ConfigManager(destination).use_profile("test")
            expected = dict(json.loads(template), current="test")
            for _ in range(2):
                previous = json.loads(destination.read_text())
                previous["profiles"][1].update(api_endpoint="https://old.example.com",
                    platform_type="mlops", command_policy={"deny": ["jupyter files upload"]})
                previous["profiles"].append({"name": "local", "api_endpoint": "https://local.example"})
                previous["auth"] = {"auto_ping": False, "ping_interval_minutes": 15}
                previous["access_control"] = {"enabled": False, "url": "https://old.example"}
                previous["api"] = {"timeout": 1}
                previous["browser"] = {"channel": "chrome"}
                previous["local_only"] = True
                destination.write_text(json.dumps(previous))
                reset_packaged_config()
                self.assertEqual(json.loads(destination.read_text()), expected)

    def test_install_ignores_old_fields_except_current(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        template = self.path.read_text()
        # Old fields may be invalid or obsolete because they are all replaced.
        destination.write_text(json.dumps({"current": "test", "auth": "obsolete", "profiles": None}))
        with patch("wiserec_cli.install_config.packaged_config_text", return_value=template):
            install_config(destination)
        self.assertEqual(json.loads(destination.read_text()), dict(json.loads(template), current="test"))

    def test_invalid_local_config_uses_packaged_default(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        template = self.path.read_text()
        baseline = json.loads(template)
        for previous in ("not json", "[]", '{}',
                         json.dumps(dict(baseline, current=123)),
                         json.dumps(dict(baseline, current="unknown")),
                         json.dumps(dict(baseline, current=""))):
            with self.subTest(previous=previous), \
                 patch("wiserec_cli.install_config.packaged_config_text", return_value=template):
                destination.write_text(previous)
                install_config(destination)
                self.assertEqual(json.loads(destination.read_text()), baseline)
                self.assertEqual(ConfigManager(destination).current_name, baseline["current"])

    def test_missing_selected_environment_uses_packaged_default(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        baseline = json.loads(self.path.read_text())
        baseline["current"] = "test"
        template = json.dumps(baseline)
        destination.write_text(json.dumps({"current": "product", "profiles": [
            {"name": "product", "api_endpoint": "https://old.example"}]}))
        with patch("wiserec_cli.install_config.packaged_config_text", return_value=template):
            install_config(destination)
        self.assertEqual(json.loads(destination.read_text()), baseline)
        self.assertEqual(ConfigManager(destination).current_profile().name, "test")

    def test_changed_template_default_does_not_switch_existing_user(self):
        destination = Path(self.temporary.name) / "installed-config.json"
        template = self.path.read_text()
        with patch("wiserec_cli.install_config.packaged_config_text", return_value=template):
            install_config(destination)
        updated = json.loads(template)
        updated["current"] = "test"
        with patch("wiserec_cli.install_config.packaged_config_text", return_value=json.dumps(updated)):
            install_config(destination)
            self.assertEqual(ConfigManager(destination).current_name, "dev")
            fresh = destination.with_name("fresh.json")
            install_config(fresh)
            self.assertEqual(ConfigManager(fresh).current_name, "test")

    def test_invalid_candidate_does_not_replace_config(self):
        original = self.path.read_bytes()
        template = json.loads(original)
        template["api"]["verify_ssl"] = "invalid"
        with patch("wiserec_cli.install_config.packaged_config_text", return_value=json.dumps(template)):
            with self.assertRaises(ConfigError):
                install_config(self.path)
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
