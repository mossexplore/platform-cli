"""Scoped machine protocol. All mutations serialize on the singleton client."""
from datetime import timedelta
from fastapi import APIRouter, Request
from sqlalchemy import select, or_
from .models import Audit, now
from .notification_models import NotificationTask
from .notification_auth import machine, fail
from .notification_schema import Identity, Lease, Prepare, Resume, Report, Heartbeat
from . import notification_state as state

router = APIRouter(prefix='/api/v1/notifications')


@router.post('/check')
def check(request: Request, body: Identity):
    with request.app.state.sessions() as db:
        client = machine(request, db, body)
        result = {'enabled': client.enabled, 'expires_at': client.expires_at.isoformat() + 'Z'}
        db.commit()
        return result


@router.post('/bind')
def bind(request: Request, body: Identity):
    with request.app.state.sessions() as db:
        client = machine(request, db, body, binding=True)
        if not client.installation_id:
            client.installation_id = body.installation_id
            client.expires_at = now() + timedelta(days=90)
            db.add(Audit(actor=f'notification:{client.owner_admin_id}', action='notifications.bind',
                         detail='助手实例已绑定'))
        client.last_seen_at = now()
        expires = client.expires_at.isoformat() + 'Z'
        db.commit()
        return {'bound': True, 'expires_at': expires, 'protocol_version': 1}


@router.post('/heartbeat')
def heartbeat(request: Request, body: Heartbeat):
    with request.app.state.sessions() as db:
        client = machine(request, db, body)
        client.last_seen_at = now()
        client.agent_version, client.health_code = body.agent_version, body.health_code
        result = {'enabled': client.enabled, 'expires_at': client.expires_at.isoformat() + 'Z'}
        db.commit()
        return result


@router.post('/claim')
def claim(request: Request, body: Identity):
    with request.app.state.sessions() as db:
        client = machine(request, db, body)
        if not client.enabled:
            db.commit()
            return {'task': None, 'enabled': False}
        # Find an unprepared claim whose response may have been lost, or new work.
        candidates = db.scalars(select(NotificationTask).where(or_(
            NotificationTask.status == 'pending',
            (NotificationTask.installation_id == body.installation_id) &
            (NotificationTask.snapshot_id == '') & (NotificationTask.status == 'processing')
        )).order_by(NotificationTask.created_at, NotificationTask.id).limit(100)).all()
        for task in candidates:
            if not state.pending(db, task):
                task.status, task.updated_at = 'skipped', now()
                continue
            raw = state.issue(task, body.installation_id)
            task.status = 'processing'
            result = state.view(db, task, raw)
            db.commit()
            return {'task': result}
        db.commit()
        return {'task': None}


@router.post('/{task_id}/prepare')
def prepare(task_id: str, request: Request, body: Prepare):
    with request.app.state.sessions() as db:
        machine(request, db, body)
        task = state.get_task(db, task_id)
        state.check_lease(task, body)
        if len(set(body.delivery_ids)) != len(body.delivery_ids) or any(
                not 8 <= len(x) <= 64 or not x.replace('-', '').replace('_', '').isalnum()
                for x in body.delivery_ids):
            fail('INVALID_DELIVERIES', 400)
        data = state.read(task)
        if task.snapshot_id:
            if task.snapshot_id != body.snapshot_id or set(data['deliveries']) != set(body.delivery_ids):
                fail('SNAPSHOT_CONFLICT')
        else:
            task.snapshot_id = body.snapshot_id
            data['deliveries'] = {i: {'state': 'pending', 'attempts': 0, 'attempt_id': ''}
                                  for i in body.delivery_ids}
            state.save(task, data)
        result = state.view(db, task)
        db.commit()
        return result


@router.post('/{task_id}/renew')
def renew(task_id: str, request: Request, body: Lease):
    with request.app.state.sessions() as db:
        machine(request, db, body)
        task = state.get_task(db, task_id)
        state.check_lease(task, body)
        task.lease_expires_at = now() + timedelta(seconds=120)
        result = state.view(db, task)
        db.commit()
        return result


@router.post('/{task_id}/resume')
def resume(task_id: str, request: Request, body: Resume):
    with request.app.state.sessions() as db:
        machine(request, db, body)
        task = state.get_task(db, task_id)
        if task.installation_id != body.installation_id:
            fail('INSTANCE_MISMATCH')
        if task.snapshot_id and task.snapshot_id != body.snapshot_id:
            fail('SNAPSHOT_CONFLICT')
        data = state.read(task)
        for item in data['deliveries'].values():
            if item['state'] == 'sending':
                item.update(state='uncertain', error_code='INTERRUPTED')
        state.save(task, data)
        raw = state.issue(task, body.installation_id)
        result = state.view(db, task, raw)
        db.commit()
        return result


@router.post('/{task_id}/result')
def result(task_id: str, request: Request, body: Report):
    with request.app.state.sessions() as db:
        client = machine(request, db, body)
        task = state.get_task(db, task_id)
        if task.installation_id != body.installation_id:
            fail('INSTANCE_MISMATCH')
        state.apply_report(task, body, state.pending(db, task))
        if any(update.manual for update in body.updates):
            db.add(Audit(actor=f'notification:{client.owner_admin_id}',
                         action='notifications.resolve', detail=f'任务 {task.id} 人工处理'))
        response = state.view(db, task)
        db.commit()
        return response
