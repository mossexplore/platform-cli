"""Validate release inputs and assemble the reviewable download manifest."""
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib
from zipfile import ZipFile

out = Path('release-assets')
version = os.environ['VERSION']
cli_version = os.environ['CLI_VERSION']
revision = os.environ['GITHUB_SHA']
assert version == Path('access-service/VERSION').read_text().strip()
assert cli_version == version
subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out, check=True)
manifest = json.loads((out / 'manifest.json').read_text())
assert manifest['image_version'] == version
assert manifest['image_revision'] == revision
assert manifest['image_reference'].endswith('@' + os.environ['IMAGE_DIGEST'])
assert manifest['image_tag'] == f'cli-access:{version}'
assert (out / manifest['image_file']).is_file()
wheel = out / f'wiserec_cli-{cli_version}-py3-none-any.whl'
assert wheel.is_file()
with ZipFile(wheel) as z:
    metadata = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
    assert len(metadata) == 1
    assert BytesParser().parsebytes(z.read(metadata[0]))['Version'] == cli_version
    assert f'__version__ = "{cli_version}"' in z.read('wiserec_cli/__init__.py').decode()
archives = sorted(out.glob('wiserec-cli-*.zip'))
assert len(archives) == 2
cli = []
for archive in archives:
    with ZipFile(archive) as z:
        names = {name.replace("\\", "/"): name for name in z.namelist()}
        meta = [n for n in names if n.endswith('/release.json')]
        assert len(meta) == 1
        data = json.loads(z.read(names[meta[0]]).decode('utf-8-sig'))
        assert data['version'] == cli_version
        if data['mode'] == 'offline':
            assert data['architecture'] == 'x64'
            assert (data['python_major'], data['python_minor']) == (3, 12)
        inner_wheels = [n for n in names if n.endswith('/' + wheel.name) and '/packages/' not in n]
        assert len(inner_wheels) == 1
        assert z.read(names[inner_wheels[0]]) == wheel.read_bytes(), 'CLI bundles must share the same wheel'
        cli.append({'file': archive.name, **data})
subprocess.run([sys.executable, 'scripts/releasing/check-cli-package.py', str(wheel),
                *map(str, archives)], check=True)
assert {item['mode'] for item in cli} == {'online', 'offline'}
assistant = out / f'permission-notifier-{version}-windows-source.zip'
with ZipFile(assistant) as z:
    prefix = f'permission-notifier-{version}-windows-source/'
    data = json.loads(z.read(prefix + 'release.json'))
    assert data['version'] == version and data['revision'] == revision
    assert data['mode'] == 'source-online' and data['python'] == '3.12' and data['platform'] == 'windows'
    assert tomllib.loads(z.read(prefix + 'pyproject.toml').decode())['project']['version'] == version
    assert f"__version__ = '{version}'" in z.read(prefix + 'src/permission_notifier/__init__.py').decode()
    assert set(z.namelist()) == {prefix + name for name in data['files']} | {prefix + 'release.json'}
    for name, digest in data['files'].items():
        assert hashlib.sha256(z.read(prefix + name)).hexdigest() == digest
        assert z.read(prefix + name) == (Path('permission-notifier') / name).read_bytes()
    assert 'scripts/install.ps1' in data['files'] and 'src/permission_notifier/static/app.js' in data['files']
    assert not any(name.endswith(('assistant.json', '.env')) for name in data['files'])
manifest['notifier_package'] = {'file': assistant.name, **data}
shutil.copyfile('permission-notifier/README.md', out / 'Notifier-install.md')
manifest['cli_packages'] = cli
manifest['cli_version'] = cli_version
manifest['release_tag'] = 'v' + version
manifest['validation'] = [
    'Assistant tests and simulated cross-component delivery; disposable MySQL notification concurrency',
    'Windows assistant installer and loopback HTTP startup/shutdown (headless)',
    'CLI and service unit tests', 'Browser timezone and environment disclosure tests',
    'MySQL Docker smoke, numeric dashboard JSON, directory mount and configuration restart',
    'Docker save/load round trip', 'Windows online and offline install',
    'Windows CLI upgrade from published 1.0.7.1; selected environment preserved on upgrade and reinstall',
]
(out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
shutil.copyfile('docs/权限管理系统Docker安装部署与调试指南.md', out / 'Docker-runbook.md')
shutil.copyfile(f'docs/权限管理系统1.0.7.1升级至{version}指南.md', out / f'Docker-upgrade-{version}.md')
shutil.copyfile('scripts/windows/INSTALL.md', out / 'CLI-install.md')
shutil.copyfile('docs/WiseRec CLI 使用手册.md', out / 'CLI-reference.md')
expected = {wheel.name, assistant.name, *(a.name for a in archives), manifest['image_file'],
            'manifest.json', 'SHA256SUMS', 'README.md', 'service.env.example', 'CLI-install.md',
            'CLI-reference.md', 'Notifier-install.md', 'Docker-runbook.md', f'Docker-upgrade-{version}.md'}
assert {p.name for p in out.iterdir()} == expected, 'Unexpected or missing release assets'
lines = []
for path in sorted(out.iterdir()):
    if path.name != 'SHA256SUMS':
        lines.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
(out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out, check=True)
