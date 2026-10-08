"""短期连接缓存；文件锁去重发现请求，代际校验防止旧请求覆盖新会话。"""
import hashlib
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from ..errors import ConfigError


def cache_ttl(settings):
    value = settings.get('connection_cache_ttl_seconds', 300)
    if type(value) is not int or not 0 <= value <= 3600:
        raise ConfigError('jupyter.connection_cache_ttl_seconds 必须为 0–3600 的整数，0 禁用缓存')
    return value


class ConnectionCache:
    def __init__(self, credential_path, profile):
        self.root = Path(credential_path).parent / 'webstudio-connections'
        self.path = self.root / (hashlib.sha256(profile.encode()).hexdigest() + '.json')

    @staticmethod
    def key(scope, target, credentials, settings):
        value = [scope, target, credentials.cookie, credentials.csrftoken,
                 settings.get('ca_file'), cache_ttl(settings)]
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    @contextmanager
    def locked(self):
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != 'nt':
            self.root.chmod(0o700)
        fd = os.open(self.path.with_suffix('.lock'), os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(fd, 'a+b') as lock:
            deadline = time.monotonic() + 35
            while True:
                try:
                    if os.name == 'nt':
                        import msvcrt
                        if lock.seek(0, os.SEEK_END) == 0:
                            lock.write(b'0')
                            lock.flush()
                        lock.seek(0)
                        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise ConfigError('等待 Web Studio 连接缓存锁超时，请稍后重试') from None
                    time.sleep(0.05)
            try:
                yield
            finally:
                if os.name == 'nt':
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def read(self):
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict):
                return {}
            now = time.time()
            return {key: entry for key, entry in data.items()
                    if isinstance(entry, dict) and type(entry.get('expires_at')) in (int, float)
                    and math.isfinite(entry['expires_at']) and now < entry['expires_at'] <= now + 3600
                    and all(isinstance(entry.get(k), str) for k in ('url', 'token', 'generation'))
                    and isinstance(entry.get('cookies'), list)}
        except (OSError, ValueError):
            return {}

    def write(self, data):
        fd, temporary = tempfile.mkstemp(prefix='.connection-', dir=self.root)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(data, stream)
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)

    def put(self, key, url, token, ttl):
        """调用者持有锁，时间从发现成功开始计算，不滑动续期。"""
        data = self.read()
        entry = dict(url=url, token=token, expires_at=time.time() + ttl,
                     generation=str(uuid4()), cookies=[], session_ready=False)
        data[key] = entry
        self.write(data)
        return entry

    def invalidate(self, key, generation):
        with self.locked():
            data = self.read()
            if data.get(key, {}).get('generation') == generation:
                data.pop(key)
                self.write(data)

    def save_session(self, key, generation, cookies):
        """调用者持有锁；不得复活退出登录、刷新或过期后的旧连接。"""
        data = self.read()
        entry = data.get(key)
        if not entry or entry['generation'] != generation:
            return
        entry.update(cookies=cookies, session_ready=True)
        expiries = [c['expires'] for c in cookies if c.get('expires') is not None]
        if expiries:
            entry['expires_at'] = min(entry['expires_at'], min(expiries) - 10)
        self.write(data)

    @classmethod
    def clear(cls, credential_path, profile=None):
        root = Path(credential_path).parent / 'webstudio-connections'
        if not root.exists():
            return
        paths = [cls(credential_path, profile).path] if profile else list(root.glob('*.json'))
        for path in paths:
            cache = cls(credential_path, profile or '')
            cache.path = path
            with cache.locked():
                path.unlink(missing_ok=True)
