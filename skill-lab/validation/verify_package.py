"""Build isolated Wheel/sdist and verify the lab never enters CLI resources."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
LAB_NAME = 'wiserec-platform-detailed'


def main():
    with tempfile.TemporaryDirectory(prefix='wiserec-skill-isolation-') as temporary:
        project = Path(temporary) / 'project'
        project.mkdir()
        for name in ('setup.py', 'pyproject.toml', 'MANIFEST.in', 'config.json'):
            shutil.copy2(ROOT / name, project / name)
        for name in ('src', 'skill', 'skill-lab'):
            shutil.copytree(ROOT / name, project / name,
                ignore=shutil.ignore_patterns('__pycache__', '*.egg-info', '.DS_Store'))
        for name in ('scripts/jupyter_local.py', 'examples/jupyter/hello.ipynb',
                     'docs/Jupyter本地开发指南.md'):
            target = project / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        built = subprocess.run([sys.executable, 'setup.py', 'sdist', 'bdist_wheel'],
                               cwd=project, capture_output=True, text=True)
        if built.returncode:
            raise SystemExit(built.stdout + built.stderr)
        wheel, = (project / 'dist').glob('*.whl')
        sdist, = (project / 'dist').glob('*.tar.gz')
        with tarfile.open(sdist) as archive:
            names = archive.getnames()
            assert not any('skill-lab/' in n or LAB_NAME in n for n in names), names
        with zipfile.ZipFile(wheel) as archive:
            names = archive.namelist()
            assert not any('skill-lab/' in n or LAB_NAME in n for n in names), names
            prefix = 'wiserec_cli/opencode_resources/'
            manifest = json.loads(archive.read(prefix + 'manifest.json'))
            expected = {'commands/ml.md', 'skills/wiserec-platform/SKILL.md'}
            expected.update('skills/wiserec-platform/references/' + p.name
                for p in (ROOT / 'skill/wiserec-platform/references').glob('*.md'))
            assert set(manifest) == expected, manifest
            assert {n[len(prefix):] for n in names if n.startswith(prefix)} == expected | {'manifest.json'}
            for name, digest in manifest.items():
                assert hashlib.sha256(archive.read(prefix + name)).hexdigest() == digest
        print('PASS: real Wheel and sdist exclude skill-lab; formal OpenCode resources and hashes unchanged')
        print('Windows ZIP installation is not exercised here; its scripts and existing packaging tests need separate review')


if __name__ == '__main__':
    main()
