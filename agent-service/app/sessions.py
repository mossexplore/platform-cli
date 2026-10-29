"""Browser session ownership and explicit revocation, independent of platform cookies."""

import hashlib
import secrets
from datetime import timedelta
from sqlalchemy import select, delete, update
from .models import Session, Credential, Attempt, Run, User, now
from .errors import AppError

TERMINAL = {"completed", "failed", "cancelled", "interrupted"}


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def revoke(db, session, status="revoked"):
    session.status = status
    session.business = None
    session.catalog = []
    db.execute(delete(Credential).where(Credential.session_id == session.id))
    db.execute(
        update(Attempt)
        .where(
            Attempt.session_id == session.id,
            Attempt.status.in_(["pending", "awaiting_login", "verifying"]),
        )
        .values(status="cancelled")
    )
    db.execute(
        update(Run)
        .where(Run.session_id == session.id, Run.status.in_(["queued", "running"]))
        .values(status="cancelled")
    )


def valid(db, config, session_id, authenticated=True):
    s = db.get(Session, session_id, populate_existing=True)
    if not s or s.status in ("revoked", "expired"):
        raise AppError("AUTH_REQUIRED", "登录已失效，请重新登录", 401)
    timestamp = now()
    if (
        s.expires_at <= timestamp
        or s.last_activity + timedelta(seconds=config.session.idle_timeout_seconds)
        <= timestamp
    ):
        revoke(db, s, "expired")
        db.commit()
        raise AppError("AUTH_REQUIRED", "登录已过期，请重新登录", 401)
    if authenticated:
        c = db.get(Credential, s.id)
        if not s.user_id or not c:
            raise AppError("AUTH_REQUIRED", "请先完成平台登录", 401)
        if c.expires_at <= timestamp:
            revoke(db, s, "expired")
            db.commit()
            raise AppError("AUTH_REQUIRED", "平台凭据已过期，请重新登录", 401)
        if not config.env(s.environment_id):
            raise AppError("ENVIRONMENT_DISABLED", "当前环境已停用", 403)
    return s


def request_session(request, db, authenticated=True):
    config = request.app.state.config
    token = request.cookies.get(config.session.cookie_name, "")
    s = (
        db.scalar(select(Session).where(Session.token_hash == digest(token)))
        if token
        else None
    )
    if not s:
        raise AppError("AUTH_REQUIRED", "请先登录", 401)
    return valid(db, config, s.id, authenticated)


def protect(request, session):
    if request.headers.get("origin") != str(request.base_url).rstrip("/"):
        raise AppError("ORIGIN_REJECTED", "请求来源不匹配，请刷新页面", 403)
    supplied = request.headers.get("x-agent-csrf", "")
    if not secrets.compare_digest(supplied, session.csrf):
        raise AppError("CSRF_REJECTED", "页面会话已更新，请刷新页面", 403)


def new_session(db, config):
    token = secrets.token_urlsafe(32)
    s = Session(
        token_hash=digest(token),
        csrf=secrets.token_hex(32),
        expires_at=now() + timedelta(seconds=config.session.absolute_timeout_seconds),
    )
    db.add(s)
    db.commit()
    return s, token


def public_session(db, s):
    u = db.get(User, s.user_id) if s.user_id else None
    active = db.scalar(
        select(Run).where(Run.session_id == s.id, Run.status.in_(["queued", "running"]))
    )
    return {
        "active_run": {"id": active.id, "conversation_id": active.conversation_id}
        if active
        else None,
        "status": s.status,
        "csrf_token": s.csrf,
        "environment_id": s.environment_id,
        "business": s.business,
        "user": {"username": u.username, "name": u.display_name} if u else None,
    }
