"""One atomically replaced JSON file; callers never mutate shared references."""
import copy
import json
import os
from pathlib import Path
import tempfile
import threading
from uuid import uuid4
from .config import Config


class StoreError(RuntimeError):
    pass


class Conflict(StoreError):
    pass


def initial():
    return {'file_version': 1, 'config_revision': 1, 'config': Config().model_dump(),
            'state': {'installation_id': str(uuid4()), 'paused': True,
                      'active_config_revision': 1, 'config_apply': {'pending_fields': [], 'effective_overrides': {}},
                      'tasks': {}, 'pending_reports': [], 'last_success_at': None, 'last_error': None}}


def outstanding(data):
    return bool(data['state']['pending_reports'] or any(not t.get('closed') for t in data['state']['tasks'].values()))


def effective(data):
    result = copy.deepcopy(data['config'])
    result.update(data['state']['config_apply']['effective_overrides'])
    return result


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.fault = ''
        try:
            if self.path.exists():
                raw = json.loads(self.path.read_text(encoding='utf-8'))
                if raw['file_version'] != 1:
                    raise ValueError('文件版本不兼容')
                raw['config'] = Config.model_validate(raw['config']).model_dump()
                state = raw['state']
                if not isinstance(state['tasks'], dict) or not isinstance(state['pending_reports'], list):
                    raise ValueError('状态格式错误')
                if not isinstance(state['installation_id'], str) or len(state['installation_id']) < 8:
                    raise ValueError('实例编号无效')
                state['config_apply']['effective_overrides']
                self.data = raw
            else:
                self.data = initial()
                self._write(self.data)
        except (ValueError, KeyError, TypeError, OSError):
            self.data = initial()
            self.fault = '配置文件损坏、版本不兼容或无法读取；已停止发送，请退出并恢复有效文件'

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='assistant.', suffix='.tmp', dir=self.path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as file:
                json.dump(data, file, ensure_ascii=False, indent=2, allow_nan=False)
                file.write('\n')
                file.flush()
                os.fsync(file.fileno())
            os.replace(name, self.path)
            if os.name != 'nt':
                os.chmod(self.path, 0o600)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.data)

    def change(self, operation):
        with self.lock:
            if self.fault:
                raise StoreError(self.fault)
            updated = copy.deepcopy(self.data)
            result = operation(updated)
            try:
                self._write(updated)
            except (OSError, ValueError, TypeError):
                self.fault = '无法安全保存状态；已停止发送，请检查文件权限与磁盘后重启'
                raise StoreError(self.fault) from None
            self.data = updated
            return result

    def configure(self, revision, values, secrets):
        def apply(data):
            if revision != data['config_revision']:
                raise Conflict('配置已被其他页面修改，请刷新后再保存')
            values_copy = copy.deepcopy(values)
            for field, target in [('assistant_token', values_copy), ('auth', values_copy['message'])]:
                old = data['config'][field] if field == 'assistant_token' else data['config']['message'][field]
                secret = secrets.get(field, {'action': 'retain'})
                if secret['action'] == 'retain':
                    target[field] = old
                elif secret['action'] == 'clear':
                    target[field] = ''
                elif secret['action'] == 'replace':
                    target[field] = secret.get('value', '')
                else:
                    raise ValueError('无效凭据操作')
            new = Config.model_validate(values_copy).model_dump()
            old_effective = effective(data)
            # Cancelling a staged server switch with "retain" means retaining
            # the still-active old credential, not the proposed new server's.
            if (data['state']['config_apply']['pending_fields'] and
                    new['permission_service_url'] == old_effective['permission_service_url'] and
                    secrets.get('assistant_token', {'action': 'retain'})['action'] == 'retain'):
                new['assistant_token'] = old_effective['assistant_token']
            data['config'] = new
            data['config_revision'] += 1
            delayed = data['state']['config_apply']
            if new['permission_service_url'] != old_effective['permission_service_url'] and outstanding(data):
                delayed['pending_fields'] = ['permission_service_url', 'assistant_token', 'service_network']
                delayed['effective_overrides'] = {k: old_effective[k] for k in delayed['pending_fields']}
            else:
                delayed.update(pending_fields=[], effective_overrides={})
                data['state']['active_config_revision'] = data['config_revision']
            return {'saved_revision': data['config_revision'],
                    'apply_state': 'waiting_action' if delayed['pending_fields'] else 'applied'}
        return self.change(apply)

    def apply_pending(self):
        data = self.snapshot()
        if data['state']['config_apply']['pending_fields'] and not outstanding(data):
            def apply(value):
                value['state']['config_apply'] = {'pending_fields': [], 'effective_overrides': {}}
                value['state']['active_config_revision'] = value['config_revision']
            self.change(apply)

    def public_config(self):
        data = self.snapshot()
        config = data['config']
        has = {'assistant_token': bool(config.pop('assistant_token')),
               'auth': bool(config['message'].pop('auth'))}
        return {'config': config, 'secrets_configured': has, 'config_revision': data['config_revision'],
                'pending_fields': data['state']['config_apply']['pending_fields']}
