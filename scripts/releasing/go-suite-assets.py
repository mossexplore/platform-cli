"""Assemble and independently validate a Go CLI, access service and gateway release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tarfile
import tomllib
from zipfile import ZipFile


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def names_in(directory):
    entries = list(directory.iterdir())
    assert all(path.is_file() and not path.is_symlink() for path in entries)
    return {path.name for path in entries}


def verify_checksums(directory):
    sums = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        digest, filename = line.split('  ', 1)
        assert re.fullmatch('[0-9a-f]{64}', digest) and filename not in sums
        sums[filename] = digest
    assert set(sums) == names_in(directory) - {'SHA256SUMS'}
    for filename, digest in sums.items():
        assert sha256(directory / filename) == digest, filename


def verify_archive(path, image_tag, image_id, version, revision):
    # Stream once without extracting to disk. Docker save may store the config after layers.
    config_bytes = None
    archive_manifest = None
    with tarfile.open(path, 'r|gz') as archive:
        for entry in archive:
            if entry.isfile() and entry.name == 'manifest.json':
                archive_manifest = json.load(archive.extractfile(entry))
            elif entry.isfile() and Path(entry.name).name.removesuffix('.json') == image_id.removeprefix('sha256:'):
                config_bytes = archive.extractfile(entry).read()
    assert archive_manifest and len(archive_manifest) == 1
    image, = archive_manifest
    assert image['RepoTags'] == [image_tag]
    assert Path(image['Config']).name.removesuffix('.json') == image_id.removeprefix('sha256:')
    assert config_bytes and 'sha256:' + hashlib.sha256(config_bytes).hexdigest() == image_id
    config = json.loads(config_bytes)
    assert (config['os'], config['architecture']) == ('linux', 'amd64')
    labels = config['config']['Labels']
    assert labels['org.opencontainers.image.version'] == version
    assert labels['org.opencontainers.image.revision'] == revision


def verify_cli(zip_path, msi_path, version, check_msi):
    with ZipFile(zip_path) as archive:
        assert json.loads(archive.read('release.json')) == {
            'component': 'cli_go', 'version': version, 'platform': 'windows', 'architecture': 'amd64'}
        names = archive.namelist()
        assert len(set(names)) == len(names)
        assert {'ml.exe', 'README.md', 'LICENSE', 'release.json'} <= set(names)
        assert not any(Path(name).name in {'config.json', 'business.json', 'credentials.json', '.env'} for name in names)
        with archive.open('ml.exe') as executable:
            header = executable.read(64)
            assert header[:2] == b'MZ'
            pe_offset, = struct.unpack_from('<I', header, 60)
            executable.seek(pe_offset)
            assert executable.read(6) == b'PE\x00\x00\x64\x86'
    with msi_path.open('rb') as stream:
        assert stream.read(8) == bytes.fromhex('d0cf11e0a1b11ae1')
    if check_msi:
        properties = subprocess.check_output(['msiinfo', 'export', str(msi_path), 'Property'], text=True)
        assert f'ProductVersion\t{version}' in properties.splitlines()
        summary = subprocess.check_output(['msiinfo', 'suminfo', str(msi_path)], text=True)
        assert re.search(r'^Template:\s*x64(?:;|$)', summary, re.MULTILINE | re.IGNORECASE), summary


def documents(version):
    return {
        'CLI-install.md': Path('cli-go/README.md'),
        'CLI-reference.md': Path('docs/WiseRec CLI 使用手册.md'),
        'Docker-runbook.md': Path('docs/权限管理系统Docker安装部署与调试指南.md'),
        f'Docker-upgrade-{version}.md': Path(f'docs/权限管理系统结构13升级至{version}指南.md'),
        'Gateway-runbook.md': Path('telemetry-gateway/README.md'),
        'gateway.env.example': Path('telemetry-gateway/gateway.env.example'),
        'service.env.example': Path('access-service/docker/service.env.example'),
        'RELEASE_NOTES.md': Path(f'docs/RELEASE_NOTES_{version}.md'),
    }


def verify(directory, version, revision, digest, gateway_id, release=None, check_msi=False):
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert manifest['release_tag'] == 'v' + version
    assert manifest['component_versions'] == dict.fromkeys(('cli_go', 'access', 'telemetry_gateway'), version)
    assert manifest['image_version'] == version and manifest['image_revision'] == revision
    assert manifest['documents_source_revision'] == revision and manifest['platform'] == 'linux/amd64'
    repository = os.environ['GITHUB_REPOSITORY'].lower()
    assert manifest['image_reference'] == f'ghcr.io/{repository.rsplit("/", 1)[0]}/cli-access@{digest}'
    assert manifest['image_tag'] == f'cli-access:{version}'
    access_file = f'cli-access-{version}-linux-amd64.tar.gz'
    gateway_file = f'wiserec-telemetry-gateway-{version}-linux-amd64.tar.gz'
    gateway_tag = f'wiserec-telemetry-gateway:{version}'
    assert manifest['image_file'] == access_file
    assert manifest['gateway'] == {'file': gateway_file, 'tag': gateway_tag, 'image_id': gateway_id,
                                   'version': version, 'revision': revision, 'platform': 'linux/amd64'}
    zip_name = f'wiserec-cli-{version}-windows-x64.zip'
    msi_name = f'wiserec-cli-{version}-windows-x64.msi'
    assert manifest['cli_packages'] == [msi_name, zip_name]
    docs = documents(version)
    expected = {*docs, access_file, gateway_file, zip_name, msi_name, 'README.md', 'manifest.json', 'SHA256SUMS'}
    assert names_in(directory) == expected
    verify_checksums(directory)
    if release is not None:
        assert release['draft'] and not release['prerelease']
        assert release['tag_name'] == 'v' + version and release['target_commitish'] == revision
        assert release['name'] == f'v{version} — Go CLI、权限管理系统与 DSH 遥测网关'
        assert release['body'].strip() == docs['RELEASE_NOTES.md'].read_text().strip()
        assert {asset['name'] for asset in release['assets']} == expected
        for asset in release['assets']:
            path = directory / asset['name']
            assert asset['size'] == path.stat().st_size
            if asset.get('digest'):
                assert asset['digest'] == 'sha256:' + sha256(path)
    for name, source in docs.items():
        assert (directory / name).read_bytes() == source.read_bytes(), name
    readme = Path('docs/权限管理系统Docker离线导入与运行.md').read_text()
    for key, value in manifest.items():
        if isinstance(value, str):
            readme = readme.replace('{{' + key + '}}', value)
    assert (directory / 'README.md').read_text() == readme
    verify_archive(directory / access_file, manifest['image_tag'], manifest['image_id'], version, revision)
    verify_archive(directory / gateway_file, gateway_tag, gateway_id, version, revision)
    verify_cli(directory / zip_name, directory / msi_name, version, check_msi)


def prepare(directory, windows, gateway, version, revision, digest, gateway_id):
    verify_checksums(directory)
    verify_checksums(gateway)
    gateway_file = f'wiserec-telemetry-gateway-{version}-linux-amd64.tar.gz'
    packages = [f'wiserec-cli-{version}-windows-x64.{ext}' for ext in ('msi', 'zip')]
    assert names_in(windows) == set(packages)
    assert names_in(gateway) == {gateway_file, 'SHA256SUMS'}
    access_file = f'cli-access-{version}-linux-amd64.tar.gz'
    assert names_in(directory) == {access_file, 'README.md', 'service.env.example', 'manifest.json',
                                   'SHA256SUMS', 'Docker-runbook.md', f'Docker-upgrade-{version}.md'}
    for name in packages:
        shutil.copyfile(windows / name, directory / name)
    shutil.copyfile(gateway / gateway_file, directory / gateway_file)
    for name, source in documents(version).items():
        shutil.copyfile(source, directory / name)
    manifest_path = directory / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    manifest.update(release_tag='v' + version, cli_packages=packages,
                    component_versions=dict.fromkeys(('cli_go', 'access', 'telemetry_gateway'), version),
                    gateway={'file': gateway_file, 'tag': f'wiserec-telemetry-gateway:{version}', 'image_id': gateway_id,
                             'version': version, 'revision': revision, 'platform': 'linux/amd64'},
                    validation=[
                        'Windows x64 MSI and portable ZIP, offline MSI lifecycle, legacy Python PATH fixture',
                        'Upgrade from Go 1.1.0 source 350a07de1e3b8e3dc51c1daef2091a86b89ad2e7',
                        'Exact permission image digest with MySQL 8, schema 13 migration and Docker save/load',
                        'Exact gateway image ID with non-root runtime, environment filtering and Docker save/load',
                    ])
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (directory / 'SHA256SUMS').write_text(''.join(
        f'{sha256(path)}  {path.name}\n' for path in sorted(directory.iterdir()) if path.name != 'SHA256SUMS'))
    verify(directory, version, revision, digest, gateway_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subcommands = parser.add_subparsers(dest='command', required=True)
    assemble = subcommands.add_parser('prepare')
    for name in ('directory', 'windows', 'gateway'):
        assemble.add_argument(name, type=Path)
    review = subcommands.add_parser('verify')
    review.add_argument('directory', type=Path)
    review.add_argument('release', type=Path)
    review.add_argument('--check-msi', action='store_true')
    args = parser.parse_args()
    version, revision, digest, gateway_id = (os.environ[key] for key in
        ('VERSION', 'GITHUB_SHA', 'IMAGE_DIGEST', 'GATEWAY_IMAGE_ID'))
    versions = tomllib.loads(Path('versions.toml').read_text())['components']
    assert version == versions['cli_go'] == versions['access'] == versions['telemetry_gateway']
    assert re.fullmatch('[0-9a-f]{40}', revision)
    assert all(re.fullmatch('sha256:[0-9a-f]{64}', value) for value in (digest, gateway_id))
    if args.command == 'prepare':
        prepare(args.directory, args.windows, args.gateway, version, revision, digest, gateway_id)
    else:
        verify(args.directory, version, revision, digest, gateway_id,
               json.loads(args.release.read_text()), args.check_msi)


if __name__ == '__main__':
    main()
