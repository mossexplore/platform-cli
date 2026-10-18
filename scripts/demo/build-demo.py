"""Build a separate demo bundle; never change production installers or PATH."""
import argparse
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile


def execute(*args, cwd=None):
    subprocess.run([sys.executable, *map(str, args)], cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('release/demo'))
    parser.add_argument('--offline', action='store_true')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    version = next(line.split('"')[1] for line in (repo/'pyproject.toml').read_text().splitlines()
                   if line.startswith('version ='))
    name = f'wiserec-cli-{version}-demo-' + ('offline' if args.offline else 'online')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output/(name+'.zip')
    if target.exists():
        raise SystemExit('目标演示包已存在，拒绝覆盖')
    with tempfile.TemporaryDirectory(prefix='wiserec-demo-build-') as temporary:
        root = Path(temporary)/name
        wheels = root/'packages'
        wheels.mkdir(parents=True)
        execute('-m', 'build', '--wheel', '--outdir', wheels, cwd=repo)
        core = next(wheels.glob('wiserec_cli-*.whl'))
        execute(repo/'scripts/releasing/check-cli-package.py', core)
        execute('-m', 'build', '--wheel', '--outdir', wheels, cwd=repo/'devtools/mock-platform')
        if args.offline:
            execute('-m', 'pip', 'download', '--only-binary=:all:', '--dest', wheels,
                    '--find-links', wheels, *list(wheels.glob('*.whl')))
        for filename in ('install-demo.py', 'start-demo.cmd', 'manage-demo.cmd', 'start-demo.sh', 'manage-demo.sh'):
            shutil.copyfile(repo/'scripts/demo'/filename, root/filename)
        shutil.copyfile(repo/'docs/CLI演示环境使用指南.md', root/'README.md')
        manifest = {'cli_version': version, 'offline': args.offline,
                    'python': sys.version.split()[0], 'platform': sys.platform, 'architecture': platform.machine(),
                    'files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in root.rglob('*') if p.is_file()}}
        (root/'manifest.json').write_text(json.dumps(manifest, indent=2))
        with zipfile.ZipFile(target, 'x', compression=zipfile.ZIP_DEFLATED) as archive:
            for file in root.rglob('*'):
                if file.is_file():
                    archive.write(file, str(file.relative_to(root.parent)))
    print(target)


if __name__ == '__main__':
    main()
