"""One sending lane; file writes and server checkpoints precede side effects."""
import threading
import time
import logging
import hashlib
from . import __version__
from .config import ready
from .delivery import Deliveries, TERMINAL
from .service import Service, ServiceError
from .sender import Sender
from .store import effective, StoreError


class Worker:
    def __init__(self, store, service=None, sender=None):
        self.store = store
        self.service, self.sender = service or Service(), sender or Sender()
        self.deliveries = Deliveries(store, self.service)
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.operation = threading.RLock()
        self.thread = None
        self.last_loop = 0
        self.last_poll = 0
        self.last_heartbeat = 0
        self.bound_signature = None
        self.restored = set()
        self.error = ''
        self.sending = False
        self.auth_block = None
        self.last_config_revision = None
        self.tests = []
        self.test_results = []
        self.client_info = {}

    def start(self):
        self.thread = threading.Thread(target=self.run, name='notification-worker', daemon=True)
        self.thread.start()

    def run(self):
        while not self.stop.is_set():
            try:
                with self.operation:
                    self.tick()
            except (ServiceError, StoreError) as exc:
                self.error = exc.code if isinstance(exc, ServiceError) else 'STORAGE_ERROR'
                logging.getLogger(__name__).warning('通知工作暂停：%s', self.error)
                if isinstance(exc, ServiceError) and exc.code == 'LEASE_CONFLICT':
                    self.restored.clear()
            except Exception:
                self.error = 'WORKER_ERROR'
                logging.getLogger(__name__).error('通知工作异常；发送状态已保留，请查看本地页面')
            self.last_loop = time.time()
            self.wake.wait(1 if not self.error else 10)
            self.wake.clear()

    def bind(self):
        data = self.store.snapshot()
        config = effective(data)
        result = self.service.call(config, data['state']['installation_id'], 'bind')
        self.client_info = result
        self.bound_signature = (config['permission_service_url'], config['assistant_token'])
        self.last_heartbeat = 0
        self.restored.clear()
        return result

    def tick(self):
        self.last_loop = time.time()
        if self.store.fault:
            raise StoreError(self.store.fault)
        self.store.apply_pending()
        data = self.store.snapshot()
        config = effective(data)
        if data['config_revision'] != self.last_config_revision:
            self.last_poll = 0
            self.last_config_revision = data['config_revision']
        if self.auth_block and self.auth_block != config['message']['auth']:
            self.auth_block = None
        if self.tests:
            self.run_test()
            return
        if not config['permission_service_url'] or not config['assistant_token']:
            self.error = 'UNCONFIGURED'
            return
        signature = (config['permission_service_url'], config['assistant_token'])
        if signature != self.bound_signature:
            self.bind()
        if time.time() - self.last_heartbeat >= 60:
            attention = any(i['state'] in {'uncertain', 'failed'} for t in data['state']['tasks'].values()
                            for i in t['deliveries'].values())
            self.client_info = self.deliveries.call('heartbeat', {'agent_version': __version__,
                'health_code': 'auth_error' if self.auth_block else 'needs_attention' if attention else
                               'paused' if data['state']['paused'] else 'running'})
            self.last_heartbeat = time.time()
        for task_id, task in data['state']['tasks'].items():
            if task['closed'] or task['source'] != config['permission_service_url']:
                continue
            if task_id not in self.restored:
                self.deliveries.restore(task_id)
                self.restored.add(task_id)
        self.deliveries.flush()
        self.error = ''
        self.prune_confirmed()
        if data['state']['paused'] or self.stop.is_set():
            return
        if not ready(config):
            self.error = 'SUCCESS_RULE_OR_CONFIG_REQUIRED'
            return
        if self.auth_block:
            self.error = 'MESSAGE_AUTH_REJECTED'
            return
        data = self.store.snapshot()
        for task_id, task in data['state']['tasks'].items():
            if task['closed'] or task['source'] != config['permission_service_url']:
                continue
            if task['route'] != {k: config['message'][k] for k in ('url', 'sender')}:
                self.error = 'ROUTE_CHANGE_NEEDS_ACTION'
                continue
            # Terminal tasks are periodically refreshed for owner retry directives.
            if time.time() - task.get('updated_at', 0) > 30 or any(
                    r['state'] in {'pending', 'retry_wait', 'sending'} for r in task['deliveries'].values()):
                self.deliveries.renew(task_id)
            task = self.deliveries.task(task_id)
            auth_digest = hashlib.sha256(config['message']['auth'].encode()).hexdigest()
            for key, item in task['deliveries'].items():
                if item.get('error_code') == 'MESSAGE_AUTH_REJECTED' and item['state'] == 'failed':
                    if item.get('rejected_auth_digest') == auth_digest:
                        self.auth_block = config['message']['auth']
                        self.error = 'MESSAGE_AUTH_REJECTED'
                        return
                    if item.get('rejected_auth_digest'):
                        self.deliveries.report(task_id, key, 'pending', manual=True)
            for key, action in task['remote'].get('actions', {}).items():
                if action == 'retry' and task['deliveries'][key]['state'] == 'failed':
                    self.deliveries.report(task_id, key, 'pending', manual=True)
            for key, item in self.deliveries.task(task_id)['deliveries'].items():
                if item['state'] == 'sending':
                    self.deliveries.report(task_id, key, 'uncertain', 'INTERRUPTED')
                    return
                if item['state'] not in {'pending', 'retry_wait'} or item.get('next_attempt_at', 0) > time.time():
                    continue
                if not task['remote']['application_pending']:
                    self.deliveries.report(task_id, key, 'skipped')
                    return
                self.send_one(task_id, key)
                return
        if not data['state']['config_apply']['pending_fields'] and time.time() - self.last_poll >= config['poll_interval_seconds']:
            self.last_poll = time.time()
            claimed = self.deliveries.call('claim')['task']
            if claimed:
                self.deliveries.remember(claimed, config)
                self.deliveries.prepare(claimed['id'])
                self.restored.add(claimed['id'])

    def send_one(self, task_id, key):
        data = self.store.snapshot()
        if data['state']['paused'] or self.stop.is_set():
            return
        config = effective(data)
        task = self.deliveries.task(task_id)
        if task['route'] != {k: config['message'][k] for k in ('url', 'sender')}:
            self.error = 'ROUTE_CHANGE_NEEDS_ACTION'
            return
        self.deliveries.report(task_id, key, 'sending')
        if self.store.snapshot()['state']['paused'] or self.stop.is_set():
            # Checkpoint was sent but no message was initiated; settle explicitly.
            self.deliveries.report(task_id, key, 'retry_wait', 'PAUSED_BEFORE_SEND')
            return
        task = self.deliveries.task(task_id)
        self.sending = True
        try:
            result = self.sender.send(config, task['route'], task['deliveries'][key]['uid'], task['content'])
        finally:
            self.sending = False
        if result['state'] == 'retry_wait' and task['deliveries'][key]['attempts'] >= 8:
            result['state'] = 'failed'
        if result.get('error_code') == 'MESSAGE_AUTH_REJECTED':
            self.auth_block = config['message']['auth']
            self.store.change(lambda d: d['state']['tasks'][task_id]['deliveries'][key].update(
                rejected_auth_digest=hashlib.sha256(config['message']['auth'].encode()).hexdigest()))
        self.deliveries.report(task_id, key, result['state'], result.get('error_code', ''))

    def resolve(self, task_id, key, action):
        with self.operation:
            if action not in ('retry', 'confirm', 'skip', 'migrate_route'):
                raise ValueError('无效操作')
            self.deliveries.restore(task_id)
            if action == 'migrate_route':
                task = self.deliveries.task(task_id)
                if any(i['state'] in {'sending', 'uncertain'} for i in task['deliveries'].values()):
                    raise ValueError('请先核对不确定结果，再迁移未发送项的接口')
                config = effective(self.store.snapshot())
                self.store.change(lambda d: d['state']['tasks'][task_id].update(
                    route={k: config['message'][k] for k in ('url', 'sender')}, route_changed_at=time.time()))
                logging.getLogger(__name__).info('用户显式迁移任务消息接口：%s', task_id)
            else:
                self.deliveries.report(task_id, key, {'retry': 'pending', 'confirm': 'accepted', 'skip': 'skipped'}[action],
                                       manual=True, error_code='MANUAL_RESOLUTION')
            self.wake.set()

    def queue_test(self, config, uids):
        if not uids or len(uids) > 100 or len(set(uids)) != len(uids):
            raise ValueError('请选择不重复的接收对象')
        allowed = {r['uid'] for r in config['message']['receivers'] if r['enabled']}
        if not set(uids) <= allowed:
            raise ValueError('测试对象必须在已启用的列表中')
        with self.operation:
            if self.tests:
                raise ValueError('已有测试正在等待发送')
            self.test_results = []
            self.tests = [(config, uid) for uid in uids]
        self.wake.set()

    def run_test(self):
        config, uid = self.tests.pop(0)
        self.sending = True
        try:
            result = self.sender.send(config, config['message'], uid, '【测试】权限通知助手连接验证')
            self.test_results.append({'uid': uid, 'tested_at': time.time(), **result})
        finally:
            self.sending = False

    def shutdown(self):
        self.stop.set()
        self.wake.set()

    def prune_confirmed(self):
        data = self.store.snapshot()
        protected = {r['task_id'] for r in data['state']['pending_reports']}
        removable = [key for key, task in data['state']['tasks'].items() if task['closed'] and
                     key not in protected and task.get('updated_at', time.time()) < time.time() - 7 * 86400]
        if removable:
            def prune(value):
                for key in removable:
                    value['state']['tasks'].pop(key, None)
            self.store.change(prune)
