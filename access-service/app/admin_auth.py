"""管理会话、CSRF 和登录频率限制；凭据不写入审计。"""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import delete, select, func
from .models import Admin, Audit, Session, LoginAttempt, now
from .security import digest, password_matches, password_hash

router = APIRouter()
DUMMY_HASH = password_hash(secrets.token_urlsafe(24))


def admin_session(request, db):
    session = db.get(Session, digest(request.cookies.get('access_session', '')))
    admin = db.get(Admin, session.admin_id) if session else None
    if not session or session.expires_at <= now() or not admin or not admin.enabled:
        raise HTTPException(401, '请先登录管理页面')
    return admin, session


def authorize_form(request, db, csrf):
    admin, session = admin_session(request, db)
    if not secrets.compare_digest(csrf, session.csrf):
        raise HTTPException(403, '表单已失效，请刷新页面重试')
    return admin


@router.get('/login')
def login_page(request: Request):
    token = secrets.token_hex(32)
    response = request.app.state.templates.TemplateResponse(
        request=request, name='login.html', context={'csrf': token})
    response.set_cookie('login_csrf', token, secure=request.app.state.settings.secure_cookie,
                        httponly=True, samesite='strict', max_age=600)
    return response


@router.post('/login')
def login(request: Request, username: str = Form(max_length=128),
          password: str = Form(max_length=256), csrf: str = Form(max_length=64)):
    if not csrf or not secrets.compare_digest(csrf, request.cookies.get('login_csrf', '')):
        raise HTTPException(403, '登录页面已失效，请刷新页面')
    source = digest(request.client.host if request.client else 'unknown')
    with request.app.state.sessions() as db:
        cutoff = now() - timedelta(minutes=15)
        db.execute(delete(LoginAttempt).where(LoginAttempt.created_at < cutoff))
        attempts = db.scalar(select(func.count()).select_from(LoginAttempt).where(LoginAttempt.source == source))
        if attempts >= 10:
            raise HTTPException(429, '尝试次数过多，请 15 分钟后重试')
        # 先记录尝试，避免密码验证耗时期间重复请求绕过限制。
        db.add(LoginAttempt(source=source))
        db.commit()
        admin = db.scalar(select(Admin).where(Admin.username == username))
        valid = password_matches(password, admin.password_hash if admin else DUMMY_HASH)
        if not admin or not admin.enabled or not valid:
            db.add(Audit(actor=username, action='login_failed', detail='管理员登录失败'))
            db.commit()
            raise HTTPException(401, '账号或密码错误')
        db.execute(delete(Session).where(Session.expires_at <= now()))
        token = secrets.token_urlsafe(32)
        db.add(Session(token_hash=digest(token), admin_id=admin.id, csrf=secrets.token_hex(32),
                       expires_at=now() + timedelta(hours=request.app.state.settings.session_hours)))
        db.add(Audit(actor=admin.username, action='login', detail='管理员登录成功'))
        db.commit()
    response = RedirectResponse('/admin', status_code=303)
    response.delete_cookie('login_csrf')
    response.set_cookie('access_session', token, secure=request.app.state.settings.secure_cookie,
                        httponly=True, samesite='strict',
                        max_age=request.app.state.settings.session_hours * 3600)
    return response


@router.post('/logout')
def logout(request: Request, csrf: str = Form(max_length=64)):
    with request.app.state.sessions() as db:
        admin = authorize_form(request, db, csrf)
        db.delete(db.get(Session, digest(request.cookies['access_session'])))
        db.add(Audit(actor=admin.username, action='logout', detail='管理员退出'))
        db.commit()
    response = RedirectResponse('/login', status_code=303)
    response.delete_cookie('access_session')
    return response
