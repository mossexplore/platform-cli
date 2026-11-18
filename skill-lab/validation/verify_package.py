"""Verify the formal Skill in real Wheel/sdist builds and exclude the lab."""
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
CLI = ROOT / 'cli-python'
PREFIX = 'wiserec_cli/opencode_resources/'


def run(args, cwd, env=None):
    result = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout.strip()


def expected_resources():
    expected = {'commands/ml.md': ROOT / 'skill/commands/ml.md'}
    directory = ROOT / 'skill/wiserec-platform'
    for path in [directory / 'SKILL.md', *sorted((directory / 'references').rglob('*.md'))]:
        expected[f'skills/{directory.name}/{path.relative_to(directory).as_posix()}'] = path
    return expected


def check_wheel(wheel, expected, version):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert not any('skill-lab/' in n or 'ml-lab.md' in n or '.DS_Store' in n for n in names)
        manifest = json.loads(archive.read(PREFIX + 'manifest.json'))
        assert set(manifest) == set(expected)
        assert {n[len(PREFIX):] for n in names if n.startswith(PREFIX)} == set(expected) | {'manifest.json'}
        for name, source in expected.items():
            data = archive.read(PREFIX + name)
            if source.name == 'SKILL.md':
                source_hashes = {target: hashlib.sha256(path.read_bytes()).hexdigest()
                                 for target, path in expected.items()}
                digest = hashlib.sha256(json.dumps(
                    source_hashes, sort_keys=True, separators=(',', ':')
                ).encode('utf-8')).hexdigest()
                stamp = f'\nmetadata:\n  source_cli_version: "{version}"\n  source_sha256: "{digest}"\n'
                assert data.decode('utf-8') == source.read_text(encoding='utf-8').replace(
                    '\nmetadata:\n', stamp, 1)
            else:
                assert data == source.read_bytes(), name
            assert hashlib.sha256(data).hexdigest() == manifest[name], name
        metadata, = [n for n in names if n.endswith('.dist-info/METADATA')]
        assert BytesParser().parsebytes(archive.read(metadata))['Version'] == version
        assert f'__version__ = "{version}"' in archive.read('wiserec_cli/__init__.py').decode()
        return manifest


def main():
    version = re.search(r'^version = "([^"]+)"', (CLI / 'pyproject.toml').read_text(), re.M)[1]
    expected = expected_resources()
    with tempfile.TemporaryDirectory(prefix='wiserec-skill-bundle-') as temporary:
        temporary = Path(temporary)
        checkout = temporary / 'checkout'
        project = checkout / 'cli-python'
        shutil.copytree(CLI, project, ignore=shutil.ignore_patterns(
            'config.json', '__pycache__', '*.egg-info', '.DS_Store', '.venv', 'build', 'dist'))
        shutil.copy2(project / 'config.example.json', project / 'config.json')
        shutil.copytree(ROOT / 'skill', checkout / 'skill')
        for name in ('versions.toml', 'scripts/sync_versions.py', 'docs/Jupyter本地开发指南.md'):
            target = checkout / name
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
            assert not any('skill-lab/' in n or 'ml-lab.md' in n or '.DS_Store' in n for n in names)
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
            for relative in expected:
                assert (destination / relative).read_bytes() == (resource_root / relative).read_bytes()
        print(f'PASS: {len(expected)} resources in Wheel/sdist and rebuilt Wheel; validation excluded')
        print(f'PASS: installed ml --version = {version}; both isolated agent directories match source')
        print('Windows ZIP installation and live agent invocation are not exercised here')


if __name__ == '__main__':
    main()
