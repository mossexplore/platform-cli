"""Synchronize component versions; --check rejects drift without modifying files."""
import argparse
from pathlib import Path
import re

try:
    import tomllib
except ModuleNotFoundError:  # CLI builds still support Python 3.9/3.10.
    import tomli as tomllib


def read_versions(root):
    with (root / 'versions.toml').open('rb') as source:
        data = tomllib.load(source)
    versions = data['components']
    if set(versions) != {'cli', 'access', 'agent', 'notifier'}:
        raise ValueError('components 必须包含 cli、access、agent、notifier')
    tested = data['compatibility']['agent_cli']
    for value in [*versions.values(), tested]:
        if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', value):
            raise ValueError('版本必须是三段或四段数字字符串')
    return versions, tested


def project_version(path, value):
    text = path.read_text(encoding='utf-8')
    start = text.index('[project]')
    end = text.find('\n[', start + 1)
    if end == -1:
        end = len(text)
    section, count = re.subn(r'^version\s*=\s*"[^"]+"',
                            f'version = "{value}"', text[start:end], flags=re.M)
    if count != 1:
        raise ValueError(f'{path} 缺少唯一 project.version')
    return text[:start] + section + text[end:]


def sync(root, check=False):
    root = Path(root)
    versions, tested = read_versions(root)
    generated = '# Generated from versions.toml by scripts/sync_versions.py; do not edit.\n'
    files = {
        root / 'pyproject.toml': project_version(root / 'pyproject.toml', versions['cli']),
        root / 'src/wiserec_cli/__init__.py':
            '"""wiserec CLI package."""\n\n' + generated + f'__version__ = "{versions["cli"]}"\n',
    }
    # CLI source distributions contain the manifest but deliberately exclude services.
    if (root / 'access-service/VERSION').is_file():
        files[root / 'access-service/VERSION'] = versions['access'] + '\n'
        files[root / 'access-service/app/_version.py'] = generated + f'__version__ = "{versions["access"]}"\n'
    agent = root / 'agent-service/pyproject.toml'
    if agent.is_file():
        files[agent] = project_version(agent, versions['agent'])
        files[root / 'agent-service/app/_version.py'] = (generated
            + f'__version__ = "{versions["agent"]}"\nTESTED_CLI_VERSION = "{tested}"\n')
    notifier = root / 'permission-notifier/pyproject.toml'
    if notifier.is_file():
        files[notifier] = project_version(notifier, versions['notifier'])
        files[root / 'permission-notifier/src/permission_notifier/__init__.py'] = (
            generated + f"__version__ = '{versions['notifier']}'\n")
    changed = [path for path, text in files.items()
               if not path.is_file() or path.read_text(encoding='utf-8') != text]
    if check and changed:
        raise ValueError('版本文件未同步：' + '、'.join(str(path.relative_to(root)) for path in changed))
    if not check:
        for path in changed:
            path.write_text(files[path], encoding='utf-8')
    return changed


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    sync(Path(__file__).resolve().parents[1], args.check)
