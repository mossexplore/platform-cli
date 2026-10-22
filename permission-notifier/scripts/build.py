"""Build a private source installer ZIP from an explicit allowlist."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import tomllib
import hashlib
import json
import os

root = Path(__file__).resolve().parents[1]
version = tomllib.loads((root / 'pyproject.toml').read_text())['project']['version']
name = f'permission-notifier-{version}-windows-source'
output = root / 'dist'
output.mkdir(exist_ok=True)
files = [root / p for p in ('pyproject.toml', 'MANIFEST.in', 'README.md', '.gitignore')]
for folder, suffixes in [('src/permission_notifier', {'.py', '.html', '.css', '.js'}),
                         ('scripts', {'.ps1', '.py'}), ('tests', {'.py'})]:
    files += [p for p in (root / folder).rglob('*') if p.is_file() and p.suffix in suffixes
              and '__pycache__' not in p.parts]
with ZipFile(output / f'{name}.zip', 'w', compression=ZIP_DEFLATED) as archive:
    archive.writestr(name + '/release.json', json.dumps({
        'version': version, 'revision': os.environ.get('GITHUB_SHA', 'local-uncommitted'),
        'platform': 'windows', 'python': '3.12', 'mode': 'source-online',
        'files': {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)},
    }, indent=2) + '\n')
    for file in sorted(files):
        archive.write(file, name + '/' + file.relative_to(root).as_posix())
print(output / f'{name}.zip')
