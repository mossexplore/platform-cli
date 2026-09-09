"""超级管理员管理管理员账号；普通管理员不能进入或修改。"""
from .pagination import PAGE_SIZE
import json
import secrets
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import select, func, delete
from .admin_auth import admin_session, authorize_form
from .models import Admin, Audit, Session, now
from .security import password_hash

router = APIRouter()


def require_super(admin):
    if admin.role != 'super_admin':
        raise HTTPException(403, '仅超级管理员可以管理管理员账号')


def audit_state(item):
    # 不记录密码或哈希，不能复用通用模型快照。
    return {'username': item.username, 'role': item.role, 'enabled': item.enabled}


def save_audit(db, actor, action, before, item):
    item.updated_at = now()
    db.add(Audit(actor=actor.username, action='administrators.' + action,
        detail=json.dumps({'before': before, 'after': audit_state(item)}, ensure_ascii=False)))
    db.commit()
    return RedirectResponse('/cli-permission/admin/administrators?saved=1', status_code=303)


@router.get('/admin/administrators')
def page(request: Request, q: str = Query('', max_length=128), status: str = '',
         page: int = Query(1, ge=1), saved: bool = False):
    if status not in ('', 'enabled', 'disabled'):
        raise HTTPException(400, '无效状态筛选')
    with request.app.state.sessions() as db:
        try:
            actor, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/cli-permission/login', status_code=303)
            raise
        require_super(actor)
        query = select(Admin)
        if q:
            query = query.where(Admin.username.contains(q, autoescape=True))
        if status:
            query = query.where(Admin.enabled.is_(status == 'enabled'))
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        items = db.scalars(query.order_by(func.coalesce(Admin.updated_at, Admin.created_at).desc(), Admin.id.desc()).offset((page-1)*PAGE_SIZE).limit(PAGE_SIZE)).all()
        return request.app.state.templates.TemplateResponse(request=request, name='administrators.html', context={
            'admin': actor, 'csrf': session.csrf, 'items': items, 'count': count,
            'page': page, 'q': q, 'status': status, 'saved': saved,
            'previous': str(request.url.include_query_params(page=page-1)),
            'next': str(request.url.include_query_params(page=page+1))})


@router.post('/admin/administrators')
def create(request: Request, csrf: str = Form(max_length=64),
           username: str = Form(min_length=1, max_length=128),
           enabled: bool = Form(False)):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        require_super(actor)
        username = username.strip()
        if not username:
            raise HTTPException(400, '管理员账号不可为空')
        password = secrets.token_urlsafe(24)
        # 不接受客户端提供的 role，新建账号只能是管理员。
        item = Admin(username=username, password_hash=password_hash(password), role='admin', enabled=enabled)
        db.add(item)
        db.flush()
        save_audit(db, actor, 'create', None, item)
        return JSONResponse({'username': item.username, 'password': password}, status_code=201)


@router.post('/admin/administrators/{item_id}/status')
def change_status(request: Request, item_id: int, csrf: str = Form(max_length=64),
                  enabled: bool = Form(...)):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        require_super(actor)
        item = db.get(Admin, item_id)
        if item is None:
            raise HTTPException(404, '管理员不存在')
        if item.id == actor.id or item.role != 'admin':
            raise HTTPException(400, '只能启用或停用普通管理员，不能修改自己或超级管理员')
        before = audit_state(item)
        item.enabled = enabled
        if not enabled:
            db.execute(delete(Session).where(Session.admin_id == item.id))
        return save_audit(db, actor, 'enable' if enabled else 'disable', before, item)


@router.post('/admin/administrators/{item_id}/reset-password')
def reset_password(request: Request, item_id: int, csrf: str = Form(max_length=64)):
    with request.app.state.sessions() as db:
        actor = authorize_form(request, db, csrf)
        require_super(actor)
        item = db.get(Admin, item_id)
        if item is None:
            raise HTTPException(404, '管理员不存在')
        if item.id == actor.id or item.role != 'admin':
            raise HTTPException(400, '只能重置普通管理员的密码')
        before = audit_state(item)
        password = secrets.token_urlsafe(24)
        item.password_hash = password_hash(password)
        db.execute(delete(Session).where(Session.admin_id == item.id))
        save_audit(db, actor, 'reset_password', before, item)
        return JSONResponse({'username': item.username, 'password': password}, status_code=201)
