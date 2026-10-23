"""Owner-only console. Never sends messages or stores actual receiver IDs."""
import secrets
from datetime import timedelta
from urllib.parse import urlencode
from fastapi import APIRouter, Request, Form, Query, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select
from .models import AccessApplication, Audit, now
from .notification_models import NotificationTask
from .notification_auth import owner
from .notification_state import read, save
from .notification_views import client_summary, task_list, STATUSES
from .security import digest

router = APIRouter(prefix='/admin/notifications')
BASE = '/cli-permission/admin/notifications'
NOTICES = {
    'enabled': '通知设置已保存。', 'revoked': '助手 Token 已撤销，助手需重新绑定后才能连接。',
    'backfill': '已补建 {count} 条历史待审批通知。', 'empty': '没有需要补建的历史待审批通知。',
    'retry': '已请求重试 {count} 个失败项，等待本地助手领取处理。',
    'retry_pending': '失败项的重试请求已提交，等待本地助手处理。',
    'no_failed': '没有可重试的失败项，无需重复操作。',
}


def form_location(page: int = Form(1, ge=1), q: str = Form('', max_length=128), status: str = Form('')):
    return dict(page=page, q=q.strip(), status=status if status in STATUSES else '')


def wants_json(request):
    return 'application/json' in request.headers.get('accept', '')


def render(request, db, actor, session, client, token='', page=1, q='', status='',
           error='', notice='', affected=0, status_code=200):
    context = task_list(db, page, q, status)
    context.update(admin=actor, csrf=session.csrf, client=client, token=token,
                   summary=client_summary(client), refreshed_at=now(), error=error,
                   notice=NOTICES.get(notice, '').format(count=affected))
    return request.app.state.templates.TemplateResponse(request=request, name='notifications.html',
        context=context, status_code=status_code)


def problem(request, db, actor, session, client, message, filters, status_code=400):
    if wants_json(request):
        return JSONResponse({'detail': message}, status_code=status_code)
    return render(request, db, actor, session, client, error=message, status_code=status_code, **filters)


def redirect(notice, filters, affected=0):
    return RedirectResponse(BASE + '?' + urlencode({**filters, 'notice': notice, 'affected': affected}), status_code=303)


@router.get('')
def page(request: Request, page: int = Query(1, ge=1), q: str = Query('', max_length=128),
         status: str = Query(''), notice: str = Query(''), affected: int = Query(0, ge=0, le=100)):
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db)
        response = render(request, db, actor, session, client, page=page, q=q.strip(),
                          status=status if status in STATUSES else '', notice=notice, affected=affected)
        db.commit()
        return response


@router.post('/token')
def token(request: Request, csrf: str = Form(), confirmation: str = Form(),
          generation: int | None = Form(None, ge=0), filters: dict = Depends(form_location)):
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db, csrf)
        if confirmation != 'reset':
            return problem(request, db, actor, session, client, '请输入 reset 确认生成新的助手凭据。', filters)
        # A browser resubmitting the same form must not silently rotate again.
        if generation is not None and generation != client.credential_generation:
            return problem(request, db, actor, session, client, '凭据状态已变化，请刷新页面后重试。', filters, 409)
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
        db.add(Audit(actor=actor.username, action='notifications.token.reset', detail='已生成新凭据，旧凭据已撤销'))
        if wants_json(request):
            html = render(request, db, actor, session, client, token=raw, **filters)
            response = JSONResponse({'token': raw, 'generation': client.credential_generation,
                                     'html': html.body.decode(), 'url': BASE + '?' + urlencode(filters)})
        else:
            response = render(request, db, actor, session, client, token=raw, **filters)
        db.commit()
        return response


@router.post('/revoke')
def revoke(request: Request, csrf: str = Form(), filters: dict = Depends(form_location)):
    with request.app.state.sessions() as db:
        actor, _, client = owner(request, db, csrf)
        client.token_hash = ''
        client.credential_generation += 1
        client.last_seen_at, client.health_code = None, 'unknown'
        db.add(Audit(actor=actor.username, action='notifications.token.revoke', detail='助手凭据已撤销'))
        db.commit()
    return redirect('revoked', filters)


@router.post('/enabled')
def enabled(request: Request, csrf: str = Form(), enabled: bool = Form(False), filters: dict = Depends(form_location)):
    with request.app.state.sessions() as db:
        actor, _, client = owner(request, db, csrf)
        client.owner_admin_id, client.enabled = actor.id, enabled
        db.add(Audit(actor=actor.username, action='notifications.enabled', detail='开启新通知' if enabled else '关闭新通知'))
        db.commit()
    return redirect('enabled', filters)


@router.post('/backfill')
def backfill(request: Request, csrf: str = Form(), filters: dict = Depends(form_location)):
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db, csrf)
        if not client.enabled:
            return problem(request, db, actor, session, client, '请先开启并保存通知设置，再补建历史通知。', filters)
        known = select(NotificationTask.application_id)
        items = db.scalars(select(AccessApplication).where(AccessApplication.status == 'pending',
                        ~AccessApplication.id.in_(known)).order_by(AccessApplication.id).limit(100)).all()
        for item in items:
            db.add(NotificationTask(application_id=item.id, event_key=f'application_submitted:{item.id}'))
        db.add(Audit(actor=actor.username, action='notifications.backfill', detail=f'补建 {len(items)} 条历史待审批通知'))
        db.commit()
    return redirect('backfill' if items else 'empty', filters, len(items))


@router.post('/{task_id}/retry')
def retry(task_id: str, request: Request, csrf: str = Form(), filters: dict = Depends(form_location)):
    with request.app.state.sessions() as db:
        actor, session, client = owner(request, db, csrf)
        task = db.get(NotificationTask, task_id)
        if not task:
            return problem(request, db, actor, session, client, '通知记录不存在，请刷新列表后重试。', filters, 404)
        data = read(task)
        failures = [key for key, item in data['deliveries'].items() if item['state'] == 'failed']
        if not failures:
            return redirect('no_failed', filters)
        application = db.get(AccessApplication, task.application_id)
        if not application or application.status != 'pending':
            return problem(request, db, actor, session, client, '申请已处理或不存在，不再请求重试。请在本地助手核对未完成项。', filters, 409)
        actions = data.setdefault('actions', {})
        changed = [key for key in failures if actions.get(key) != 'retry']
        for key in changed:
            actions[key] = 'retry'
        if changed:
            save(task, data)
            db.add(Audit(actor=actor.username, action='notifications.retry', detail=f'任务 {task.id} 请求重试 {len(changed)} 个失败项'))
        db.commit()
    return redirect('retry' if changed else 'retry_pending', filters, len(changed))
