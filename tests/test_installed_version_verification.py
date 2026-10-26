"""实际执行安装器内嵌验收代码，覆盖版本漂移及源码覆盖。"""
import json
import os
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "scripts/windows/install.ps1").read_text(encoding="utf-8")
VERIFY = INSTALLER.split("$VerifyInstalledPackage = @'\n", 1)[1].split("\n'@", 1)[0]


def check_installation(tmp_path, *, metadata_version="9.8.7", code_version="9.8.7",
                       release_version="9.8.7", editable=False, shadow=False, duplicate=False):
    prefix = tmp_path / "venv"
    packages = prefix / "Lib/site-packages"
    module = packages / "wiserec_cli/__init__.py"
    module.parent.mkdir(parents=True)
    module.write_text(f'__version__ = "{code_version}"\n', encoding="utf-8")
    dist = packages / f"wiserec_cli-{metadata_version}.dist-info"
    dist.mkdir()
    dist.joinpath("METADATA").write_text(
        f"Name: wiserec-cli\nVersion: {metadata_version}\n", encoding="utf-8"
    )
    if editable:
        dist.joinpath("direct_url.json").write_text(json.dumps({"dir_info": {"editable": True}}))
    if duplicate:
        second = packages / "wiserec_cli-0.0.1.dist-info"
        second.mkdir()
        second.joinpath("METADATA").write_text("Name: wiserec-cli\nVersion: 0.0.1\n")
    wheel_path = tmp_path / "wiserec_cli-9.8.7-py3-none-any.whl"
    with ZipFile(wheel_path, "w") as wheel:
        wheel.writestr("wiserec_cli-9.8.7.dist-info/METADATA", "Name: wiserec-cli\nVersion: 9.8.7\n")
    (tmp_path / "release.json").write_text(json.dumps({"version": release_version}))
    source = tmp_path / "source"
    (source / "wiserec_cli").mkdir(parents=True)
    (source / "wiserec_cli/__init__.py").write_text('__version__ = "9.8.7"\n')
    paths = [str(source), str(packages)] if shadow else [str(packages)]
    bootstrap = (
        "import sys\n"
        f"sys.path[:0] = {paths!r}\n"
        f"sys.prefix = {str(prefix)!r}\n"
        # Exclude other CLI installations, while retaining the stdlib.
        "sys.path[:] = [p for p in sys.path if 'site-packages' not in p or p in " + repr(paths) + "]\n"
    )
    env = dict(os.environ, PYTHONPATH=str(source))
    return subprocess.run(
        [sys.executable, "-I", "-S", "-c", bootstrap + VERIFY, str(wheel_path)],
        capture_output=True, text=True, env=env, cwd=source, timeout=20,
    )


def test_accepts_matching_versions_and_ignores_pythonpath_and_cwd(tmp_path):
    result = check_installation(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "Verified Wheel / metadata / imported CLI: 9.8.7" in result.stdout
    assert "site-packages" in result.stdout


@pytest.mark.parametrize("options,reason", [
    ({"metadata_version": "0.0.1"}, "versions differ"),
    ({"code_version": "0.0.1"}, "versions differ"),
    ({"release_version": "0.0.1"}, "release.json version differs"),
    ({"editable": True}, "editable installation detected"),
    ({"shadow": True}, "outside the installed package"),
    ({"duplicate": True}, "exactly one installed"),
])
def test_rejects_inconsistent_or_ambiguous_installation(tmp_path, options, reason):
    result = check_installation(tmp_path, **options)
    assert result.returncode != 0
    assert reason in result.stderr


def test_verification_precedes_config_updates_and_launcher_is_isolated():
    assert INSTALLER.index('"-I", "-c", $VerifyInstalledPackage') < INSTALLER.index(
        'Write-Host "Updating user config.json'
    )
    assert 'python.exe" -I -c "import sys; sys.argv[0]=\'ml\'' in INSTALLER
