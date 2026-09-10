"""Validate release inputs and assemble the reviewable download manifest."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

out = Path('release-assets')
version = os.environ['VERSION']
revision = os.environ['GITHUB_SHA']
subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out, check=True)
manifest = json.loads((out / 'manifest.json').read_text())
assert manifest['image_version'] == version
assert manifest['image_revision'] == revision
assert manifest['image_reference'].endswith('@' + os.environ['IMAGE_DIGEST'])
assert manifest['image_tag'] == f'cli-access:{version}'
assert (out / manifest['image_file']).is_file()
wheel = out / f'wiserec_cli-{version}-py3-none-any.whl'
assert wheel.is_file()
with ZipFile(wheel) as z:
    metadata = [n for n in z.namelist() if n.endswith('.dist-info/METADATA')]
    assert len(metadata) == 1
    assert f'Version: {version}\n' in z.read(metadata[0]).decode()
archives = sorted(out.glob('*.zip'))
assert len(archives) == 2
cli = []
for archive in archives:
    with ZipFile(archive) as z:
        names = z.namelist()
        meta = [n for n in names if n.endswith('/release.json')]
        assert len(meta) == 1
        data = json.loads(z.read(meta[0]).decode('utf-8-sig'))
        assert data['version'] == version
        if data['mode'] == 'offline':
            assert data['architecture'] == 'x64'
            assert (data['python_major'], data['python_minor']) == (3, 12)
        inner_wheels = [n for n in names if n.endswith('/' + wheel.name) and '/packages/' not in n]
        assert len(inner_wheels) == 1
        assert z.read(inner_wheels[0]) == wheel.read_bytes(), 'CLI bundles must share the same wheel'
        cli.append({'file': archive.name, **data})
manifest['cli_packages'] = cli
manifest['release_tag'] = 'v' + version
manifest['validation'] = [
    'CLI and service unit tests', 'Browser timezone tests',
    'MySQL Docker smoke, directory mount and configuration restart',
    'Docker save/load round trip', 'Windows online and offline install',
    'Windows upgrade from 0.3.42',
]
(out / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
shutil.copyfile('docs/权限管理系统Docker安装部署与调试指南.md', out / 'Docker部署速查.md')
shutil.copyfile('scripts/windows/INSTALL.md', out / 'CLI安装指南.md')
shutil.copyfile('docs/CLI参考使用指南.md', out / 'CLI参考使用指南.md')
lines = []
for path in sorted(out.iterdir()):
    if path.name != 'SHA256SUMS':
        lines.append(f'{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}')
(out / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
subprocess.run(['sha256sum', '-c', 'SHA256SUMS'], cwd=out, check=True)
