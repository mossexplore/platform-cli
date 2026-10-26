"""校验构建产物内的版本，不导入开发环境或执行包内源码。"""
import io
from pathlib import Path
import runpy
import subprocess
import sys
from zipfile import ZipFile

import pytest


CHECKER = Path(__file__).resolve().parents[1] / "scripts/releasing/check-cli-package.py"
check = runpy.run_path(str(CHECKER))["check"]


def wheel_bytes(metadata_version="9.8.7", code_version="9.8.7", source=None):
    result = io.BytesIO()
    with ZipFile(result, "w") as wheel:
        wheel.writestr("wiserec_cli-9.8.7.dist-info/METADATA",
                       f"Name: wiserec-cli\nVersion: {metadata_version}\n")
        wheel.writestr("wiserec_cli/__init__.py", source or f'__version__ = "{code_version}"\n')
    return result.getvalue()


def test_matching_wheel_and_bundled_dependency_versions(tmp_path):
    dependency = io.BytesIO()
    with ZipFile(dependency, "w") as wheel:
        wheel.writestr("dependency-1.0.dist-info/METADATA", "Name: dependency\nVersion: 1.0\n")
    bundle = tmp_path / "online.zip"
    with ZipFile(bundle, "w") as archive:
        archive.writestr("bundle/wiserec_cli-9.8.7-py3-none-any.whl", wheel_bytes())
        archive.writestr("bundle/packages/dependency-1.0-py3-none-any.whl", dependency.getvalue())
    assert check(bundle, expected_version="9.8.7") == 1


@pytest.mark.parametrize("options", [
    {"metadata_version": "0.0.1"}, {"code_version": "0.0.1"},
    {"source": "# missing version\n"},
    {"source": "__version__ = '9.8.7'\n__version__ = '0.0.1'\n"},
])
def test_rejects_drift_before_installation(options):
    with pytest.raises(ValueError, match="版本不一致"):
        check("wiserec_cli-9.8.7-py3-none-any.whl", wheel_bytes(**options), expected_version="9.8.7")


def test_version_inspection_does_not_execute_code(tmp_path):
    marker = tmp_path / "should-not-exist"
    source = f"__version__ = '9.8.7'\nopen({str(marker)!r}, 'w').write('executed')\n"
    assert check("wiserec_cli-9.8.7-py3-none-any.whl", wheel_bytes(source=source),
                 expected_version="9.8.7") == 1
    assert not marker.exists()


def test_cli_expected_version_requires_an_actual_cli_wheel(tmp_path):
    bundle = tmp_path / "empty.zip"
    with ZipFile(bundle, "w") as archive:
        archive.writestr("INSTALL.md", "missing CLI")
    result = subprocess.run([sys.executable, "-I", str(CHECKER), "--expected-version", "9.8.7", str(bundle)],
                            capture_output=True, timeout=20)
    assert result.returncode != 0


def test_cli_expected_version_accepts_valid_wheel(tmp_path):
    wheel = tmp_path / "wiserec_cli-9.8.7-py3-none-any.whl"
    wheel.write_bytes(wheel_bytes())
    result = subprocess.run([sys.executable, "-I", str(CHECKER), "--expected-version", "9.8.7", str(wheel)],
                            capture_output=True, timeout=20)
    assert result.returncode == 0, result.stderr
