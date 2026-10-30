"""Verify both skills in real Wheel/sdist builds; keep validation tools out."""
from email.parser import BytesParser
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PREFIX = 'wiserec_cli/opencode_resources/'


def run(args, cwd, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def expected_resources():
    expected = {}
    for name in ('ml', 'ml-lab'):
        expected[f'commands/{name}.md'] = ROOT / f'skill/commands/{name}.md'
    for relative in ('skill/wiserec-platform', 'skill-lab/wiserec-platform-detailed'):
        directory = ROOT / relative
        for path in [directory / 'SKILL.md', *sorted((directory / 'references').rglob('*.md'))]:
            expected[f'skills/{directory.name}/{path.relative_to(directory).as_posix()}'] = path
    return expected


def check_wheel(wheel, expected, version):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any('validation/' in n or '.DS_Store' in n for n in names)
        manifest = json.loads(archive.read(PREFIX + 'manifest.json'))
        assert set(manifest) == set(expected)
        assert {n[len(PREFIX):] for n in names if n.startswith(PREFIX)} == set(expected) | {'manifest.json'}
        for name, source in expected.items():
            data = archive.read(PREFIX + name)
            assert data == source.read_bytes(), name
            assert hashlib.sha256(data).hexdigest() == manifest[name], name
        metadata, = [n for n in names if n.endswith('.dist-info/METADATA')]
        assert BytesParser().parsebytes(archive.read(metadata))['Version'] == version
        assert f'__version__ = "{version}"' in archive.read('wiserec_cli/__init__.py').decode()
        return manifest


def main():
    version = re.search(r'^version = "([^"]+)"', (ROOT / 'pyproject.toml').read_text(), re.M)[1]
    expected = expected_resources()
    with tempfile.TemporaryDirectory(prefix='wiserec-skill-bundle-') as temporary:
        temporary = Path(temporary)
        project = temporary / 'project'
        project.mkdir()
        for name in ('setup.py', 'pyproject.toml', 'MANIFEST.in', 'config.json', 'versions.toml'):
            shutil.copy2(ROOT / name, project / name)
        for name in ('src', 'skill', 'skill-lab'):
            shutil.copytree(ROOT / name, project / name,
                ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', '.DS_Store'))
        for name in ('scripts/jupyter_local.py', 'scripts/sync_versions.py', 'examples/jupyter/hello.ipynb',
                     'docs/Jupyter本地开发指南.md'):
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        run([sys.executable, 'setup.py', 'sdist', 'bdist_wheel'], project)
        wheel, = (project / 'dist').glob('*.whl')
        sdist, = (project / 'dist').glob('*.tar.gz')
        manifest = check_wheel(wheel, expected, version)
        extracted = temporary / 'extracted'
        extracted.mkdir()
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            assert not any('validation/' in n or '.DS_Store' in n for n in names)
            for source in expected.values():
                assert any(n.endswith('/' + source.relative_to(ROOT).as_posix()) for n in names), source
            # Copy only regular files/directories, also on supported Python 3.9.
            for member in archive.getmembers():
                relative = Path(member.name)
                assert not relative.is_absolute() and '..' not in relative.parts
                target = extracted / relative
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    assert member.isfile(), member.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, target.open('wb') as destination:
                        shutil.copyfileobj(source, destination)
        source_project, = extracted.iterdir()
        run([sys.executable, 'setup.py', 'bdist_wheel'], source_project)
        rebuilt, = (source_project / 'dist').glob('*.whl')
        assert check_wheel(rebuilt, expected, version) == manifest
        installed = temporary / 'installed'
        run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
             '--target', str(installed), str(rebuilt)], temporary)
        env = dict(os.environ, PYTHONPATH=str(installed), PYTHONDONTWRITEBYTECODE='1')
        executable = installed / ('Scripts/ml.exe' if os.name == 'nt' else 'bin/ml')
        output = run([str(executable), '--version'], temporary, env)
        assert output == f'ml {version}', output
        # Install the built resources into isolated agent directories, never the user's real config.
        resource_root = installed / 'wiserec_cli/opencode_resources'
        for agent in ('opencode', 'cac'):
            destination = temporary / agent
            run([sys.executable, '-c',
                 'from pathlib import Path; from wiserec_cli.opencode_install import install_resources; '
                 'import sys; install_resources(Path(sys.argv[1]), Path(sys.argv[2]))',
                 str(destination), str(resource_root)], temporary, env)
            for relative, source in expected.items():
                assert (destination / relative).read_bytes() == source.read_bytes()
        print(f'PASS: {len(expected)} resources in Wheel/sdist and rebuilt Wheel; validation excluded')
        print(f'PASS: installed ml --version = {version}; both isolated agent directories match source')
        print('Windows ZIP installation and live agent invocation are not exercised here')


if __name__ == '__main__':
    main()
