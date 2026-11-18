"""Reject development providers and stale files in distributable CLI archives."""
import argparse
import io
from pathlib import Path, PurePosixPath
import tarfile
import zipfile

FORBIDDEN = ('wiserec_cli_mock', 'wiserec-cli-mock', 'devtools/', 'scripts/demo/',
             'workspace.json', 'state.sqlite3', 'jupyter.json', 'wiserec_cli/mock/',
             'wiserec_cli/mock.py', 'wiserec_cli/seeds/', 'wiserec_cli/scenarios/',
             'permission_notifier', 'permission-notifier', 'assistant.json',
             'notification_models.py', 'notification_api.py', 'notification_auth.py',
             'notification_admin.py', 'notification_schema.py', 'notification_state.py',
             'notifications.html', '权限申请通知与独立本地助手设计.md', '权限通知开发与验收说明.md')


def check(path, content=None):
    name = str(path)
    source = io.BytesIO(content) if content is not None else path
    if name.endswith(('.whl', '.zip')):
        with zipfile.ZipFile(source) as archive:
            for item in archive.namelist():
                normalized = item.replace('\\', '/').lower()
                if any(token in normalized for token in FORBIDDEN):
                    raise ValueError(f'非正式内容进入发布包: {item}')
                if name.endswith('.whl') and Path(name).name.startswith('wiserec_cli-'):
                    top = PurePosixPath(item).parts[0]
                    if top != 'wiserec_cli' and not top.endswith('.dist-info'):
                        raise ValueError(f'CLI Wheel 中出现未知模块: {item}')
                    if item.endswith('METADATA'):
                        metadata = archive.read(item).lower()
                        if any(name in metadata for name in (b'wiserec-cli-mock', b'permission-notifier', b'pystray')):
                            raise ValueError('正式 CLI 依赖了隔离组件')
                if item.endswith('.whl'):
                    check(item, archive.read(item))
    elif name.endswith('.tar.gz'):
        with tarfile.open(fileobj=source if content is not None else None,
                          name=None if content is not None else str(path), mode='r:gz') as archive:
            for item in archive.getnames():
                if any(token in item.lower() for token in FORBIDDEN):
                    raise ValueError(f'源码分发包包含演示内容: {item}')
    else:
        raise ValueError(f'不支持的产物类型: {path}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives', nargs='+', type=Path)
    args = parser.parse_args()
    for archive in args.archives:
        check(archive)
        print(f'CLI package isolation passed: {archive.name}')
