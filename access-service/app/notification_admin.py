"""Owner-only controls. Never sends messages or stores actual receiver IDs."""
import json
import secrets
from datetime import timedelta
from fastapi import APIRouter, Request, Form, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from .models import AccessApplication, Audit, now
from .notification_models import NotificationTask
from .notification_auth import owner, fail
from .notification_state import counts, read, save, get_task
from .security import digest

router = APIRouter(prefix='/admin/notifications')


def render(request, db, actor, session, client, token='', page=1):
    tasks = db.scalars(select(NotificationTask).order_by(NotificationTask.created_at.desc())
                       .offset((page - 1) * 30).limit(30)).all()
    total = db.scalar(select(func.count()).select_from(NotificationTask))
    return request.app.state.templates.TemplateResponse(request=request,
        name='notifications.html', context={'admin': actor, 'csrf': session.csrf,
            'client': client, 'token': token, 'tasks': tasks, 'counts': counts,
            'online': bool(client.last_seen_at and client.last_seen_at > now() - timedelta(seconds=180)),
            'page': page, 'has_next': total > page * 30})


@router.get('')
def page(request: Request, page: int = Query(1, ge=1)):
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db)
        response = render(request, db, actor, session, client, page=page)
        db.commit()
        return response


@router.post('/token')
def token(request: Request, csrf: str = Form(), confirmation: str = Form()):
    if confirmation != 'reset':
        fail('CONFIRMATION_REQUIRED', 400)
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db, csrf)
        raw = secrets.token_urlsafe(32)
        client.owner_admin_id = actor.id
        client.token_hash = digest(raw)
        client.credential_generation += 1
        client.installation_id = ''
        client.expires_at = None
        client.bind_deadline = now() + timedelta(minutes=30)
        client.last_seen_at, client.health_code = None, 'unknown'
        for task in db.scalars(select(NotificationTask).where(NotificationTask.lease_expires_at > now())):
            task.lease_expires_at = now()
        db.add(Audit(actor=actor.username, action='notifications.token.reset', detail='旧凭据已撤销'))
        response = render(request, db, actor, session, client, token=raw)
        db.commit()
        return response


@router.post('/revoke')
def revoke(request: Request, csrf: str = Form()):
    with request.app.state.sessions() as db:
        actor, _, client = owner(request, db, csrf)
        client.token_hash = ''
        client.credential_generation += 1
        db.add(Audit(actor=actor.username, action='notifications.token.revoke', detail='助手凭据已撤销'))
        db.commit()
    return RedirectResponse('/cli-permission/admin/notifications', status_code=303)


@router.post('/enabled')
def enabled(request: Request, csrf: str = Form(), enabled: bool = Form(False)):
    with request.app.state.sessions() as db:
        actor, _, client = owner(request, db, csrf)
        client.owner_admin_id, client.enabled = actor.id, enabled
        db.add(Audit(actor=actor.username, action='notifications.enabled', detail=json.dumps(enabled)))
        db.commit()
    return RedirectResponse('/cli-permission/admin/notifications', status_code=303)


@router.post('/backfill')
def backfill(request: Request, csrf: str = Form()):
    with request.app.state.sessions() as db:
        actor, _, client = owner(request, db, csrf)
        if not client.enabled:
            fail('ENABLE_NOTIFICATIONS_FIRST', 400)
        # Bounded operation; repeated calls advance without duplicating events.
        known = select(NotificationTask.application_id)
        items = db.scalars(select(AccessApplication).where(AccessApplication.status == 'pending',
                        ~AccessApplication.id.in_(known)).order_by(AccessApplication.id).limit(100)).all()
        for item in items:
            db.add(NotificationTask(application_id=item.id, event_key=f'application_submitted:{item.id}'))
        db.add(Audit(actor=actor.username, action='notifications.backfill', detail=f'补建 {len(items)} 条'))
        db.commit()
    return RedirectResponse('/cli-permission/admin/notifications', status_code=303)


@router.post('/{task_id}/retry')
def retry(task_id: str, request: Request, csrf: str = Form()):
    with request.app.state.sessions() as db:
        actor, _, _ = owner(request, db, csrf)
        task = get_task(db, task_id)
        data = read(task)
        for key, item in data['deliveries'].items():
            if item['state'] == 'failed':
                data['actions'][key] = 'retry'
        save(task, data)
        db.add(Audit(actor=actor.username, action='notifications.retry', detail=f'任务 {task.id} 请求重试明确失败项'))
        db.commit()
    return RedirectResponse('/cli-permission/admin/notifications', status_code=303)
