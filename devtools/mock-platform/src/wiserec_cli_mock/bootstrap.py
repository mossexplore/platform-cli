"""The only host that activates simulated dependencies."""
import os
import sys
from pathlib import Path
from .workspace import checked, validate_config
from .storage import Store
from .transport import Transport
from .auth import DemoAuth


def activate(root):
    from wiserec_cli.execution import ExecutionContext, configure
    root = checked(root)
    Store(root).validate()
    # Ignore inherited production settings; no system/user environment is changed.
    os.environ['ML_CONFIG'] = str(root / 'config.json')
    os.environ['ML_CLIENT_STATE_DIR'] = str(root / 'client')
    os.environ.pop('ML_JUPYTER_TOKEN', None)
    os.environ['WISEREC_DEMO_WORKSPACE'] = str(root)
    from .local_jupyter import validate_connection
    import json
    from . import __version__
    metadata = json.loads((root / "workspace.json").read_text())
    configure(ExecutionContext(mode='演示（模拟数据）', state_dir=root / 'client',
        config_path=root / 'config.json', transport_factory=lambda: Transport(root),
        auth_factory=DemoAuth, validate_config=lambda config: validate_config(root, config),
        validate_connection=lambda connection: validate_connection(root, connection),
        worker_module='wiserec_cli_mock.worker',
        details={'权限服务': metadata['permission_url'], '权限账号': metadata['username'], '演示工作区': str(root), '当前场景': metadata['scenario'], '演示扩展版本': __version__}))
    from wiserec_cli.config import ConfigManager
    ConfigManager()
    return root


def main():
    try:
        root = activate(os.environ['WISEREC_DEMO_WORKSPACE'])
        # Reject external configuration before command history can touch its directory.
        for i, arg in enumerate(sys.argv[1:], 1):
            value = sys.argv[i+1] if arg == '--config' and i+1 < len(sys.argv) else arg.partition('=')[2] if arg.startswith('--config=') else None
            if value is not None and Path(value).resolve() != root / 'config.json':
                raise ValueError('演示环境禁止使用外部配置')
        from wiserec_cli.cli import run
        run()
    except Exception as exc:
        print(f'演示环境启动失败：{exc}', file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
