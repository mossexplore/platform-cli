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
    for name in ('versions.toml', 'cli-python/pyproject.toml', 'cli-python/src/wiserec_cli/__init__.py',
                 'cli-go/go.mod', 'cli-go/cmd/ml/version.go',
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
cli_go = "2.3.5"
access = "5.6.7.8"
agent = "3.2.1"
notifier = "4.5.6"
[compatibility]
agent_cli = "2.3.4"
''')
    before = (root / 'cli-python/pyproject.toml').read_bytes()
    with pytest.raises(ValueError, match='未同步'):
        SYNC(root, check=True)
    assert (root / 'cli-python/pyproject.toml').read_bytes() == before
    SYNC(root)
    assert SYNC(root, check=True) == []
    assert runpy.run_path(str(root / 'cli-python/src/wiserec_cli/__init__.py'))['__version__'] == '2.3.4'
    assert 'const version = "2.3.5"' in (root / 'cli-go/cmd/ml/version.go').read_text()
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
    manifest.write_text(manifest.read_text().replace('cli = "1.0.9.6"', 'cli = "bad"', 1))
    before = (root / 'cli-python/pyproject.toml').read_bytes()
    with pytest.raises(ValueError, match='版本'):
        SYNC(root)
    assert (root / 'cli-python/pyproject.toml').read_bytes() == before


@pytest.mark.parametrize('go_version', ['1.0.9.7', '1.256.1', '1.0.65536', '01.0.10', '1.0.9'])
def test_go_version_must_fit_msi_and_differ_from_python(tmp_path, go_version):
    root = checkout(tmp_path)
    manifest = root / 'versions.toml'
    text = manifest.read_text().replace('cli = "1.0.9.6"', 'cli = "1.0.9.0"', 1)
    manifest.write_text(text.replace('cli_go = "1.0.10"', f'cli_go = "{go_version}"', 1))
    with pytest.raises(ValueError, match='Go CLI.*版本'):
        SYNC(root)


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
    assert result.stdout.strip().splitlines()[-1] == '1.0.9.1'
