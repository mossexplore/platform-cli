"""Release gate must keep the third ZIP separate and reject mixed build sources."""
import hashlib
import io
import tarfile
import runpy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile
import pytest

ROOT = Path(__file__).parents[1]
VERSION = '1.0.9.1'
SHA = 'a' * 40


def assemble(tmp_path, *, wrong_revision=False, extra_file=False, leak=False, legacy_layout=False):
    scripts = tmp_path / 'scripts/releasing'
    scripts.mkdir(parents=True)
    shutil.copyfile(ROOT / 'scripts/releasing/prepare-assets.py', scripts / 'prepare-assets.py')
    cli_checker = 'scripts/releasing/check-cli-package.py' if legacy_layout else 'cli-python/scripts/check-cli-package.py'
    cli_install = 'scripts/windows/INSTALL.md' if legacy_layout else 'cli-python/scripts/windows/INSTALL.md'
    (tmp_path / cli_checker).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / 'cli-python/scripts/check-cli-package.py', tmp_path / cli_checker)
    files = {
        'access-service/VERSION': VERSION,
        f'docs/releases/ACCESS_RELEASE_NOTES_{VERSION}.md': '[access notes](../upgrades/环境禁止命令开发与迁移说明.md)',
        'docs/upgrades/环境禁止命令开发与迁移说明.md': 'migration notes',
        f'docs/releases/RELEASE_NOTES_{VERSION}.md': 'release notes fixture',
        'docs/deployment/权限管理系统Docker离线导入与运行.md': 'image readme',
        'access-service/docker/service.env.example': 'placeholder',
        'docs/deployment/权限管理系统Docker安装部署与调试指南.md': 'runbook',
        f'docs/upgrades/权限管理系统结构12升级至{VERSION}指南.md': 'upgrade',
        'docs/guides/WiseRec CLI 使用手册.md': 'commands',
        cli_install: 'install',
        'permission-notifier/README.md': 'assistant install',
        'permission-notifier/pyproject.toml': f'[project]\nversion="{VERSION}"',
        'permission-notifier/src/permission_notifier/__init__.py': f"__version__ = '{VERSION}'",
        'permission-notifier/src/permission_notifier/static/app.js': 'source',
        'permission-notifier/scripts/install.ps1': 'installer',
    }
    for name, value in files.items():
        if legacy_layout and name.startswith('docs/'):
            name = f'docs/{Path(name).name}'
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
        suffix = 'windows-py3-online' if mode == 'online' else 'windows-x64-py312-offline'
        with ZipFile(out / f'wiserec-cli-{VERSION}-{suffix}.zip', 'w') as z:
            z.writestr('bundle/release.json', json.dumps({'version': VERSION, 'mode': mode, 'platform': 'windows',
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
    config = json.dumps({'os': 'linux', 'architecture': 'amd64', 'config': {'Labels': {
        'org.opencontainers.image.version': VERSION, 'org.opencontainers.image.revision': SHA}}}).encode()
    image_id = 'sha256:' + hashlib.sha256(config).hexdigest()
    with tarfile.open(out / image, 'w:gz') as archive:
        for name, content in {'config.json': config, 'manifest.json': json.dumps([{
            'Config': 'config.json', 'RepoTags': ['cli-access:' + VERSION], 'Layers': []}]).encode()}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(content)
            archive.addfile(entry, io.BytesIO(content))
    (out / 'RELEASE_NOTES.md').write_text('[access notes](Migration-notes.md)')
    (out / 'Migration-notes.md').write_text('migration notes')
    (out / 'README.md').write_text('image readme')
    (out / 'service.env.example').write_text('placeholder')
    (out / 'manifest.json').write_text(json.dumps({'image_version': VERSION, 'image_revision': SHA,
        'image_reference': 'ghcr.io/mossexplore/cli-access@sha256:' + 'c' * 64,
        'image_tag': 'cli-access:' + VERSION, 'image_file': image,
        'image_id': image_id, 'platform': 'linux/amd64'}))
    if extra_file:
        (out / 'unexpected-config.txt').write_text('must not ship')
    (out / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in out.iterdir()
        if p.name != 'SHA256SUMS'))
    return subprocess.run([sys.executable, str(scripts / 'prepare-assets.py')], cwd=tmp_path,
        env={**os.environ, 'VERSION': VERSION, 'CLI_VERSION': VERSION, 'GITHUB_SHA': SHA,
             'IMAGE_DIGEST': 'sha256:' + 'c' * 64}, capture_output=True, text=True)


@pytest.mark.parametrize('legacy_layout', [False, True])
def test_assistant_is_third_separate_archive_with_complete_checksums(tmp_path, legacy_layout):
    result = assemble(tmp_path, legacy_layout=legacy_layout)
    assert result.returncode == 0, result.stdout + result.stderr
    out = tmp_path / 'release-assets'
    manifest = json.loads((out / 'manifest.json').read_text())
    assert len(manifest['cli_packages']) == 2
    assert manifest['notifier_package']['file'].startswith('permission-notifier-')
    assert len((out / 'SHA256SUMS').read_text().splitlines()) == 15
    assert (out / 'Notifier-install.md').read_text() == 'assistant install'


@pytest.mark.parametrize('fault', ['wrong_revision', 'extra_file', 'leak'])
def test_release_rejects_mixed_sources_extra_files_or_cli_leak(tmp_path, fault):
    assert assemble(tmp_path, **{fault: True}).returncode != 0


def downloaded_release(directory):
    return {'draft': True, 'prerelease': False, 'tag_name': 'v' + VERSION,
            'target_commitish': SHA, 'body': 'release notes fixture',
            'assets': [{'name': p.name, 'size': p.stat().st_size,
                        'digest': 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()}
                       for p in directory.iterdir()]}


def test_independent_download_verifier_accepts_matching_draft(tmp_path, monkeypatch):
    result = assemble(tmp_path)
    assert result.returncode == 0, result.stderr
    verify = runpy.run_path(str(ROOT / 'scripts/releasing/verify-assets.py'))['verify']
    monkeypatch.chdir(tmp_path)
    directory = tmp_path / 'release-assets'
    verify(directory, downloaded_release(directory), VERSION, SHA, 'sha256:' + 'c' * 64)


def test_download_verifier_rejects_wrong_image_even_with_valid_file_hashes(tmp_path, monkeypatch):
    assert assemble(tmp_path).returncode == 0
    directory = tmp_path / 'release-assets'
    manifest = directory / 'manifest.json'
    data = json.loads(manifest.read_text())
    data['image_id'] = 'sha256:' + 'd' * 64
    manifest.write_text(json.dumps(data))
    (directory / 'SHA256SUMS').write_text(''.join(
        f'{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.name}\n' for p in directory.iterdir()
        if p.name != 'SHA256SUMS'))
    verify = runpy.run_path(str(ROOT / 'scripts/releasing/verify-assets.py'))['verify']
    monkeypatch.chdir(tmp_path)
    with pytest.raises(AssertionError):
        verify(directory, downloaded_release(directory), VERSION, SHA, 'sha256:' + 'c' * 64)


def test_go_suite_checks_artifact_inventory_and_image_identity(tmp_path, monkeypatch):
    import struct

    revision = 'a' * 40
    version = '1.1.1'
    digest = 'sha256:' + 'b' * 64
    module = runpy.run_path(str(ROOT / 'scripts/releasing/go-suite-assets.py'))
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv('GITHUB_REPOSITORY', 'mossexplore/platform-cli')
    access, windows, gateway = (tmp_path / name for name in ('access', 'windows', 'gateway'))
    for directory in (access, windows, gateway):
        directory.mkdir()

    def save_image(directory, stem):
        config = json.dumps({'os': 'linux', 'architecture': 'amd64', 'config': {'Labels': {
            'org.opencontainers.image.version': version, 'org.opencontainers.image.revision': revision}}}).encode()
        image_hash = hashlib.sha256(config).hexdigest()
        config_name = 'blobs/sha256/' + image_hash
        image_file = f'{stem}-{version}-linux-amd64.tar.gz'
        archive_manifest = [{'Config': config_name, 'RepoTags': [f'{stem}:{version}'], 'Layers': []}]
        with tarfile.open(directory / image_file, 'w:gz') as archive:
            for name, content in ((config_name, config), ('manifest.json', json.dumps(archive_manifest).encode())):
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                archive.addfile(entry, io.BytesIO(content))
        return image_file, 'sha256:' + image_hash

    access_file, access_id = save_image(access, 'cli-access')
    _, gateway_id = save_image(gateway, 'wiserec-telemetry-gateway')
    metadata = {
        'image_version': version, 'image_revision': revision, 'documents_source_revision': revision,
        'image_reference': 'ghcr.io/mossexplore/cli-access@' + digest, 'image_tag': 'cli-access:' + version,
        'image_file': access_file, 'image_id': access_id, 'platform': 'linux/amd64',
    }
    (access / 'manifest.json').write_text(json.dumps(metadata))
    readme = (ROOT / 'docs/deployment/权限管理系统Docker离线导入与运行.md').read_text()
    for key, value in metadata.items():
        readme = readme.replace('{{' + key + '}}', value)
    (access / 'README.md').write_text(readme)
    for name in ('service.env.example', 'Docker-runbook.md', f'Docker-upgrade-{version}.md'):
        (access / name).touch()
    for directory in (access, gateway):
        (directory / 'SHA256SUMS').write_text(''.join(
            f'{module["sha256"](path)}  {path.name}\n' for path in sorted(directory.iterdir())))

    package = windows / f'wiserec-cli-{version}-windows-x64'
    (windows / (package.name + '.msi')).write_bytes(bytes.fromhex('d0cf11e0a1b11ae1'))
    with ZipFile(windows / (package.name + '.zip'), 'w') as archive:
        exe = bytearray(64)
        exe[:2] = b'MZ'
        struct.pack_into('<I', exe, 60, 64)
        archive.writestr('ml.exe', exe + b'PE\x00\x00\x64\x86')
        archive.writestr('README.md', 'fixture')
        archive.writestr('LICENSE', 'fixture')
        archive.writestr('release.json', json.dumps({
            'component': 'cli_go', 'version': version, 'platform': 'windows', 'architecture': 'amd64'}))
    module['prepare'](access, windows, gateway, version, revision, digest, gateway_id)
    draft = {
        'draft': True, 'prerelease': False, 'tag_name': 'v' + version, 'target_commitish': revision,
        'name': f'v{version} — Go CLI、权限管理系统与 DSH 遥测网关',
        'body': (ROOT / f'docs/releases/RELEASE_NOTES_{version}.md').read_text(),
        'assets': [{'name': p.name, 'size': p.stat().st_size,
                    'digest': 'sha256:' + module['sha256'](p)} for p in access.iterdir()],
    }
    module['verify'](access, version, revision, digest, gateway_id, draft)
    with pytest.raises(AssertionError):
        module['verify'](access, version, revision, digest, 'sha256:' + 'c' * 64, draft)
