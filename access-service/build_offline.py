#!/usr/bin/env python3
"""在联网机器交叉下载 Linux wheels，生成含独立 Python 的完整离线包。"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from email.parser import BytesParser

RUNTIME_SHA256 = '72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c'
RUNTIME_URL = ('https://github.com/astral-sh/python-build-standalone/releases/download/20260901/'
               'cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz')


def sha256(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True,
                        help='官方 CPython 3.12.14+20260901 Linux x86_64 install_only_stripped 归档')
    parser.add_argument('--output', type=Path, default=Path('dist'))
    parser.add_argument('--wheelhouse', type=Path, help='已有 Linux wheel 目录；指定后完全离线重新打包')
    args = parser.parse_args()
    if sha256(args.runtime) != RUNTIME_SHA256:
        parser.error('Python 运行时 SHA256 不匹配。下载地址：' + RUNTIME_URL)
    source = Path(__file__).resolve().parent
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cli-access-build-') as temporary:
        root = Path(temporary) / 'cli-access'
        root.mkdir()
        shutil.copytree(source / 'app', root / 'app', ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
        for name in ('install.sh', 'start.sh', 'bootstrap.sh', 'manage.sh', 'QUICKSTART.md', '.env.example', 'cli-access.service', 'nginx.conf.example', 'README.md'):
            shutil.copy2(source / name, root / name)
        shutil.copy2(args.runtime, root / 'python-runtime.tar.gz')
        wheels = root / 'wheelhouse'
        wheels.mkdir()
        # 多个 platform 表示允许的旧兼容标签，绝不混入构建机的 macOS wheels。
        offline = ['--no-index', '--find-links', str(args.wheelhouse.resolve())] if args.wheelhouse else []
        subprocess.run([sys.executable, '-m', 'pip', 'download', '--only-binary=:all:',
                        '--implementation', 'cp', '--python-version', '3.12', '--abi', 'cp312',
                        '--abi', 'abi3', '--abi', 'none',
                        '--platform', 'manylinux_2_28_x86_64',
                        '--platform', 'manylinux_2_17_x86_64', '--platform', 'manylinux2014_x86_64',
                        '-r', str(source / 'requirements.lock'), '--dest', str(wheels)] + offline, check=True)
        # 安装锁包含每个包的确切版本与已下载 wheel 的哈希。
        locked = []
        for wheel in sorted(wheels.glob('*.whl')):
            with zipfile.ZipFile(wheel) as archive:
                metadata = next(name for name in archive.namelist() if name.endswith('.dist-info/METADATA'))
                info = BytesParser().parsebytes(archive.read(metadata))
                locked.append(f"{info['Name']}=={info['Version']} --hash=sha256:{sha256(wheel)}")
        (root / 'requirements.lock').write_text('\n'.join(locked) + '\n')
        (root / 'manifest.json').write_text(json.dumps({
            'architecture': 'x86_64', 'python': '3.12.14', 'minimum_glibc': '2.28',
            'runtime_source': RUNTIME_URL, 'runtime_sha256': RUNTIME_SHA256,
            'dependency_count': len(locked)}, indent=2) + '\n')
        files = sorted(path for path in root.rglob('*') if path.is_file())
        (root / 'SHA256SUMS').write_text(''.join(f'{sha256(path)}  {path.relative_to(root)}\n' for path in files))
        target = args.output / 'cli-access-linux-x86_64-python312.tar.gz'
        with tarfile.open(target, 'w:gz') as archive:
            archive.add(root, arcname='cli-access')
        checksum = target.with_name(target.name + '.sha256')
        checksum.write_text(f'{sha256(target)}  {target.name}\n')
        print(f'离线包: {target.resolve()}\nSHA256: {sha256(target)}')


if __name__ == '__main__':
    main()
