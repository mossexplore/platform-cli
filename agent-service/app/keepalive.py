"""Single-process server-side platform keepalive; no model calls or CLI subprocesses."""

import asyncio
import logging
import threading
from datetime import timedelta
import httpx
from sqlalchemy import select
from wiserec_cli.models import Profile
from wiserec_cli.access_transport import tls_verify
from .models import Session, Credential, now
from .errors import AppError
from .credential_activity import confirm_activity, response_credentials, expire_snapshot

log = logging.getLogger("uvicorn.error.agent_keepalive")
AUTH_CODES = {401, 403, 419, 440, "UNAUTHORIZED", "SESSION_EXPIRED"}


class KeepaliveManager:
    def __init__(self, config, factory, platform):
        self.config, self.db, self.platform = config, factory, platform
        self.stop = threading.Event()
        self.task = None
        self.retry_after = {}

    def probe(self, sid):
        with self.platform.credential_locks[sid]:
            session, env, original = self.platform.context(sid)
            if session.status != "ready" or not session.business:
                return
            try:
                identity, identity_response = self.platform.identity(
                    env, original, return_response=True
                )
                probe_credentials = response_credentials(original, identity_response)
                if identity["username"] != original.username:
                    raise AppError(
                        "IDENTITY_CHANGED", "平台身份已改变，请重新登录", 401
                    )
                if (probe_credentials.cookie, probe_credentials.csrftoken) != (
                    original.cookie,
                    original.csrftoken,
                ):
                    # Identity succeeded and rotated tokens. Preserve that rotation even
                    # if the following gateway/probe is transiently unavailable; no TTL extension yet.
                    original = confirm_activity(
                        self.db,
                        self.config,
                        sid,
                        original,
                        probe_credentials,
                        renew=False,
                    )
                    probe_credentials = original
                # Re-check user/environment/business authorization before platform business traffic.
                from uuid import uuid4

                self.platform.gateway(sid, session.business, "keepalive", str(uuid4()))
                self.platform.context(sid)
                with httpx.Client(
                    transport=self.platform.transport,
                    verify=tls_verify() if env.verify_ssl else False,
                    trust_env=False,
                    timeout=self.config.runtime.platform_timeout_seconds,
                    follow_redirects=False,
                ) as client:
                    response = client.post(
                        Profile(env.id, env.api_endpoint).base_url
                        + "/ai/backend/mep/tenant/queryTeamList",
                        headers={
                            "cookie": probe_credentials.cookie,
                            "csrftoken": probe_credentials.csrftoken,
                            "referer": env.api_endpoint,
                            "businessid": session.business["businessId"],
                            "ai-businessId": session.business["businessId"],
                        },
                        json={"businessId": session.business["businessId"]},
                    )
                if response.status_code in (401, 419, 440) or response.is_redirect:
                    raise AppError("AUTH_REQUIRED", "平台会话已失效", 401)
                if response.status_code == 403:
                    # A resource denial alone does not prove the account session expired.
                    self.platform.identity(env, probe_credentials)
                    raise AppError("KEEPALIVE_DENIED", "平台拒绝保活请求", 403)
                response.raise_for_status()
                result = response.json().get("result", {})
                if result.get("code") in AUTH_CODES:
                    raise AppError("AUTH_REQUIRED", "平台会话已失效", 401)
                if type(result.get("code")) is not int or result["code"] != 0:
                    raise AppError("KEEPALIVE_NOT_CONFIRMED", "平台未确认保活成功", 502)
                updated = response_credentials(probe_credentials, response)
                if not updated.cookie or not updated.csrftoken:
                    raise AppError("AUTH_REQUIRED", "平台已删除登录凭据", 401)
                confirm_activity(self.db, self.config, sid, original, updated)
            except AppError as exc:
                if exc.status == 401:
                    expire_snapshot(self.db, sid, original)
                raise

    def tick(self):
        if not self.config.session.keepalive_enabled or self.stop.is_set():
            return
        timestamp = now()
        interval = self.config.session.keepalive_interval_seconds
        ttl = self.config.session.credential_ttl_seconds
        with self.db() as db:
            rows = list(
                db.execute(
                    select(Session.id, Credential.expires_at)
                    .join(Credential, Credential.session_id == Session.id)
                    .where(Session.status == "ready")
                )
            )
        current = {sid for sid, _ in rows}
        self.retry_after = {
            sid: due for sid, due in self.retry_after.items() if sid in current
        }
        for sid, expires in rows:
            if self.stop.is_set():
                return
            if timestamp < expires - timedelta(seconds=ttl) + timedelta(
                seconds=interval
            ):
                continue
            if timestamp < self.retry_after.get(sid, timestamp):
                continue
            try:
                self.probe(sid)
                self.retry_after.pop(sid, None)
                log.info("keepalive session=%s status=confirmed", sid)
            except Exception as exc:
                self.retry_after[sid] = now() + timedelta(seconds=min(60, interval))
                log.warning(
                    "keepalive session=%s class=%s code=%s; secrets omitted",
                    sid,
                    type(exc).__name__,
                    exc.code if isinstance(exc, AppError) else "NETWORK_OR_STORAGE",
                )

    async def loop(self):
        while not self.stop.is_set():
            worker = asyncio.create_task(asyncio.to_thread(self.tick))
            try:
                await asyncio.shield(worker)
            except asyncio.CancelledError:
                await asyncio.gather(worker, return_exceptions=True)
                raise
            except Exception as exc:
                log.warning("keepalive scan_failed class=%s", type(exc).__name__)
            await asyncio.sleep(5)

    def start(self):
        if self.config.session.keepalive_enabled:
            self.task = asyncio.create_task(self.loop())

    async def close(self):
        self.stop.set()
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
