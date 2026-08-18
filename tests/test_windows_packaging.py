import re
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
        ):
            self.assertTrue((self.windows_scripts / name).is_file(), name)
        doc = self.root / "docs" / "CLI Windows安装说明.md"
        self.assertTrue(doc.is_file(), doc)

    def test_build_script_supports_offline_and_online_bundles(self):
        script = (self.windows_scripts / "build-release.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("[switch]$Online", script)
        self.assertIn("[switch]$Offline", script)
        self.assertIn('[string]$IndexUrl = ""', script)
        self.assertTrue(script.startswith("#requires -Version 5.1\n"))
        self.assertIn('[string]$OutputDirectory = ""', script)
        self.assertIn(
            "$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path",
            script,
        )
        self.assertNotIn("Join-Path $PSScriptRoot", script)
        self.assertIn('"-m", "pip", "download"', script)
        self.assertIn('"--only-binary=:all:"', script)
        self.assertIn('"CHECKSUMS.sha256"', script)
        self.assertIn('"release.json"', script)
        self.assertIn('-windows-py3-online"', script)
        self.assertIn('$ReleaseMetadata["index_url"] = $IndexUrl', script)
        self.assertIn('"--no-isolation"', script)
        self.assertIn("struct.calcsize('P')*8", script)
        self.assertIn("Compress-Archive", script)
        self.assertIn("Assert-RequiredCommand -Name $RequiredCommand", script)

    def test_installer_uses_isolated_environment_and_user_path(self):
        script = (self.windows_scripts / "install.ps1").read_text(
            encoding="utf-8"
        )

        self.assertTrue(script.startswith("#requires -Version 5.1\n"))
        self.assertIn('[string]$InstallDirectory = ""', script)
        self.assertIn('[string]$IndexUrl = ""', script)
        self.assertIn('[string]$Cert = ""', script)
        self.assertIn(
            "$ScriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path",
            script,
        )
        self.assertNotIn("Join-Path $PSScriptRoot", script)
        self.assertIn('"-m", "venv"', script)
        self.assertIn('"--no-index"', script)
        self.assertIn('@("--index-url", $EffectiveIndexUrl)', script)
        self.assertIn('@("--cert", $ResolvedCert)', script)
        self.assertIn('$env:PIP_INDEX_URL', script)
        self.assertIn('"CHECKSUMS.sha256"', script)
        self.assertIn("$($LASTEXITCODE): $Command", script)
        self.assertNotIn("$LASTEXITCODE: $Command", script)
        self.assertIn("$PythonArchitecture -ne $RequiredArchitecture", script)
        self.assertIn('"Microsoft\\Edge\\Application\\msedge.exe"', script)
        self.assertIn(
            '[Environment]::SetEnvironmentVariable("Path", $NewUserPath, "User")',
            script,
        )
        self.assertIn('Invoke-Checked -Command $VirtualEnvironmentMl', script)

    def test_scripts_avoid_newer_or_ambiguous_powershell_syntax(self):
        ambiguous_variable = re.compile(
            r'\$(?!(?:env|script|global|local|private):)'
            r'[A-Za-z_][A-Za-z0-9_]*:'
        )
        powershell_7_only_tokens = ("??", "?.", "&&", "||")

        for path in self.windows_scripts.glob("*.ps1"):
            script = path.read_text(encoding="utf-8")
            for line_number, line in enumerate(script.splitlines(), start=1):
                if '"' in line and ambiguous_variable.search(line):
                    self.fail(
                        f"{path.name}:{line_number} contains an ambiguous "
                        "variable followed by a colon"
                    )
            for token in powershell_7_only_tokens:
                self.assertNotIn(token, script, f"{path.name}: {token}")


if __name__ == "__main__":
    unittest.main()
