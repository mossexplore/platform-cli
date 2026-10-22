"""Persistent per-recipient checkpoints and ordered, idempotent reports."""
import time
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from .store import effective
from .service import ServiceError

TERMINAL = {'accepted', 'failed', 'uncertain', 'skipped'}


def content(task, base):
    date = datetime.fromisoformat(task['created_at'].replace('Z', '+00:00')).astimezone(
        timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
    root = base.rstrip('/')
    if root.endswith('/cli-permission'):
        root = root[:-len('/cli-permission')]
    # Build from numeric application ID, never a server-supplied arbitrary URL.
    link = root + '/cli-permission/admin/applications/' + str(int(task['application_id']))
    return (f"【权限申请待审批】\n\n申请人：{task['applicant_name']}\n账号：{task['applicant_account']}"
            f"\n申请时间：{date}\n申请编号：{task['application_id']}\n\n审批地址：{link}")


class Deliveries:
    def __init__(self, store, service):
        self.store, self.service = store, service

    def call(self, endpoint, body=None):
        data = self.store.snapshot()
        return self.service.call(effective(data), data['state']['installation_id'], endpoint, body)

    def task(self, task_id):
        return self.store.snapshot()['state']['tasks'][task_id]

    def remember(self, task, config):
        receivers = {}
        for receiver in config['message']['receivers']:
            if receiver['enabled']:
                receivers[str(uuid4())] = {**receiver, 'state': 'pending', 'attempt_id': '',
                                          'attempts': 0, 'next_attempt_at': 0, 'error_code': ''}
        value = {'id': task['id'], 'snapshot_id': str(uuid4()), 'remote': task, 'prepared': False,
                 'source': config['permission_service_url'], 'content': content(task, config['permission_service_url']),
                 'route': {k: config['message'][k] for k in ('url', 'sender')}, 'report_seq': 0,
                 'deliveries': receivers, 'closed': False, 'updated_at': time.time()}
        self.store.change(lambda data: data['state']['tasks'].setdefault(task['id'], value))

    def merge(self, task_id, remote, raw_token=None):
        def update(data):
            task = data['state']['tasks'][task_id]
            token = raw_token or remote.get('lease_token') or task['remote'].get('lease_token')
            task['remote'] = {**remote, 'lease_token': token}
            queued = any(r['task_id'] == task_id for r in data['state']['pending_reports'])
            if not queued:
                for key, state in remote['deliveries'].items():
                    if key not in task['deliveries']:
                        raise ValueError('REMOTE_SNAPSHOT_MISMATCH')
                    local = task['deliveries'][key]
                    local.update({k: v for k, v in state.items() if k != 'actions'})
                task['report_seq'] = remote['report_seq']
                task['closed'] = bool(task['prepared'] and task['deliveries'] and all(
                    x['state'] in {'accepted', 'skipped'} for x in task['deliveries'].values()))
            task['updated_at'] = time.time()
        self.store.change(update)

    def lease(self, task_id):
        remote = self.task(task_id)['remote']
        return {k: remote[k] for k in ('lease_token', 'lease_generation')}

    def restore(self, task_id):
        task = self.task(task_id)
        remote = self.call(f'{task_id}/resume', {'snapshot_id': task['snapshot_id']})
        # Set lease without overwriting locally persisted but unreported outcomes.
        self.merge(task_id, remote)
        self.flush(task_id)
        task = self.task(task_id)
        if not task['prepared']:
            self.prepare(task_id)

    def prepare(self, task_id):
        task = self.task(task_id)
        remote = self.call(f'{task_id}/prepare', {**self.lease(task_id),
            'snapshot_id': task['snapshot_id'], 'delivery_ids': list(task['deliveries'])})
        self.store.change(lambda d: d['state']['tasks'][task_id].update(prepared=True))
        self.merge(task_id, remote)

    def renew(self, task_id):
        try:
            remote = self.call(f'{task_id}/renew', self.lease(task_id))
            self.merge(task_id, remote)
        except ServiceError as exc:
            if exc.code != 'LEASE_CONFLICT':
                raise
            self.restore(task_id)

    def report(self, task_id, delivery_id, state, error_code='', manual=False, message_id=None):
        def append(data):
            task = data['state']['tasks'][task_id]
            item = task['deliveries'][delivery_id]
            if state == 'sending':
                item['attempt_id'] = str(uuid4())
                item['attempts'] += 1
            if manual and state == 'pending':
                item['attempts'] = 0
            item.update(state=state, error_code=error_code)
            if state == 'retry_wait':
                delay = [30, 60, 120, 300, 600][min(max(item['attempts'] - 1, 0), 4)]
                item['next_attempt_at'] = time.time() + delay
            if state == 'accepted':
                data['state']['last_success_at'] = time.time()
            task['report_seq'] += 1
            task['closed'] = False
            data['state']['pending_reports'].append({'task_id': task_id, 'source': task['source'],
                'body': {'report_id': str(uuid4()), 'report_seq': task['report_seq'], 'updates': [{
                    'delivery_id': delivery_id, 'attempt_id': item['attempt_id'], 'state': state,
                    'error_code': error_code, 'message_id': message_id, 'manual': manual}]}})
        self.store.change(append)
        self.flush()

    def flush(self, only_task=None):
        while True:
            data = self.store.snapshot()
            queue = [r for r in data['state']['pending_reports']
                     if only_task is None or r['task_id'] == only_task]
            if not queue:
                return
            report = queue[0]
            if report['source'] != effective(data)['permission_service_url']:
                raise ServiceError('REPORT_SOURCE_MISMATCH')
            task_id = report['task_id']
            remote = self.call(f'{task_id}/result', {**report['body'], **self.lease(task_id)})
            def remove(data):
                data['state']['pending_reports'] = [r for r in data['state']['pending_reports']
                    if r['body']['report_id'] != report['body']['report_id']]
            self.store.change(remove)
            self.merge(task_id, remote)
