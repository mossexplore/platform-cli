import re
import contextlib
import io
import json
import tempfile
import unittest
from importlib.metadata import PackageNotFoundError
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile


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

    def test_installer_reads_actual_wheel_and_environment_versions(self):
        script = (self.windows_scripts / "install.ps1").read_text(encoding="utf-8")
        check = script.split("$VersionCheck = @'\n", 1)[1].split("\n'@", 1)[0]
        with tempfile.TemporaryDirectory() as directory:
            wheel = Path(directory) / "wisemlops_cli.whl"
            with ZipFile(wheel, "w") as archive:
                archive.writestr(
                    "wisemlops_cli-0.3.33.dist-info/METADATA",
                    "Name: wisemlops-cli\nVersion: 0.3.33\n",
                )
            for installed in (None, "0.3.32", "0.3.33", "0.3.34"):
                with self.subTest(installed=installed):
                    output = io.StringIO()
                    with patch("sys.argv", ["-c", str(wheel)]), patch(
                        "importlib.metadata.version",
                        return_value=installed,
                        side_effect=PackageNotFoundError if installed is None else None,
                    ) as read_version, contextlib.redirect_stdout(output):
                        exec(check, {})
                    read_version.assert_called_once_with("wisemlops-cli")
                    self.assertEqual(
                        json.loads(output.getvalue()),
                        {"target": "0.3.33", "installed": installed},
                    )

    def test_installer_skips_matching_versions_without_forcing_dependencies(self):
        script = (self.windows_scripts / "install.ps1").read_text(encoding="utf-8")
        self.assertIn("$VersionOutput = & $VirtualEnvironmentPython -c $VersionCheck $WheelPath", script)
        self.assertIn("-not $Force -and\n    $Versions.installed -eq $Versions.target", script)
        self.assertIn("if ($SkipPackageInstall)", script)
        self.assertNotIn("--force-reinstall", script)
        self.assertIn("if ($Force -and (Test-Path -LiteralPath $VirtualEnvironment))", script)


if __name__ == "__main__":
    unittest.main()
