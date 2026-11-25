"""Synchronize component versions; --check rejects drift without modifying files."""
import argparse
import json
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
    required = {'cli', 'cli_go', 'access', 'agent', 'notifier'}
    optional = {'dsh_plugin', 'telemetry_gateway'}
    if not required <= versions.keys() or versions.keys() - required - optional:
        raise ValueError('components 必须包含 cli、cli_go、access、agent、notifier，可选 dsh_plugin、telemetry_gateway')
    for key in optional & versions.keys():
        if not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}', str(versions[key])):
            raise ValueError(f'{key} 版本必须是三段数字 SemVer')
    tested = data['compatibility']['agent_cli']
    for value in [*versions.values(), tested]:
        if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+(?:\.\d+)?', value):
            raise ValueError('版本必须是三段或四段数字字符串')
    go = versions['cli_go']
    if not re.fullmatch(r'(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*)){2}', go) or any(
        int(part) > limit for part, limit in zip(go.split('.'), (255, 255, 65535))
    ):
        raise ValueError('Go CLI 版本必须符合 Windows Installer 三段版本范围（255.255.65535）')
    python_cli = tuple(map(int, versions['cli'].split('.')))
    if python_cli + (0,) * (4 - len(python_cli)) == (*map(int, go.split('.')), 0):
        raise ValueError('Go CLI 与 Python CLI 的版本必须不同')
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


def go_version_source(version):
    return ('// Code generated from versions.toml by scripts/sync_versions.py; DO NOT EDIT.\n\n'
            f'package main\n\nconst version = "{version}"\n')


def sync_go(root):
    """Refresh only the Go runtime version for the Windows packager."""
    root = Path(root)
    version = read_versions(root)[0]['cli_go']
    version_path = root / 'cli-go/cmd/ml/version.go'
    content = go_version_source(version)
    if not version_path.is_file() or version_path.read_text(encoding='utf-8') != content:
        version_path.write_text(content, encoding='utf-8')
    return version


def sync(root, check=False):
    root = Path(root)
    versions, tested = read_versions(root)
    cli = root / "cli-python"
    if not (cli / "pyproject.toml").is_file():
        cli = root  # Standalone Python CLI source distribution.
    generated = '# Generated from versions.toml by scripts/sync_versions.py; do not edit.\n'
    files = {
        cli / 'pyproject.toml': project_version(cli / 'pyproject.toml', versions['cli']),
        cli / 'src/wiserec_cli/__init__.py':
            '"""wiserec CLI package."""\n\n' + generated + f'__version__ = "{versions["cli"]}"\n',
    }
    if (root / 'cli-go/go.mod').is_file():
        files[root / 'cli-go/cmd/ml/version.go'] = go_version_source(versions['cli_go'])
    if (root / 'telemetry-gateway/go.mod').is_file():
        files[root / 'telemetry-gateway/cmd/gateway/version.go'] = go_version_source(versions['telemetry_gateway'])
    plugin = root / 'dsh-plugin/wiserec-cli/package.json'
    if plugin.is_file():
        if 'dsh_plugin' not in versions:
            raise ValueError('versions.toml 缺少 dsh_plugin 版本')
        manifest = json.loads(plugin.read_text(encoding='utf-8'))
        manifest['version'] = versions['dsh_plugin']
        files[plugin] = json.dumps(manifest, ensure_ascii=False, indent=2) + '\n'
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
