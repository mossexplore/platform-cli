"""Settings and delivery state in separate atomic files, with legacy migration."""
import copy
import json
import os
from pathlib import Path
import threading
from uuid import uuid4
from .config import Config
from .storage_files import split, read, atomic_write
from .records import rows as record_rows


class StoreError(RuntimeError):
    pass


class Conflict(StoreError):
    pass


def initial():
    return {'file_version': 1, 'config_revision': 1, 'config': Config().model_dump(),
            'state': {'installation_id': str(uuid4()), 'paused': True,
                      'active_config_revision': 1, 'config_apply': {'pending_fields': [], 'effective_overrides': {}},
                      'tasks': {}, 'send_records': {}, 'pending_reports': [], 'last_success_at': None, 'last_error': None}}


def outstanding(data):
    return bool(data['state']['pending_reports'] or any(not t.get('closed') for t in data['state']['tasks'].values()))


def effective(data):
    result = copy.deepcopy(data['config'])
    result.update(data['state']['config_apply']['effective_overrides'])
    return result


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.records_path = self.path.with_name('send-records.json')
        self.lock = threading.RLock()
        self.fault = ''
        try:
            if self.path.exists():
                raw, migrate = read(self.path, self.records_path)
                raw['config'] = Config.model_validate(raw['config']).model_dump()
                state = raw['state']
                if not isinstance(state['tasks'], dict) or not isinstance(state['pending_reports'], list):
                    raise ValueError('状态格式错误')
                if not isinstance(state['installation_id'], str) or len(state['installation_id']) < 8:
                    raise ValueError('实例编号无效')
                state['config_apply']['effective_overrides']
                state.setdefault('send_records', {})
                if not isinstance(state['send_records'], dict):
                    raise ValueError('发送记录格式错误')
                self.data = raw
                legacy = {row['id']: row for row in record_rows(raw) if row['id'].startswith('legacy:') and row['id'] not in state['send_records']}
                if legacy:
                    updated = copy.deepcopy(raw)
                    updated['state']['send_records'].update(legacy)
                    if not migrate:
                        self._write(updated)
                    self.data = updated
                if migrate:
                    self._write(self.data, initialize=True)
            else:
                if self.records_path.exists():
                    raise ValueError('配置缺失，已有发送记录不能丢弃')
                self.data = initial()
                self._write(self.data, initialize=True)
        except (ValueError, KeyError, TypeError, OSError):
            self.data = initial()
            self.fault = '配置或发送记录文件损坏、缺失、版本不兼容或无法读取；已停止发送，请退出并恢复有效文件'

    def _write(self, data, initialize=False):
        settings, records = split(data)
        before_settings, before_records = split(self.data)
        write_settings = initialize or settings != before_settings
        write_records = initialize or records != before_records
        # Each normal operation changes exactly one document. Never pretend two
        # separate os.replace calls are a single atomic transaction.
        if not initialize and write_settings and write_records:
            raise ValueError('配置与发送状态不能在同一操作中同时修改')
        if write_records:
            atomic_write(self.records_path, records)
        if write_settings:
            atomic_write(self.path, settings)

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
