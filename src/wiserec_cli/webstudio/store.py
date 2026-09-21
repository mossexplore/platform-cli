"""按配置、环境、账号及业务隔离默认实例；不持久化 Token。"""
import hashlib
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

from ..config import user_config_dir
from ..errors import ConfigError


class SelectionStore:
    def __init__(self, path=None):
        self.path = path or user_config_dir() / 'webstudio.json'

    @staticmethod
    def key(runtime, username, business_id):
        profile = runtime.config.current_profile()
        settings = runtime.config.jupyter_settings()
        mapping = settings.get('server_urls_by_region')
        if mapping is None:
            # 保留旧版键格式，使继续使用单一 server_url 的默认实例无缝升级。
            scope = [str(runtime.config.path.resolve()), profile.name, profile.api_endpoint,
                     settings.get('server_url'), username, business_id]
            return hashlib.sha256(json.dumps(scope, ensure_ascii=False).encode()).hexdigest()
        routing = {'server_urls_by_region': mapping}
        scope = [str(runtime.config.path.resolve()), profile.name, profile.api_endpoint,
                 routing, username, business_id]
        return hashlib.sha256(json.dumps(
            scope, ensure_ascii=False, sort_keys=True, separators=(',', ':')
        ).encode()).hexdigest()

    def _read(self):
        if not self.path.exists():
            return {'version': 1, 'selections': {}}
        try:
            value = json.loads(self.path.read_text(encoding='utf-8'))
            if value['version'] != 1 or not isinstance(value['selections'], dict):
                raise ValueError()
            return value
        except (ValueError, KeyError, TypeError):
            raise ConfigError('webstudio.json 无效，请备份后修复') from None

    def get(self, key):
        value = self._read()['selections'].get(key)
        if value is not None and (not isinstance(value, dict) or not isinstance(value.get('envId'), str)):
            raise ConfigError('Web Studio 默认实例记录无效')
        return value

    def save(self, key, item):
        value = self._read()
        value['selections'][key] = {'envId': item['envId'], 'labelName': item.get('labelName', ''),
                                   'region': item.get('region', ''),
                                   'selectedAt': datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.webstudio-', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump(value, stream, ensure_ascii=False, indent=2)
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)
