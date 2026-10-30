"""FastAPI composition. Missing configuration is visible; no production mock fallback."""

import asyncio
import logging
import os
import shutil
from contextlib import asynccontextmanager
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from wiserec_cli import __version__ as cli_version
from ._version import __version__, TESTED_CLI_VERSION
from sqlalchemy import select, delete, update
from .settings import load_settings
from .db import connect, verify_schema
from .models import Session, Attempt, Run, Event, Message, Conversation, ToolCall, now
from .sessions import revoke
from .platform import Platform
from .login import LoginManager
from .keepalive import KeepaliveManager
from .runs import RunManager
from .errors import AppError
from . import auth_api, chat_api

log = logging.getLogger("wiserec.agent")
STATIC = Path(__file__).parent / "static"


def housekeeping(state):
    timestamp = now()
    with state.db() as db:
        sessions = db.scalars(
            select(Session).where(Session.status.not_in(["revoked", "expired"]))
        )
        for s in sessions:
            if (
                s.expires_at <= timestamp
                or s.last_activity
                + timedelta(seconds=state.config.session.idle_timeout_seconds)
                <= timestamp
            ):
                revoke(db, s, "expired")
        from .models import Credential

        for c in db.scalars(
            select(Credential).where(Credential.expires_at <= timestamp)
        ):
            revoke(db, db.get(Session, c.session_id), "expired")
        db.execute(
            delete(Event).where(
                Event.created_at
                < timestamp
                - timedelta(hours=state.config.runtime.event_retention_hours)
            )
        )
        old = list(
            db.scalars(
                select(Conversation.id).where(
                    Conversation.updated_at
                    < timestamp
                    - timedelta(days=state.config.runtime.history_retention_days)
                )
            )
        )
        for cid in old:
            if db.scalar(
                select(Run.id).where(
                    Run.conversation_id == cid, Run.status.in_(["queued", "running"])
                )
            ):
                continue
            ids = list(db.scalars(select(Run.id).where(Run.conversation_id == cid)))
            db.execute(delete(Event).where(Event.run_id.in_(ids)))
            db.execute(delete(ToolCall).where(ToolCall.run_id.in_(ids)))
            db.execute(delete(Message).where(Message.conversation_id == cid))
            db.execute(delete(Run).where(Run.conversation_id == cid))
            db.execute(delete(Conversation).where(Conversation.id == cid))
        db.commit()

    from .artifacts import prune
    with state.db() as db:
        active = set(db.scalars(select(Session.id).where(
            Session.status.not_in(['expired', 'revoked']), Session.expires_at > timestamp)))
    prune(state.config, active)


async def cleanup_loop(state):
    while True:
        try:
            await asyncio.to_thread(housekeeping, state)
        except Exception:
            log.error("cleanup_failed: 请检查数据库连接；未记录敏感异常内容")
        await asyncio.sleep(60)


def create_app(
    config=None,
    *,
    test_url=None,
    platform_transport=None,
    login_provider=None,
    agent_engine=None,
):
    @asynccontextmanager
    async def lifespan(app):
        app.state.ready = False
        app.state.config_error = ""
        try:
            cfg = config or load_settings()
            app.state.config = cfg
            cfg.runtime.state_dir.mkdir(parents=True, exist_ok=True)
            # Process-start setting, never switched per user.
            os.environ["ML_CLIENT_STATE_DIR"] = str(cfg.runtime.state_dir)
            engine, db = connect(cfg, test_url)
            app.state.engine, app.state.db = engine, db
            verify_schema(db)
            with db() as session:
                session.execute(
                    update(Run)
                    .where(Run.status.in_(["queued", "running"]))
                    .values(status="interrupted", error="服务已重启，请重新发送问题")
                )
                session.execute(
                    update(Attempt)
                    .where(
                        Attempt.status.in_(["pending", "awaiting_login", "verifying"])
                    )
                    .values(status="failed", error="服务已重启，请重新登录")
                )
                session.execute(
                    update(ToolCall)
                    .where(ToolCall.status == "running")
                    .values(status="interrupted")
                )
                session.commit()
            if cfg.login.profile_root.exists():
                for child in cfg.login.profile_root.iterdir():
                    # Only UUID-named directories owned by this application.
                    try:
                        UUID(child.name)
                    except ValueError:
                        continue
                    if child.is_dir() and not child.is_symlink():
                        shutil.rmtree(child)
            platform = Platform(cfg, db, platform_transport)
            app.state.platform = platform
            app.state.login = LoginManager(cfg, db, platform, login_provider)
            app.state.runs = RunManager(cfg, db, platform, agent_engine)
            app.state.keepalive = KeepaliveManager(cfg, db, platform)
            app.state.login_lock = asyncio.Lock()
            app.state.ready = True
            cleanup = asyncio.create_task(cleanup_loop(app.state))
            app.state.keepalive.start()
        except Exception:
            app.state.config_error = "服务尚未就绪，请填写 config.local.json，检查数据库连接并执行数据库迁移后重启"
            log.error(
                "startup_not_ready: 配置或数据库检查失败；运行 python -m app.manage check 获取安全诊断"
            )
        yield
        if app.state.ready:
            await app.state.keepalive.close()
            cleanup.cancel()
            await asyncio.gather(cleanup, return_exceptions=True)
            app.state.login.stop.set()
            await app.state.runs.shutdown()
            if app.state.login.task:
                try:
                    await asyncio.wait_for(
                        asyncio.shield(app.state.login.task), timeout=20
                    )
                except (TimeoutError, asyncio.CancelledError):
                    pass
        if hasattr(app.state, "engine"):
            app.state.engine.dispose()

    app = FastAPI(
        title="WiseRec Agent",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        if (
            request.headers.get("content-length", "0").isdigit()
            and int(request.headers.get("content-length", "0")) > 65536
        ):
            return JSONResponse(
                {"error": {"code": "BODY_TOO_LARGE", "message": "请求过大"}},
                status_code=413,
            )
        if (
            request.url.path.startswith("/api/")
            and request.url.path not in ("/api/health", "/api/environments")
            and not app.state.ready
        ):
            response = JSONResponse(
                {
                    "error": {
                        "code": "SETUP_REQUIRED",
                        "message": app.state.config_error,
                    }
                },
                status_code=503,
            )
        else:
            response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    @app.exception_handler(AppError)
    async def app_error(request, exc):
        return JSONResponse(
            {
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "request_id": request.state.request_id,
                }
            },
            status_code=exc.status,
        )

    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(
            {"error": {"code": "INVALID_INPUT", "message": "请求参数格式不正确"}},
            status_code=400,
        )

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        log.error(
            "request_failed id=%s class=%s",
            request.state.request_id,
            type(exc).__name__,
        )
        return JSONResponse(
            {
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务暂时无法完成请求，请检查本地服务状态",
                    "request_id": request.state.request_id,
                }
            },
            status_code=503,
        )

    @app.get("/api/health")
    def health():
        return {"ready": app.state.ready, "message": app.state.config_error,
                "version": __version__, "cli_version": cli_version,
                "tested_cli_version": TESTED_CLI_VERSION}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    # Register safe environment listing before auth router; no invented fallback entries.
    @app.get("/api/environments")
    def environments():
        cfg = getattr(app.state, "config", None)
        return (
            [{"id": e.id, "name": e.name} for e in cfg.environments if e.enabled]
            if cfg
            else []
        )

    app.include_router(auth_api.router)
    app.include_router(chat_api.router)
    from . import action_api
    app.include_router(action_api.router)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
