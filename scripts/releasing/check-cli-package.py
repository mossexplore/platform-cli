"""Reject development providers and stale files in distributable CLI archives."""
import argparse
import ast
from email.parser import Parser
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


def check_wheel_version(archive, expected_version):
    metadata_paths = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
    if len(metadata_paths) != 1:
        raise ValueError('CLI Wheel 必须包含唯一的安装元数据')
    metadata = Parser().parsestr(archive.read(metadata_paths[0]).decode('utf-8'))
    if metadata.get('Name', '').lower().replace('_', '-') != 'wiserec-cli':
        raise ValueError('CLI Wheel 的包名不正确')
    source = ast.parse(archive.read('wiserec_cli/__init__.py').decode('utf-8-sig'))
    versions = [ast.literal_eval(node.value) for node in source.body
                if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == '__version__'
                        for target in node.targets)]
    if versions != [expected_version] or metadata.get('Version') != expected_version:
        raise ValueError(f'CLI Wheel 版本不一致：目标 {expected_version}，'
                         f'元数据 {metadata.get("Version")}，代码 {versions}')


def check(path, content=None, expected_version=None):
    name = str(path)
    source = io.BytesIO(content) if content is not None else path
    cli_wheels = 0
    if name.endswith(('.whl', '.zip')):
        with zipfile.ZipFile(source) as archive:
            if name.endswith('.whl') and Path(name).name.startswith('wiserec_cli-'):
                cli_wheels += 1
                if expected_version is not None:
                    check_wheel_version(archive, expected_version)
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
                    cli_wheels += check(item, archive.read(item), expected_version=expected_version)
    elif name.endswith('.tar.gz'):
        with tarfile.open(fileobj=source if content is not None else None,
                          name=None if content is not None else str(path), mode='r:gz') as archive:
            for item in archive.getnames():
                if any(token in item.lower() for token in FORBIDDEN):
                    raise ValueError(f'源码分发包包含演示内容: {item}')
    else:
        raise ValueError(f'不支持的产物类型: {path}')
    return cli_wheels


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-version', help='核对 CLI Wheel 元数据和包内代码版本')
    parser.add_argument('archives', nargs='+', type=Path)
    args = parser.parse_args()
    for archive in args.archives:
        count = check(archive, expected_version=args.expected_version)
        if args.expected_version is not None and count == 0:
            raise ValueError(f'产物中未找到 CLI Wheel: {archive}')
        print(f'CLI package isolation passed: {archive.name}')
