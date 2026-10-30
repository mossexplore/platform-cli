"""Immutable, session/business-scoped attachments. No model-supplied local paths."""
import hashlib
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from .errors import AppError

MAX_BYTES = 20 * 1024 * 1024


class Artifacts:
    def __init__(self, config, session_id, business):
        scope = hashlib.sha256(json.dumps(business, sort_keys=True).encode()).hexdigest()
        self.root = config.runtime.state_dir / 'artifacts' / session_id / scope

    def metadata(self, key):
        if not re.fullmatch(r'[0-9a-f]{32}', key):
            raise AppError('ARTIFACT_NOT_FOUND', '附件不存在', 404)
        try:
            return json.loads((self.root / key / 'metadata.json').read_text())
        except FileNotFoundError:
            raise AppError('ARTIFACT_NOT_FOUND', '附件不存在或不属于当前会话和业务', 404) from None

    def path(self, key, kind=None):
        meta = self.metadata(key)
        if kind and meta['kind'] != kind:
            raise AppError('ARTIFACT_KIND', '附件类型不匹配')
        path = self.root / key / meta['name']
        if not path.is_file() or path.is_symlink():
            raise AppError('ARTIFACT_NOT_FOUND', '附件不存在', 404)
        return path

    def put(self, name, data, kind='file'):
        if len(data) > MAX_BYTES:
            raise AppError('FILE_TOO_LARGE', '附件超过 20 MiB 限制', 413)
        # Preserve safe extension for CLI validators. Never trust a path from upstream.
        name = re.sub(r'[^A-Za-z0-9_.-]', '_', name.replace('\\', '/').rsplit('/', 1)[-1])
        name = name.strip('.')[:120] or 'attachment.bin'
        if name == 'metadata.json': name = 'attachment.json'
        key = uuid4().hex
        directory = self.root / key
        directory.mkdir(parents=True, mode=0o700)
        try:
            (directory / name).write_bytes(data)
            meta = {'artifact_id': key, 'name': name, 'bytes': len(data), 'kind': kind,
                    'sha256': hashlib.sha256(data).hexdigest(), 'download_url': '/api/artifacts/' + key}
            (directory / 'metadata.json').write_text(json.dumps(meta))
            return meta
        except BaseException:
            shutil.rmtree(directory)
            raise


def prune(config, active_sessions):
    """Remove revoked-session files and attachments older than the audit retention."""
    import time
    root = config.runtime.state_dir / 'artifacts'
    if not root.exists(): return
    cutoff = time.time() - config.runtime.event_retention_hours * 3600
    for session in root.iterdir():
        if session.is_symlink(): continue
        if session.name not in active_sessions:
            shutil.rmtree(session, ignore_errors=True)
            continue
        for meta in session.glob('*/*/metadata.json'):
            if meta.stat().st_mtime < cutoff:
                shutil.rmtree(meta.parent, ignore_errors=True)
