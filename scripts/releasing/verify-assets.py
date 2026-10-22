"""Independently verify freshly downloaded draft assets without modifying them."""
from email.parser import BytesParser
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tarfile
import tomllib
from zipfile import ZipFile


def verify(directory, release, version, revision, digest):
    expected = {
        f'wiserec-cli-{version}-windows-py3-online.zip',
        f'wiserec-cli-{version}-windows-x64-py312-offline.zip',
        f'wiserec_cli-{version}-py3-none-any.whl',
        f'permission-notifier-{version}-windows-source.zip',
        f'cli-access-{version}-linux-amd64.tar.gz',
        'CLI-install.md', 'CLI-reference.md', 'Notifier-install.md', 'Docker-runbook.md',
        f'Docker-upgrade-{version}.md', 'README.md', 'service.env.example', 'manifest.json', 'SHA256SUMS',
    }
    assert release['draft'] and not release['prerelease']
    assert release['tag_name'] == 'v' + version and release['target_commitish'] == revision
    assert release['body'].strip() == Path(f'docs/RELEASE_NOTES_{version}.md').read_text().strip()
    assert {a['name'] for a in release['assets']} == expected
    assert {p.name for p in directory.iterdir()} == expected
    checksums = {}
    for line in (directory / 'SHA256SUMS').read_text().splitlines():
        value, name = line.split('  ', 1)
        assert name not in checksums
        checksums[name] = value
    assert set(checksums) == expected - {'SHA256SUMS'}
    for asset in release['assets']:
        path = directory / asset['name']
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert path.stat().st_size == asset['size']
        if path.name != 'SHA256SUMS':
            assert actual == checksums[path.name], path.name
        if asset.get('digest'):
            assert asset['digest'] == 'sha256:' + actual, path.name
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert manifest['release_tag'] == 'v' + version
    assert manifest['cli_version'] == manifest['image_version'] == version
    assert manifest['image_revision'] == revision and manifest['platform'] == 'linux/amd64'
    assert manifest['image_tag'] == 'cli-access:' + version
    assert manifest['image_reference'] == 'ghcr.io/mossexplore/cli-access@' + digest
    wheel = directory / f'wiserec_cli-{version}-py3-none-any.whl'
    check_cli = runpy.run_path('scripts/releasing/check-cli-package.py')['check']
    check_cli(wheel)
    with ZipFile(wheel) as z:
        metadata, = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
        assert BytesParser().parsebytes(z.read(metadata))['Version'] == version
        assert f'__version__ = "{version}"' in z.read('wiserec_cli/__init__.py').decode()
    for package in manifest['cli_packages']:
        path = directory / package['file']
        check_cli(path)
        with ZipFile(path) as z:
            names = {n.replace('\\', '/'): n for n in z.namelist()}
            meta, = [n for n in names if n.endswith('/release.json')]
            data = json.loads(z.read(names[meta]).decode('utf-8-sig'))
            assert data['version'] == version and data['platform'] == 'windows'
            assert package == {'file': path.name, **data}
            if data['mode'] == 'offline':
                assert (data['python_major'], data['python_minor'], data['architecture']) == (3, 12, 'x64')
            copies = [n for n in names if n.endswith('/' + wheel.name)]
            assert copies and all(z.read(names[n]) == wheel.read_bytes() for n in copies)
    assert {p['mode'] for p in manifest['cli_packages']} == {'online', 'offline'}
    assistant = manifest['notifier_package']
    assert assistant['version'] == version and assistant['revision'] == revision
    prefix = f'permission-notifier-{version}-windows-source/'
    with ZipFile(directory / assistant['file']) as z:
        data = json.loads(z.read(prefix + 'release.json'))
        assert assistant == {'file': assistant['file'], **data}
        assert data['mode'] == 'source-online' and data['platform'] == 'windows' and data['python'] == '3.12'
        assert set(z.namelist()) == {prefix + n for n in data['files']} | {prefix + 'release.json'}
        assert tomllib.loads(z.read(prefix + 'pyproject.toml').decode())['project']['version'] == version
        assert f"__version__ = '{version}'" in z.read(prefix + 'src/permission_notifier/__init__.py').decode()
        for name, value in data['files'].items():
            content = z.read(prefix + name)
            assert hashlib.sha256(content).hexdigest() == value
            assert content == (Path('permission-notifier') / name).read_bytes()
    docs = {
        'CLI-install.md': 'scripts/windows/INSTALL.md',
        'CLI-reference.md': 'docs/WiseRec CLI 使用手册.md',
        'Notifier-install.md': 'permission-notifier/README.md',
        'Docker-runbook.md': 'docs/权限管理系统Docker安装部署与调试指南.md',
        f'Docker-upgrade-{version}.md': f'docs/权限管理系统1.0.7.1升级至{version}指南.md',
        'service.env.example': 'access-service/docker/service.env.example',
    }
    for name, source in docs.items():
        assert (directory / name).read_bytes() == Path(source).read_bytes(), name
    template = Path('docs/权限管理系统Docker离线导入与运行.md').read_text()
    for key, value in manifest.items():
        if isinstance(value, str):
            template = template.replace('{{' + key + '}}', value)
    assert (directory / 'README.md').read_text() == template
    assert manifest['image_file'] == f'cli-access-{version}-linux-amd64.tar.gz'
    with tarfile.open(directory / manifest['image_file'], 'r:gz') as archive:
        images = json.load(archive.extractfile('manifest.json'))
        assert len(images) == 1 and images[0]['RepoTags'] == [manifest['image_tag']]
        config = archive.extractfile(images[0]['Config']).read()
        assert 'sha256:' + hashlib.sha256(config).hexdigest() == manifest['image_id']
        config = json.loads(config)
        assert (config['os'], config['architecture']) == ('linux', 'amd64')
        labels = config['config']['Labels']
        assert labels['org.opencontainers.image.version'] == version
        assert labels['org.opencontainers.image.revision'] == revision
    return manifest


if __name__ == '__main__':
    directory, release_file = map(Path, sys.argv[1:])
    manifest = verify(directory, json.loads(release_file.read_text()), os.environ['VERSION'],
           os.environ['GITHUB_SHA'], os.environ['IMAGE_DIGEST'])
    print(json.dumps({key: manifest[key] for key in ('release_tag', 'image_revision', 'image_reference', 'image_id')}, indent=2))
    print('Verified all 14 downloaded draft assets: hashes, versions, source, CLI isolation, docs and Docker archive identity')
