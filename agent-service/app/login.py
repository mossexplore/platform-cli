"""Local interactive Edge authentication; all Playwright objects stay on one thread."""

import asyncio
import threading
import time
from collections import deque
from datetime import timedelta
from urllib.parse import urlsplit
from sqlalchemy import select
from wiserec_cli.auth import BrowserAuthenticator
from wiserec_cli.business import parse_business_list, BusinessStore
from wiserec_cli.models import Profile
from wiserec_cli.errors import BusinessError
from .errors import AppError
from .models import Attempt, Session, Credential, User, UserPreference, now
from .sessions import valid
from .business_preferences import preferred, remember
from .login_support import prepare_profile, login_failure


def selections(raw):
    values = []
    for department in parse_business_list(raw):
        for tenant in department.tenants:
            values.append(
                BusinessStore._make_selection(department, tenant, "").to_dict()
            )
            for team in tenant.teams:
                if team.selectable and team.business_id:
                    values.append(
                        BusinessStore._make_selection(
                            department, tenant, team.id
                        ).to_dict()
                    )
    return values


class LocalEdge:
    def __call__(self, config, env, attempt_id, stop, status):
        from playwright.sync_api import sync_playwright

        stage = "profile"
        try:
            directory = prepare_profile(config, env.id)
        except Exception as exc:
            raise login_failure(stage, exc) from None
        profile = Profile(
            name=env.id, api_endpoint=env.api_endpoint, verify_ssl=env.verify_ssl
        )
        auth = BrowserAuthenticator(store=None)
        headers = deque(maxlen=20)
        info_url = profile.base_url + "/ai/user/info"
        try:
            stage = "browser_launch"
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    str(directory),
                    channel="msedge",
                    headless=False,
                    ignore_https_errors=not env.verify_ssl,
                )
                try:

                    def capture(req):
                        if req.url.split("?", 1)[0].rstrip("/") == info_url:
                            h = req.all_headers()
                            if auth._find_csrftoken(h):
                                headers.append(h)

                    context.on("request", capture)
                    page = context.pages[0] if context.pages else context.new_page()
                    stage = "navigation"
                    page.goto(
                        env.api_endpoint, wait_until="domcontentloaded", timeout=60000
                    )
                    status("awaiting_login")
                    stage = "credential_capture"
                    deadline = time.monotonic() + config.login.timeout_seconds
                    credentials = None
                    while time.monotonic() < deadline:
                        if stop.is_set():
                            raise AppError("LOGIN_CANCELLED", "登录已取消")
                        pages = [page for page in context.pages if not page.is_closed()]
                        if not pages:
                            raise AppError("LOGIN_CLOSED", "登录窗口已关闭，请重新登录")
                        while headers and not credentials:
                            credentials = auth._credentials_from_headers(
                                context,
                                profile,
                                info_url,
                                config.session.credential_ttl_seconds,
                                15000,
                                headers.popleft(),
                            )
                        if credentials and credentials.username.strip():
                            for current in pages:
                                if (
                                    urlsplit(current.url).netloc
                                    != urlsplit(env.api_endpoint).netloc
                                ):
                                    continue
                                stage = "business_catalog"
                                raw = current.evaluate(
                                    "localStorage.getItem('ai-businessList')"
                                )
                                if raw:
                                    try:
                                        catalog = selections(raw)
                                    except BusinessError:
                                        # Platform may populate the directory after user/info succeeds.
                                        continue
                                    status("verifying")
                                    return credentials, catalog
                        pages[-1].wait_for_timeout(250)
                    if credentials:
                        raise AppError(
                            "LOGIN_CATALOG_TIMEOUT",
                            "平台身份已确认，但等待有效业务目录超时（阶段=business_catalog），请确认平台已加载可访问的租户或团队",
                        )
                    raise AppError(
                        "LOGIN_TIMEOUT",
                        "等待平台登录凭据超时（阶段=credential_capture），请确认平台登录已完成",
                    )
                finally:
                    try:
                        context.close()
                    except Exception as exc:
                        raise login_failure("browser_close", exc) from None
        except Exception as exc:
            raise login_failure(stage, exc) from None


class LoginManager:
    def __init__(self, config, db, platform, provider=None):
        self.config, self.db, self.platform = config, db, platform
        self.provider = provider or LocalEdge()
        self.active = None
        self.active_environment = None
        self.stop = threading.Event()
        self.task = None

    def busy(self):
        return self.task is not None and not self.task.done()

    def start(self, attempt_id):
        self.active = attempt_id
        with self.db() as db:
            self.active_environment = db.get(Attempt, attempt_id).environment_id
        self.stop = threading.Event()
        self.task = asyncio.create_task(self._run(attempt_id, self.stop))

    def cancel(self, attempt_id):
        if self.active == attempt_id:
            self.stop.set()

    @staticmethod
    def clear_partial(db, attempt):
        if attempt.status in ("succeeded", "consumed"):
            return
        session = db.get(Session, attempt.session_id)
        if session and session.status not in ("revoked", "expired"):
            credential = db.get(Credential, session.id)
            if credential:
                db.delete(credential)
            session.user_id = session.environment_id = session.business = None
            session.catalog = []
            session.status = "anonymous"

    def _status(self, attempt_id, state):
        with self.db() as db:
            a = db.get(Attempt, attempt_id)
            if a and a.status not in ("cancelled", "failed", "succeeded"):
                a.status = state
                db.commit()

    async def _run(self, attempt_id, stop):
        stage = "provider"
        try:
            with self.db() as db:
                a = db.get(Attempt, attempt_id)
                env = self.config.env(a.environment_id)
            credentials, catalog = await asyncio.to_thread(
                self.provider,
                self.config,
                env,
                attempt_id,
                stop,
                lambda state: self._status(attempt_id, state),
            )
            # Verify again using the actual server HTTP client, independent of Edge request context.
            stage = "identity_probe"
            identity = await asyncio.to_thread(self.platform.identity, env, credentials)
            stage = "credential_save"
            with self.db() as db:
                a = db.scalar(
                    select(Attempt).where(Attempt.id == attempt_id).with_for_update()
                )
                if stop.is_set() or a.status == "cancelled" or a.expires_at <= now():
                    return
                s = valid(db, self.config, a.session_id, False)
                u = db.scalar(
                    select(User).where(
                        User.environment_id == env.id,
                        User.username == identity["username"],
                    )
                )
                if not u:
                    u = User(environment_id=env.id, username=identity["username"])
                    db.add(u)
                    db.flush()
                u.display_name, u.department = (
                    identity.get("cnName", ""),
                    identity.get("department", ""),
                )
                s.user_id, s.environment_id, s.status, s.catalog = (
                    u.id,
                    env.id,
                    "business_required",
                    catalog,
                )
                s.last_activity = now()
                db.add(
                    Credential(
                        session_id=s.id,
                        cookie=credentials.cookie,
                        csrftoken=credentials.csrftoken,
                        expires_at=now()
                        + timedelta(seconds=self.config.session.credential_ttl_seconds),
                    )
                )
                restore = preferred(db, u.id, catalog)
                missing_preference = (
                    db.get(UserPreference, u.id) is not None and restore is None
                )
                sid = s.id
                db.commit()
            notice = (
                "上次使用的租户已不在本次可用目录中，请重新选择"
                if missing_preference
                else ""
            )
            if restore:
                stage = "business_restore"
                try:
                    await asyncio.to_thread(
                        self.platform.gateway,
                        sid,
                        restore,
                        "business_selection",
                        attempt_id,
                    )
                    with self.db() as db:
                        a = db.get(Attempt, attempt_id)
                        if stop.is_set() or a.status == "cancelled":
                            self.clear_partial(db, a)
                            db.commit()
                            return
                        s = valid(db, self.config, sid)
                        s.business, s.status, s.last_activity = restore, "ready", now()
                        remember(db, s.user_id, restore)
                        db.commit()
                except AppError as exc:
                    if exc.status == 401:
                        raise
                    notice = "上次使用的租户暂时无法通过权限校验，请重新选择"
            with self.db() as db:
                a = db.get(Attempt, attempt_id)
                if stop.is_set() or a.status == "cancelled":
                    self.clear_partial(db, a)
                    db.commit()
                    return
                valid(db, self.config, sid)
                a.status, a.error = "succeeded", notice
                db.commit()
        except Exception as exc:
            with self.db() as db:
                a = db.get(Attempt, attempt_id)
                if a and a.status != "cancelled":
                    a.status = "failed"
                    self.clear_partial(db, a)
                    a.error = login_failure(stage, exc).message
                    db.commit()
