import unittest
from pathlib import Path


class WindowsPackagingScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.windows_scripts = cls.root / "scripts" / "windows"

    def test_release_bundle_files_exist(self):
        for name in (
            "build-release.cmd",
            "build-release.ps1",
            "install.cmd",
            "install.ps1",
            "INSTALL.md",
        ):
            self.assertTrue((self.windows_scripts / name).is_file(), name)

    def test_build_script_supports_offline_and_online_bundles(self):
        script = (self.windows_scripts / "build-release.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[switch]$Online", script)
        self.assertIn('"-m", "pip", "download"', script)
        self.assertIn('"--only-binary=:all:"', script)
        self.assertIn('"CHECKSUMS.sha256"', script)
        self.assertIn('"release.json"', script)
        self.assertIn("struct.calcsize('P')*8", script)
        self.assertIn("Compress-Archive", script)

    def test_installer_uses_isolated_environment_and_user_path(self):
        script = (self.windows_scripts / "install.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn('"-m", "venv"', script)
        self.assertIn('"--no-index"', script)
        self.assertIn('"CHECKSUMS.sha256"', script)
        self.assertIn("$PythonArchitecture -ne $RequiredArchitecture", script)
        self.assertIn('"Microsoft\\Edge\\Application\\msedge.exe"', script)
        self.assertIn(
            '[Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")',
            script,
        )
        self.assertIn('Invoke-Checked -Command $VirtualEnvironmentMl', script)


if __name__ == "__main__":
    unittest.main()
