"""Public applications, private receipt links, and administrator review pages."""
import json
import secrets
from datetime import timedelta
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from .admin_auth import admin_session, authorize_form
from .application_review import approve, fingerprint, identity, reject, review_state
from .models import AccessApplication, ApplicationAttempt, now
from .pagination import PAGE_SIZE
from .security import digest

router = APIRouter()
STATUSES = {'pending': '待审批', 'approved': '已通过', 'rejected': '已拒绝'}


def render(request, template, **context):
    return request.app.state.templates.TemplateResponse(request=request, name=template,
        context={'statuses': STATUSES, **context})


def admin_context(request, db):
    actor, session = admin_session(request, db)
    return {'admin': actor, 'csrf': session.csrf, 'tab': 'applications', 'page_title': '权限申请'}


@router.get('/apply')
def apply_page(request: Request):
    csrf = secrets.token_hex(32)
    response = render(request, 'apply.html', csrf=csrf)
    response.set_cookie('apply_csrf', csrf, secure=request.app.state.settings.secure_cookie,
                        httponly=True, samesite='strict', path='/cli-permission/apply', max_age=3600)
    return response


@router.post('/apply')
def submit(request: Request, csrf: str = Form(max_length=64),
           username: str = Form(min_length=1, max_length=128),
           display_name: str = Form(min_length=1, max_length=128)):
    if not csrf or not secrets.compare_digest(csrf, request.cookies.get('apply_csrf', '')):
        raise HTTPException(403, '申请页面已失效，请刷新页面重试')
    username, display_name = identity(username, display_name)
    source = digest(request.client.host if request.client else 'unknown')
    with request.app.state.sessions() as db:
        cutoff = now() - timedelta(minutes=15)
        db.execute(delete(ApplicationAttempt).where(ApplicationAttempt.created_at < cutoff))
        count = db.scalar(select(func.count()).select_from(ApplicationAttempt).where(ApplicationAttempt.source == source))
        if count >= 10:
            raise HTTPException(429, '提交过于频繁，请 15 分钟后重试')
        db.add(ApplicationAttempt(source=source))
        db.commit()
        token = secrets.token_urlsafe(32)
        item = AccessApplication(username=username, display_name=display_name,
                                 pending_username=username, token_hash=digest(token))
        db.add(item)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            if db.scalar(select(AccessApplication.id).where(AccessApplication.pending_username == username)) is None:
                raise
            return render(request, 'apply.html', duplicate=True)
    return RedirectResponse('/cli-permission/apply/status/' + token, status_code=303)


@router.get('/apply/status/{token}')
def receipt(request: Request, token: str):
    if len(token) != 43:
        raise HTTPException(404, '查询链接无效')
    with request.app.state.sessions() as db:
        item = db.scalar(select(AccessApplication).where(AccessApplication.token_hash == digest(token)))
        if not item:
            raise HTTPException(404, '查询链接无效')
        return render(request, 'apply.html', item=item, result=json.loads(item.result))


@router.get('/admin/applications')
def application_list(request: Request, status: str = 'pending', q: str = Query('', max_length=128),
                     page: int = Query(1, ge=1)):
    if status not in ('', *STATUSES):
        raise HTTPException(400, '无效申请状态')
    with request.app.state.sessions() as db:
        try:
            context = admin_context(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        query = select(AccessApplication)
        if status:
            query = query.where(AccessApplication.status == status)
        if q:
            query = query.where(or_(*[field.contains(q, autoescape=True) for field in (
                AccessApplication.username, AccessApplication.display_name,
                AccessApplication.approved_username, AccessApplication.approved_name)]))
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        items = db.scalars(query.order_by(AccessApplication.created_at.desc(), AccessApplication.id.desc())
                           .offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE)).all()
        return render(request, 'applications.html', **context, items=items, count=count,
                      page=page, q=q, status=status,
                      previous=str(request.url.include_query_params(page=page-1)),
                      next=str(request.url.include_query_params(page=page+1)))


def get_application(db, application_id):
    item = db.get(AccessApplication, application_id)
    if item is None:
        raise HTTPException(404, '申请不存在')
    return item


@router.get('/admin/applications/{application_id}')
def detail(request: Request, application_id: int):
    with request.app.state.sessions() as db:
        context = admin_context(request, db)
        item = get_application(db, application_id)
        return render(request, 'application_detail.html', **context, item=item,
                      result=json.loads(item.result))


@router.post('/admin/applications/{application_id}/preview')
def preview(request: Request, application_id: int, csrf: str = Form(max_length=64),
            username: str = Form(min_length=1, max_length=128),
            display_name: str = Form(min_length=1, max_length=128)):
    username, display_name = identity(username, display_name)
    with request.app.state.sessions() as db:
        authorize_form(request, db, csrf)
        context = admin_context(request, db)
        item = get_application(db, application_id)
        if item.status != 'pending':
            raise HTTPException(409, '申请已审批，请刷新列表')
        state, _, _ = review_state(db, username, application_id)
        return render(request, 'application_preview.html', **context, item=item, state=state,
                      snapshot=fingerprint(state), username=username, display_name=display_name)


@router.post('/admin/applications/{application_id}/approve')
def accept(request: Request, application_id: int, csrf: str = Form(max_length=64),
           username: str = Form(min_length=1, max_length=128), display_name: str = Form(min_length=1, max_length=128),
           environments: list[str] = Form(default=[]), expires_at: str = Form('', max_length=32),
           snapshot: str = Form(max_length=64), confirm_existing: bool = Form(False),
           update_name: bool = Form(False), restore_grants: bool = Form(False)):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        approve(db, actor, application_id, username, display_name, environments, expires_at,
                snapshot, confirm_existing, update_name, restore_grants)
    return RedirectResponse(f'/cli-permission/admin/applications/{application_id}', status_code=303)


@router.post('/admin/applications/{application_id}/reject')
def decline(request: Request, application_id: int, csrf: str = Form(max_length=64),
            reason: str = Form(min_length=1, max_length=1000)):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        reject(db, actor, application_id, reason)
    return RedirectResponse(f'/cli-permission/admin/applications/{application_id}', status_code=303)
