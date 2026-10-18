"""Install only inside a fresh demo bundle directory."""
import json
import platform
from pathlib import Path
import subprocess
import sys
import venv


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--permission-url', required=True)
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    runtime = root/'runtime'
    if runtime.exists() or (root/'workspace').exists():
        raise SystemExit('演示环境已存在，拒绝覆盖；请解压到新目录安装')
    manifest = json.loads((root/'manifest.json').read_text())
    if manifest['offline'] and (manifest['platform'] != sys.platform or
            manifest['python'].split('.')[:2] != [str(n) for n in sys.version_info[:2]] or
            manifest['architecture'] != platform.machine()):
        raise SystemExit('离线包的 Python、系统或架构与当前环境不匹配')
    import hashlib
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise SystemExit('演示包校验失败')
    venv.EnvBuilder(with_pip=True).create(runtime)
    python = runtime/('Scripts/python.exe' if sys.platform == 'win32' else 'bin/python')
    wheels = root/'packages'
    command = [str(python), '-I', '-m', 'pip', 'install', '--find-links', str(wheels)]
    if manifest['offline']:
        command += ['--no-index']
    command += [str(next(wheels.glob('wiserec_cli-*.whl'))), str(next(wheels.glob('wiserec_cli_mock-*.whl')))]
    subprocess.run(command, check=True)
    subprocess.run([str(python), '-I', '-m', 'wiserec_cli_mock.manage', '--workspace', str(root/'workspace'), 'init',
                    '--permission-url', args.permission_url, '--username', args.username], check=True)
    # This runtime is a library host, not a second production CLI installation.
    (runtime/('Scripts/ml.exe' if sys.platform == 'win32' else 'bin/ml')).unlink(missing_ok=True)
    (root/'bin').mkdir()
    (root/'bin/ml.cmd').write_text('@echo off\r\n"%~dp0..\\runtime\\Scripts\\python.exe" -I -m wiserec_cli_mock.bootstrap %*\r\nexit /b %errorlevel%\r\n')
    entry = root/'bin/ml'
    entry.write_text('#!/bin/sh\nexec "$(dirname "$0")/../runtime/bin/python" -I -m wiserec_cli_mock.bootstrap "$@"\n')
    entry.chmod(0o755)
    (root/'start-demo.sh').chmod(0o755)
    (root/'manage-demo.sh').chmod(0o755)
    print('演示安装完成，使用 start-demo 打开专用终端')


if __name__ == '__main__':
    main()
