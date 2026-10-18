"""Workspace ownership, initialization and configuration validation."""
import json
from pathlib import Path
from .seeds import SCENARIOS, PROFILES, populate
from .storage import Store


def checked(root):
    root = Path(root).expanduser().absolute()
    if root.is_symlink() or any(p.is_symlink() for p in root.parents):
        raise ValueError('演示目录及其父目录不能是符号链接')
    root = root.resolve()
    marker = root / 'workspace.json'
    if not marker.is_file() or marker.is_symlink():
        raise ValueError('目录不是已初始化的演示工作区')
    metadata = json.loads(marker.read_text())
    if (metadata.get('format') != 1 or metadata.get('scenario') not in SCENARIOS
            or not metadata.get('username') or not metadata.get('permission_url')):
        raise ValueError('无效的演示工作区标记')
    for item in root.rglob('*'):
        if item.is_symlink():
            raise ValueError('演示工作区不能包含符号链接')
    return root


def initialize(root, scenario='standard', *, permission_url, username):
    from .permissions import settings
    access = settings(permission_url, username)
    if scenario not in SCENARIOS:
        raise ValueError('未知场景')
    root = Path(root).expanduser().absolute()
    if root.exists():
        raise ValueError('初始化目标已存在，拒绝覆盖')
    if any(p.is_symlink() for p in root.parents):
        raise ValueError('演示目录父路径不能是符号链接')
    root.mkdir(parents=True, mode=0o700)
    (root / 'workspace.json').write_text(json.dumps({'format': 1, 'scenario': scenario, 'username': username, 'permission_url': permission_url}), encoding='utf-8')
    for name in ('client', 'jupyter', 'exports', 'samples'):
        (root / name).mkdir()
    (root / 'samples' / 'clicks.csv').write_text('user_id,clicks\nu001,12\nu002,7\n')
    config = dict(current='demo-dev', auth={'auto_ping': False}, api={'retry_times': 0},
        access_control=access,
        profiles=[dict(name=p, alias=p, api_endpoint=f'https://{p}.mock.invalid/dashboard',
                       jupyter={'mode': 'webstudio', 'server_url': 'http://127.0.0.1:18888/'}) for p in PROFILES])
    (root / 'config.json').write_text(json.dumps(config, indent=2), encoding='utf-8')
    store = Store(root)
    store.create()
    populate(root, scenario)
    if scenario == 'partial-failure':
        with store.transaction() as db:
            db.execute('INSERT INTO faults VALUES(?,?,?)', ('/ai/backend/modelDev/modelTrain/list', 503, 1))
    return root


def validate_config(root, config):
    if config.path != root / 'config.json':
        raise ValueError('演示环境禁止使用外部配置')
    for profile in config.profiles():
        if profile.name not in PROFILES or profile.api_endpoint != f'https://{profile.name}.mock.invalid/dashboard':
            raise ValueError('演示环境禁止配置真实平台')
        settings = next(p.get('jupyter', {}) for p in config._data['profiles'] if p['name'] == profile.name)
        if (settings.get('mode') != 'webstudio' or settings.get('business_file')
                or settings.get('token_file') or settings.get('ca_file') or settings.get('token_env')):
            raise ValueError('演示环境不允许引用外部凭据文件')
    from wiserec_cli.access import access_enabled
    if not access_enabled(config.access_control):
        raise ValueError('演示环境必须经过真实权限系统校验')
    metadata = json.loads((root/'workspace.json').read_text())
    from .permissions import settings
    settings(metadata['permission_url'], metadata['username'])
    if config.access_control['url'] != metadata['permission_url']:
        raise ValueError('演示权限地址不匹配')
    if config.access_control.get('use_env_proxy', False):
        raise ValueError('演示权限服务使用直连，禁止代理转发')
