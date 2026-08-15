import json
import tempfile
import unittest
from pathlib import Path

from typer.testing import CliRunner

from wisemlops_cli.cli import app


class CliEnvironmentCommandTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.config_path = Path(self.temporary.name) / "config.json"
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
        self.runner = CliRunner()

    def tearDown(self):
        self.temporary.cleanup()

    def test_env_show_is_available(self):
        result = self.runner.invoke(
            app,
            ["--config", str(self.config_path), "env", "show"],
        )

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("dev", result.output)
        self.assertIn("https://dev.example.com/dashboard", result.output)

    def test_profile_command_is_no_longer_available(self):
        result = self.runner.invoke(
            app,
            ["--config", str(self.config_path), "profile", "show"],
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("No such command", result.output)

    def test_version_is_0_3_7(self):
        result = self.runner.invoke(app, ["--version"])

        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("ml 0.3.7", result.output)


if __name__ == "__main__":
    unittest.main()
