"""账号、环境和授权的管理页面。"""
import json
from fastapi import APIRouter, Form, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func, or_
from .admin_auth import admin_session, authorize_form
from .models import Audit, Environment, Grant, User
from .security import expiry, origin
from .admin_views import overview, filter_status, grant_state, audit_detail

router = APIRouter()


def snapshot(item):
    return {column.name: str(getattr(item, column.name)) for column in item.__table__.columns}


def record(db, admin, action, before, item):
    db.flush()
    db.add(Audit(actor=admin.username, action=action,
                 detail=json.dumps({'before': before, 'after': snapshot(item)}, ensure_ascii=False)))
    db.commit()
    return RedirectResponse('/admin?tab=' + action.split('.')[0] + '&saved=1', status_code=303)


def existing(db, model, item_id):
    item = db.get(model, item_id)
    if item is None:
        raise HTTPException(404, '记录不存在')
    return item


@router.get('/admin')
def dashboard(request: Request, tab: str = 'users', page: int = Query(1, ge=1),
              q: str = Query('', max_length=128), saved: bool = False, status: str = ''):
    if tab not in ('users', 'environments', 'grants', 'audit'):
        raise HTTPException(400, '无效页面')
    allowed_statuses = ('', 'active', 'expired', 'expiring', 'disabled') if tab == 'grants' else ('', 'enabled', 'disabled')
    if status not in allowed_statuses or (tab == 'audit' and status):
        raise HTTPException(400, '无效状态筛选')
    with request.app.state.sessions() as db:
        try:
            admin, session = admin_session(request, db)
        except HTTPException as exc:
            if exc.status_code == 401:
                return RedirectResponse('/login', status_code=303)
            raise
        model = {'users': User, 'environments': Environment, 'grants': Grant, 'audit': Audit}[tab]
        query = select(model)
        if tab == 'grants':
            query = query.join(User).join(Environment)
        query = filter_status(query, tab, status)
        if q:
            if tab == 'users':
                query = query.where(or_(User.username.contains(q, autoescape=True), User.display_name.contains(q, autoescape=True)))
            elif tab == 'environments':
                query = query.where(or_(Environment.name.contains(q, autoescape=True), Environment.display_name.contains(q, autoescape=True)))
            elif tab == 'grants':
                query = query.where(or_(User.username.contains(q, autoescape=True), Environment.name.contains(q, autoescape=True)))
            else:
                query = query.where(Audit.actor.contains(q, autoescape=True))
        count = db.scalar(select(func.count()).select_from(query.subquery()))
        items = db.scalars(query.order_by(model.id.desc()).offset((page - 1) * 20).limit(20)).all()
        # 授权表单按账号和环境名称输入，不一次加载全部账号。
        users = {item.user_id: existing(db, User, item.user_id).username for item in items} if tab == 'grants' else {}
        environments = {item.environment_id: existing(db, Environment, item.environment_id).name for item in items} if tab == 'grants' else {}
        available_environments = db.scalars(select(Environment).where(Environment.enabled.is_(True)).order_by(Environment.name)).all() if tab == 'grants' else []
        grant_states = {item.id: grant_state(item, db.get(User, item.user_id), db.get(Environment, item.environment_id)) for item in items} if tab == 'grants' else {}
        user_grants = dict(db.execute(select(Grant.user_id, func.count()).where(Grant.user_id.in_([item.id for item in items])).group_by(Grant.user_id)).all()) if tab == 'users' else {}
        return request.app.state.templates.TemplateResponse(request=request, name='dashboard.html', context={
            'admin': admin, 'csrf': session.csrf, 'tab': tab, 'items': items, 'page': page,
            'count': count, 'q': q, 'saved': saved, 'users': users, 'environments': environments,
            'available_environments': available_environments, 'status': status, 'stats': overview(db),
            'grant_states': grant_states, 'user_grants': user_grants,
            'audit_details': {item.id: audit_detail(item) for item in items} if tab == 'audit' else {}})


@router.post('/admin/users')
def save_user(request: Request, csrf: str = Form(max_length=64), item_id: int = Form(0, ge=0),
              username: str = Form(min_length=1, max_length=128),
              display_name: str = Form('', max_length=128), enabled: bool = Form(False)):
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        item = existing(db, User, item_id) if item_id else User(username=username.strip())
        before = snapshot(item) if item_id else None
        if not item.username or (item_id and item.username != username):
            raise HTTPException(400, '账号不可为空，已建账号不可重命名')
        item.display_name, item.enabled = display_name, enabled
        db.add(item)
        return record(db, admin, 'users.save', before, item)


@router.post('/admin/environments')
def save_environment(request: Request, csrf: str = Form(max_length=64), item_id: int = Form(0, ge=0),
                     name: str = Form(min_length=1, max_length=64),
                     display_name: str = Form(min_length=1, max_length=128),
                     platform_origin: str = Form(max_length=512), enabled: bool = Form(False)):
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        item = existing(db, Environment, item_id) if item_id else Environment(name=name.strip())
        before = snapshot(item) if item_id else None
        if not item.name or (item_id and item.name != name):
            raise HTTPException(400, '环境标识不可为空，已建环境不可重命名')
        item.display_name, item.platform_origin, item.enabled = display_name, origin(platform_origin), enabled
        db.add(item)
        return record(db, admin, 'environments.save', before, item)


@router.post('/admin/grants')
def save_grant(request: Request, csrf: str = Form(max_length=64), item_id: int = Form(0, ge=0),
               username: str = Form(min_length=1, max_length=128),
               environment: str = Form(min_length=1, max_length=64),
               expires_at: str = Form('', max_length=32), note: str = Form('', max_length=1000),
               enabled: bool = Form(False)):
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        user = db.scalar(select(User).where(User.username == username))
        env = db.scalar(select(Environment).where(Environment.name == environment))
        if not user or not env:
            raise HTTPException(400, '请先创建对应账号和环境')
        item = existing(db, Grant, item_id) if item_id else Grant(user_id=user.id, environment_id=env.id)
        before = snapshot(item) if item_id else None
        if item.user_id != user.id or item.environment_id != env.id:
            raise HTTPException(400, '已有授权的账号和环境不可更改，请新增授权')
        item.enabled, item.expires_at, item.note = enabled, expiry(expires_at), note
        db.add(item)
        return record(db, admin, 'grants.save', before, item)


@router.post('/admin/grants/batch')
def save_grants(request: Request, csrf: str = Form(max_length=64),
                username: str = Form(min_length=1, max_length=128),
                environments: list[str] = Form(min_length=1, max_length=100),
                expires_at: str = Form('', max_length=32), note: str = Form('', max_length=1000),
                enabled: bool = Form(False)):
    """所选环境按同一配置新增或更新；未选择的已有授权不变，整批原子提交。"""
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        user = db.scalar(select(User).where(User.username == username.strip()))
        if not user:
            raise HTTPException(400, '请先创建对应账号')
        names = set(environments)
        if any(not name or len(name) > 64 for name in names):
            raise HTTPException(400, '环境标识无效')
        selected = db.scalars(select(Environment).where(Environment.name.in_(names))).all()
        if {item.name for item in selected} != names or any(not item.enabled for item in selected):
            raise HTTPException(400, '所选环境不存在或已停用，请刷新页面后重试')
        expires = expiry(expires_at)
        for env in selected:
            item = db.scalar(select(Grant).where(Grant.user_id == user.id, Grant.environment_id == env.id))
            before = snapshot(item) if item else None
            if item is None:
                item = Grant(user_id=user.id, environment_id=env.id)
                db.add(item)
            item.enabled, item.expires_at, item.note = enabled, expires, note
            db.flush()
            db.add(Audit(actor=admin.username, action='grants.batch_save',
                         detail=json.dumps({'before': before, 'after': snapshot(item)}, ensure_ascii=False)))
        db.commit()
        return RedirectResponse('/admin?tab=grants&saved=1', status_code=303)
