"""Verify reused CLI downloads against the immutable v1.0.3 release checksum list."""
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import sys
import tomllib
from zipfile import ZipFile


assets = Path(sys.argv[1])
checksums = Path(sys.argv[2]) if len(sys.argv) > 2 else assets / 'SHA256SUMS'
version = tomllib.loads(Path('pyproject.toml').read_text())['project']['version']
assert version == '1.0.3'
names = [
    f'wiserec-cli-{version}-windows-py3-online.zip',
    f'wiserec-cli-{version}-windows-x64-py312-offline.zip',
    f'wiserec_cli-{version}-py3-none-any.whl',
]
published = dict(line.split('  ', 1) for line in checksums.read_text().splitlines())
published = {name: digest for digest, name in published.items()}
assert all(name in published for name in names)
wheel = (assets / names[2]).read_bytes()
for name in names:
    assert hashlib.sha256((assets / name).read_bytes()).hexdigest() == published[name], name
for name in ('CLI-install.md', 'CLI-reference.md'):
    if (assets / name).exists():
        assert hashlib.sha256((assets / name).read_bytes()).hexdigest() == published[name], name
with ZipFile(assets / names[2]) as archive:
    metadata = [name for name in archive.namelist() if name.endswith('.dist-info/METADATA')]
    assert len(metadata) == 1
    assert BytesParser().parsebytes(archive.read(metadata[0]))['Version'] == version
for filename, mode in zip(names[:2], ('online', 'offline')):
    with ZipFile(assets / filename) as archive:
        members = {name.replace('\\', '/'): name for name in archive.namelist()}
        release = [name for name in members if name.endswith('/release.json')]
        bundled = [name for name in members if name.endswith('/' + names[2]) and '/packages/' not in name]
        assert len(release) == len(bundled) == 1
        data = json.loads(archive.read(members[release[0]]).decode('utf-8-sig'))
        assert data['version'] == version and data['mode'] == mode
        if mode == 'offline':
            assert (data['python_major'], data['python_minor'], data['architecture']) == (3, 12, 'x64')
        assert archive.read(members[bundled[0]]) == wheel
print(f'Published CLI {version} assets verified: {len(names)} files')
