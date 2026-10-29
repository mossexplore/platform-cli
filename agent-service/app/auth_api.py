import asyncio
import secrets
from datetime import timedelta
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from .models import Attempt, Run, now
from .sessions import (
    request_session,
    new_session,
    public_session,
    protect,
    digest,
    revoke,
)
from .errors import AppError

router = APIRouter(prefix="/api")


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    environment_id: str = Field(max_length=32)


class BusinessBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    business_id: str = Field(min_length=1, max_length=256)


def set_cookie(response, config, token):
    response.set_cookie(
        config.session.cookie_name,
        token,
        httponly=True,
        secure=False,
        samesite="lax",
        path="/",
        max_age=config.session.absolute_timeout_seconds,
    )


@router.get("/environments")
def environments(request: Request):
    return [
        {"id": e.id, "name": e.name}
        for e in request.app.state.config.environments
        if e.enabled
    ]


@router.get("/session")
def session(request: Request, response: Response):
    state = request.app.state
    with state.db() as db:
        try:
            s = request_session(request, db, False)
            if s.user_id:
                s = request_session(request, db, True)
        except AppError:
            s, token = new_session(db, state.config)
            set_cookie(response, state.config, token)
        return public_session(db, s)


@router.post("/login-attempts", status_code=202)
async def login(body: LoginBody, request: Request):
    state = request.app.state
    async with state.login_lock:
        with state.db() as db:
            s = request_session(request, db, False)
            protect(request, s)
            if s.user_id:
                raise AppError("LOGIN_CONFLICT", "请先退出当前环境", 409)
            if not state.config.env(body.environment_id):
                raise AppError("ENVIRONMENT_INVALID", "环境不可用")
            if state.login.busy():
                raise AppError("LOGIN_BUSY", "已有登录窗口，请完成或取消后重试", 409)
            a = Attempt(
                session_id=s.id,
                environment_id=body.environment_id,
                expires_at=now()
                + timedelta(seconds=state.config.login.timeout_seconds + 60),
            )
            s.last_activity = now()
            db.add(a)
            db.commit()
            state.login.start(a.id)
            return {"attempt_id": a.id}


@router.get("/login-attempts/{attempt_id}")
def login_status(attempt_id: str, request: Request, response: Response):
    state = request.app.state
    with state.db() as db:
        s = request_session(request, db, False)
        a = db.scalar(select(Attempt).where(Attempt.id == attempt_id).with_for_update())
        if not a or a.session_id != s.id:
            raise AppError("NOT_FOUND", "登录任务不存在", 404)
        if a.status == "succeeded":
            token = secrets.token_urlsafe(32)
            s.token_hash, s.csrf = digest(token), secrets.token_hex(32)
            a.status = "consumed"
            db.commit()
            set_cookie(response, state.config, token)
        return {
            "status": "succeeded" if a.status == "consumed" else a.status,
            "message": a.error,
        }


@router.post("/login-attempts/{attempt_id}/cancel")
def cancel_login(attempt_id: str, request: Request):
    state = request.app.state
    with state.db() as db:
        s = request_session(request, db, False)
        protect(request, s)
        a = db.get(Attempt, attempt_id)
        if not a or a.session_id != s.id:
            raise AppError("NOT_FOUND", "登录任务不存在", 404)
        if a.status not in ("succeeded", "consumed", "failed", "cancelled"):
            a.status = "cancelled"
        db.commit()
        state.login.cancel(a.id)
    return {"ok": True}


@router.get("/businesses")
def businesses(request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        return s.catalog


@router.post("/business-selection")
async def select_business(body: BusinessBody, request: Request):
    state = request.app.state
    async with state.runs.lock:
        with state.db() as db:
            s = request_session(request, db)
            protect(request, s)
            if db.scalar(
                select(Run.id).where(
                    Run.session_id == s.id, Run.status.in_(["running", "queued"])
                )
            ):
                raise AppError("RUN_ACTIVE", "请等待当前运行结束再选择业务", 409)
            matches = [b for b in s.catalog if b["businessId"] == body.business_id]
            if not matches:
                raise AppError("BUSINESS_DENIED", "业务不可用", 403)
            business, sid = matches[0], s.id
        await asyncio.to_thread(
            state.platform.gateway,
            sid,
            business,
            "business_selection",
            secrets.token_hex(16),
        )
        with state.db() as db:
            s = request_session(request, db)
            s.business, s.status, s.last_activity = business, "ready", now()
            db.commit()
            return public_session(db, s)


@router.post("/logout")
async def logout(request: Request, response: Response):
    state = request.app.state
    with state.db() as db:
        try:
            s = request_session(request, db, False)
        except AppError:
            response.delete_cookie(state.config.session.cookie_name)
            return {"ok": True}
        protect(request, s)
        attempts = list(
            db.scalars(select(Attempt.id).where(Attempt.session_id == s.id))
        )
        runs = list(
            db.scalars(
                select(Run.id).where(
                    Run.session_id == s.id, Run.status.in_(["queued", "running"])
                )
            )
        )
        revoke(db, s)
        db.commit()
    for a in attempts:
        state.login.cancel(a)
    for r in runs:
        await state.runs.stop(r)
    response.delete_cookie(state.config.session.cookie_name, path="/")
    return {"ok": True}
