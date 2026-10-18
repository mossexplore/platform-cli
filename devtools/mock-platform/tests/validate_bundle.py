"""Validate a built bundle outside the source tree against real permissions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from permission_server import PermissionServer


def main():
    with tempfile.TemporaryDirectory(prefix='demo-bundle-validation-') as directory:
        target = Path(directory)
        service = PermissionServer(target)
        try:
            with zipfile.ZipFile(sys.argv[1]) as archive:
                archive.extractall(target/'unpacked')
            root = next((target/'unpacked').iterdir())
            manifest = json.loads((root/'manifest.json').read_text())
            environment = dict(os.environ)
            if manifest['offline']:
                environment['PIP_NO_INDEX'] = '1'
            subprocess.run([sys.executable, str(root/'install-demo.py'), '--permission-url', service.url,
                            '--username', 'demo'], env=environment, cwd=target, check=True)
            environment['WISEREC_DEMO_WORKSPACE'] = str(root/'workspace')
            # A wrapper must ignore inherited Python module lookup configuration.
            poison = target/'poison'
            poison.mkdir()
            (poison/'wiserec_cli.py').write_text('raise RuntimeError("inherited PYTHONPATH")')
            environment['PYTHONPATH'] = str(poison)
            entry = root/('bin/ml.cmd' if sys.platform == 'win32' else 'bin/ml')
            for arguments in [('context', '--json'), ('train', 'list', '-o', 'json')]:
                result = subprocess.run([str(entry), *arguments], env=environment, cwd=target,
                                        capture_output=True, text=True, check=True)
                value = json.loads(result.stdout)
                if arguments[0] == 'context':
                    assert value['运行模式'] == '演示（模拟数据）'
                    assert value['权限服务'] == service.url
                else:
                    assert value['count'] == 25
            from app.models import CallLog
            from sqlalchemy import select
            with service.app.state.sessions() as db:
                record = db.scalars(select(CallLog).where(CallLog.command == 'ml train list')).one()
                assert record.allowed and record.environment == 'demo-dev'
            print('Bundle installation, isolated ml, real permissions and persisted call log passed')
        finally:
            service.close()


if __name__ == '__main__':
    main()
