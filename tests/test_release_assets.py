"""Release gate must keep the third ZIP separate and reject mixed build sources."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).parents[1]
VERSION = '1.0.7.7'
SHA = 'a' * 40


def assemble(tmp_path, *, wrong_revision=False, extra_file=False, leak=False):
    scripts = tmp_path / 'scripts/releasing'
    scripts.mkdir(parents=True)
    for name in ('prepare-assets.py', 'check-cli-package.py'):
        shutil.copyfile(ROOT / 'scripts/releasing' / name, scripts / name)
    files = {
        'access-service/VERSION': VERSION,
        'docs/权限管理系统Docker安装部署与调试指南.md': 'runbook',
        f'docs/权限管理系统1.0.7.1升级至{VERSION}指南.md': 'upgrade',
        'docs/WiseRec CLI 使用手册.md': 'commands',
        'scripts/windows/INSTALL.md': 'install',
        'permission-notifier/README.md': 'assistant install',
        'permission-notifier/pyproject.toml': f'[project]\nversion="{VERSION}"',
        'permission-notifier/src/permission_notifier/__init__.py': f"__version__ = '{VERSION}'",
        'permission-notifier/src/permission_notifier/static/app.js': 'source',
        'permission-notifier/scripts/install.ps1': 'installer',
    }
    for name, value in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
    out = tmp_path / 'release-assets'
    out.mkdir()
    wheel = out / f'wiserec_cli-{VERSION}-py3-none-any.whl'
    with ZipFile(wheel, 'w') as z:
        z.writestr('wiserec_cli/__init__.py', f'__version__ = "{VERSION}"')
        z.writestr(f'wiserec_cli-{VERSION}.dist-info/METADATA', f'Version: {VERSION}\n')
        if leak:
            z.writestr('permission_notifier/worker.py', 'not CLI code')
    for mode in ('online', 'offline'):
        with ZipFile(out / f'wiserec-cli-{VERSION}-{mode}.zip', 'w') as z:
            z.writestr('bundle/release.json', json.dumps({'version': VERSION, 'mode': mode,
                'architecture': 'x64', 'python_major': 3, 'python_minor': 12}))
            z.writestr('bundle/' + wheel.name, wheel.read_bytes())
    assistant_files = {name.removeprefix('permission-notifier/'): value for name, value in files.items()
                       if name.startswith('permission-notifier/')}
    prefix = f'permission-notifier-{VERSION}-windows-source/'
    with ZipFile(out / (prefix[:-1] + '.zip'), 'w') as z:
        for name, value in assistant_files.items():
            z.writestr(prefix + name, value)
        z.writestr(prefix + 'release.json', json.dumps({'version': VERSION,
            'revision': 'b' * 40 if wrong_revision else SHA, 'mode': 'source-online',
            'python': '3.12', 'platform': 'windows',
            'files': {name: hashlib.sha256(value.encode()).hexdigest() for name, value in assistant_files.items()}}))
    image = f'cli-access-{VERSION}-linux-amd64.tar.gz'
    (out / image).write_bytes(b'fixture; Docker contents are independently validated by image CI')
    (out / 'README.md').write_text('image readme')
    (out / 'service.env.example').write_text('placeholder')
    (out / 'manifest.json').write_text(json.dumps({'image_version': VERSION, 'image_revision': SHA,
        'image_reference': 'ghcr.io/example/cli-access@sha256:' + 'c' * 64,
        'image_tag': 'cli-access:' + VERSION, 'image_file': image}))
    if extra_file:
        (out / 'unexpected-config.txt').write_text('must not ship')
    (out / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in out.iterdir()
        if p.name != 'SHA256SUMS'))
    return subprocess.run([sys.executable, str(scripts / 'prepare-assets.py')], cwd=tmp_path,
        env={**os.environ, 'VERSION': VERSION, 'CLI_VERSION': VERSION, 'GITHUB_SHA': SHA,
             'IMAGE_DIGEST': 'sha256:' + 'c' * 64}, capture_output=True, text=True)


def test_assistant_is_third_separate_archive_with_complete_checksums(tmp_path):
    result = assemble(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / 'release-assets'
    manifest = json.loads((out / 'manifest.json').read_text())
    assert len(manifest['cli_packages']) == 2
    assert manifest['notifier_package']['file'].startswith('permission-notifier-')
    assert len((out / 'SHA256SUMS').read_text().splitlines()) == 13
    assert (out / 'Notifier-install.md').read_text() == 'assistant install'


@pytest.mark.parametrize('fault', ['wrong_revision', 'extra_file', 'leak'])
def test_release_rejects_mixed_sources_extra_files_or_cli_leak(tmp_path, fault):
    assert assemble(tmp_path, **{fault: True}).returncode != 0
