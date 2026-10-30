"""Single-source version updates survive independent component changes and packaging."""
from pathlib import Path
import runpy
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
SYNC = runpy.run_path(str(ROOT / 'scripts/sync_versions.py'))['sync']


def checkout(tmp_path):
    for name in ('versions.toml', 'pyproject.toml', 'src/wiserec_cli/__init__.py',
                 'access-service/VERSION', 'agent-service/pyproject.toml',
                 'permission-notifier/pyproject.toml'):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    (tmp_path / 'access-service/app').mkdir()
    (tmp_path / 'agent-service/app').mkdir()
    (tmp_path / 'permission-notifier/src/permission_notifier').mkdir(parents=True)
    return tmp_path


def test_repository_has_no_version_drift():
    assert SYNC(ROOT, check=True) == []


def test_independent_component_versions_and_read_only_check(tmp_path):
    root = checkout(tmp_path)
    (root / 'versions.toml').write_text('''[components]
cli = "2.3.4"
access = "5.6.7.8"
agent = "3.2.1"
notifier = "4.5.6"
[compatibility]
agent_cli = "2.3.4"
''')
    before = (root / 'pyproject.toml').read_bytes()
    with pytest.raises(ValueError, match='未同步'):
        SYNC(root, check=True)
    assert (root / 'pyproject.toml').read_bytes() == before
    SYNC(root)
    assert SYNC(root, check=True) == []
    assert runpy.run_path(str(root / 'src/wiserec_cli/__init__.py'))['__version__'] == '2.3.4'
    assert (root / 'access-service/VERSION').read_text().strip() == '5.6.7.8'
    assert runpy.run_path(str(root / 'access-service/app/_version.py'))['__version__'] == '5.6.7.8'
    agent = runpy.run_path(str(root / 'agent-service/app/_version.py'))
    assert agent['__version__'] == '3.2.1'
    assert agent['TESTED_CLI_VERSION'] == '2.3.4'
    assert runpy.run_path(str(root / 'permission-notifier/src/permission_notifier/__init__.py'))['__version__'] == '4.5.6'
    assert 'version = "3.2.1"' in (root / 'agent-service/pyproject.toml').read_text()
    assert 'version = "4.5.6"' in (root / 'permission-notifier/pyproject.toml').read_text()


def test_invalid_version_cannot_partially_update_files(tmp_path):
    root = checkout(tmp_path)
    manifest = root / 'versions.toml'
    manifest.write_text(manifest.read_text().replace('cli = "1.0.7.12"', 'cli = "bad"', 1))
    before = (root / 'pyproject.toml').read_bytes()
    with pytest.raises(ValueError, match='版本'):
        SYNC(root)
    assert (root / 'pyproject.toml').read_bytes() == before


@pytest.mark.parametrize('component', ['agent-service', 'permission-notifier'])
def test_build_hook_supports_standalone_source_without_root_manifest(tmp_path, component):
    project = tmp_path / component
    project.mkdir()
    for name in ('setup.py', 'pyproject.toml'):
        shutil.copy2(ROOT / component / name, project / name)
    # Running metadata preparation needs no repository manifest or CLI import.
    result = subprocess.run([sys.executable, 'setup.py', '--version'], cwd=project,
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().splitlines()[-1] == '1.0.7.12'
