"""Lease fencing and delivery state transitions (no external network calls)."""
import json
import secrets
from datetime import timedelta
from collections import Counter
from .models import AccessApplication, now
from .notification_models import NotificationTask
from .notification_auth import fail
from .security import digest

TERMINAL = {'sent', 'skipped', 'partial', 'failed', 'uncertain'}


def read(task):
    return json.loads(task.data)


def save(task, data):
    task.data = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    task.updated_at = now()
    states = [item['state'] for item in data['deliveries'].values()]
    if not states:
        return
    if 'sending' in states or 'pending' in states:
        task.status = 'processing'
    elif 'retry_wait' in states:
        task.status = 'retry_wait'
    elif all(s == 'accepted' for s in states):
        task.status = 'sent'
    elif all(s == 'skipped' for s in states):
        task.status = 'skipped'
    elif 'accepted' in states:
        task.status = 'partial'
    elif 'uncertain' in states:
        task.status = 'uncertain'
    else:
        task.status = 'failed'


def get_task(db, task_id):
    task = db.get(NotificationTask, task_id)
    if not task:
        fail('TASK_NOT_FOUND', 404)
    return task


def pending(db, task):
    app = db.get(AccessApplication, task.application_id)
    return app is not None and app.status == 'pending'


def check_lease(task, body):
    if (task.installation_id != body.installation_id or
            task.lease_generation != body.lease_generation or
            not secrets.compare_digest(task.lease_token_hash, digest(body.lease_token)) or
            not task.lease_expires_at or task.lease_expires_at <= now()):
        fail('LEASE_CONFLICT')


def issue(task, installation):
    raw = secrets.token_urlsafe(32)
    task.installation_id = installation
    task.lease_generation += 1
    task.lease_token_hash = digest(raw)
    task.lease_expires_at = now() + timedelta(seconds=120)
    task.updated_at = now()
    return raw


def view(db, task, lease_token=None):
    app = db.get(AccessApplication, task.application_id)
    data = read(task)
    return {'id': task.id, 'event': 'application_submitted', 'application_id': task.application_id,
            'applicant_name': app.display_name if app else '',
            'applicant_account': app.username if app else '',
            'created_at': task.created_at.isoformat() + 'Z',
            'review_path': f'/cli-permission/admin/applications/{task.application_id}',
            'application_pending': bool(app and app.status == 'pending'),
            'status': task.status, 'snapshot_id': task.snapshot_id,
            'deliveries': data['deliveries'], 'actions': data.get('actions', {}),
            'report_seq': task.report_seq, 'lease_generation': task.lease_generation,
            'lease_token': lease_token,
            'lease_expires_at': task.lease_expires_at.isoformat() + 'Z' if task.lease_expires_at else None}


def apply_report(task, body, application_pending):
    data = read(task)
    payload = {'report_id': body.report_id, 'updates': [u.model_dump() for u in body.updates]}
    fingerprint = digest(json.dumps(payload, sort_keys=True, separators=(',', ':')))
    existing = data['reports'].get(str(body.report_seq))
    if existing:
        if existing != {'id': body.report_id, 'hash': fingerprint}:
            fail('REPORT_CONFLICT')
        return
    if any(value['id'] == body.report_id for value in data['reports'].values()):
        fail('REPORT_CONFLICT')
    check_lease(task, body)
    if body.report_seq != task.report_seq + 1:
        fail('REPORT_CONFLICT')
    for update in body.updates:
        item = data['deliveries'].get(update.delivery_id)
        if item is None:
            fail('UNKNOWN_DELIVERY')
        old, new = item['state'], update.state
        if update.manual:
            allowed = (old in {'failed', 'uncertain', 'retry_wait', 'pending'} and
                       new in {'pending', 'accepted', 'skipped'})
        elif new == 'sending':
            allowed = (old in {'pending', 'retry_wait'} and application_pending and
                       bool(update.attempt_id) and update.attempt_id != item.get('attempt_id') and
                       item.get('attempts', 0) < 8)
        elif new == 'skipped':
            allowed = old in {'pending', 'retry_wait'} and not application_pending
        else:
            # Resume conservatively changes sending -> uncertain. A persisted
            # definitive response for that same attempt may still settle it.
            allowed = (old in {'sending', 'uncertain'} and
                       update.attempt_id == item.get('attempt_id') and bool(update.attempt_id) and
                       new in {'accepted', 'retry_wait', 'failed', 'uncertain'})
        if not allowed:
            fail('INVALID_TRANSITION')
        if new == 'sending':
            item['attempts'] = item.get('attempts', 0) + 1
        if update.manual and new == 'pending':
            item['attempts'] = 0
        item.update(state=new, attempt_id=update.attempt_id, error_code=update.error_code,
                    message_id=update.message_id)
        data.get('actions', {}).pop(update.delivery_id, None)
    task.report_seq = body.report_seq
    data['reports'][str(body.report_seq)] = {'id': body.report_id, 'hash': fingerprint}
    save(task, data)


def counts(task):
    return dict(Counter(i['state'] for i in read(task)['deliveries'].values()))
