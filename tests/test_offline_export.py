"""Offline export documentation must belong to the image revision."""
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).parents[1]


def test_export_uses_exact_revision_and_includes_chinese_upgrade_guide(tmp_path, monkeypatch):
    revision = 'a' * 40
    version = '1.0.9.1'
    sources = {
        'access-service/docker/service.env.example': 'example only',
        'docs/权限管理系统Docker离线导入与运行.md': '{{image_tag}} {{image_revision}}',
        'docs/权限管理系统Docker安装部署与调试指南.md': 'cli-access:1.0.9.1 权限管理系统结构12升级至1.0.9.1指南.md',
        'docs/权限管理系统结构12升级至1.0.9.1指南.md': 'cli-access:1.0.9.1 cli-access-1.0.9.1-linux-amd64.tar.gz',
        'docs/ACCESS_RELEASE_NOTES_1.0.9.1.md': '环境禁止命令开发与迁移说明.md',
        'docs/环境禁止命令开发与迁移说明.md': 'schema 12 to 13',
    }
    calls = []

    def source_output(args):
        calls.append(args)
        if args[1] == 'show':
            assert args[2].startswith(revision + ':')
            return sources[args[2].split(':', 1)[1]].encode()
        assert args == ['git', 'ls-tree', '-rz', '--name-only', revision, 'docs']
        return ('\0'.join(sources) + '\0').encode()

    monkeypatch.setattr(subprocess, 'check_output', source_output)
    values = dict(OUTPUT_DIR=str(tmp_path), IMAGE_REFERENCE='ghcr.io/example/cli-access@sha256:' + 'b' * 64,
                  IMAGE_ID='sha256:' + 'c' * 64, IMAGE_TAG='cli-access:1.0.9.1-aaaaaaaaaaaa',
                  IMAGE_FILE='candidate.tar.gz', IMAGE_VERSION=version, IMAGE_REVISION=revision)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    source = (ROOT / 'access-service/ci/export-image.sh').read_text().split("python - <<'PY'\n", 1)[1].split('\nPY\n', 1)[0]
    exec(compile(source, 'export-metadata', 'exec'), {})
    assert (tmp_path / 'Docker-upgrade-1.0.9.1.md').read_text() == values['IMAGE_TAG'] + ' candidate.tar.gz'
    assert 'Docker-upgrade-1.0.9.1.md' in (tmp_path / 'Docker-runbook.md').read_text()
    assert (tmp_path / 'RELEASE_NOTES.md').read_text() == 'Migration-notes.md'
    assert (tmp_path / 'Migration-notes.md').read_text() == 'schema 12 to 13'
    assert json.loads((tmp_path / 'manifest.json').read_text())['documents_source_revision'] == revision
    assert calls
