"""Confirmed platform activity renews only the exact, still-active credential snapshot."""

from dataclasses import replace
from datetime import timedelta, timezone
from http.cookies import SimpleCookie
from sqlalchemy import select
from .models import Session, Credential, now
from .sessions import valid, revoke
from .errors import AppError


def response_credentials(credentials, response):
    cookies = SimpleCookie()
    cookies.load(credentials.cookie)
    rotated_csrf = None
    changes_received = response.headers.get_list("set-cookie")
    for header in changes_received:
        changes = SimpleCookie()
        changes.load(header)
        for name, item in changes.items():
            if name.lower() == "csrftoken":
                rotated_csrf = "" if item["max-age"] == "0" else item.value
            if item["max-age"] == "0" or not item.value:
                cookies.pop(name, None)
            else:
                cookies[name] = item.value
    csrf = (
        response.headers.get("csrftoken")
        or response.headers.get("x-csrftoken")
        or response.headers.get("x-csrf-token")
    )
    if not csrf:
        csrf = rotated_csrf if rotated_csrf is not None else credentials.csrftoken
    return replace(
        credentials,
        cookie="; ".join(f"{k}={v.value}" for k, v in cookies.items())
        if changes_received
        else credentials.cookie,
        csrftoken=csrf,
    )


def confirm_activity(factory, config, sid, original, updated=None, *, renew=True):
    if not config.session.keepalive_enabled:
        return original
    updated = updated or original
    if not updated.cookie or not updated.csrftoken:
        raise AppError("AUTH_REQUIRED", "平台已删除登录凭据", 401)
    with factory() as db:
        session = db.scalar(select(Session).where(Session.id == sid).with_for_update())
        session = valid(db, config, sid)
        credential = db.get(Credential, sid)
        if (credential.cookie, credential.csrftoken) != (
            original.cookie,
            original.csrftoken,
        ):
            raise AppError("CREDENTIAL_CHANGED", "平台凭据已更新，请重试本次查询", 409)
        timestamp = now()
        credential.cookie, credential.csrftoken = updated.cookie, updated.csrftoken
        if renew:
            credential.expires_at = timestamp + timedelta(
                seconds=config.session.credential_ttl_seconds
            )
            session.last_activity = timestamp
            session.expires_at = timestamp + timedelta(
                seconds=config.session.absolute_timeout_seconds
            )
        db.commit()
        return replace(
            updated,
            expires_at=credential.expires_at.replace(tzinfo=timezone.utc).timestamp(),
        )


def expire_snapshot(factory, sid, original):
    with factory() as db:
        session = db.scalar(select(Session).where(Session.id == sid).with_for_update())
        credential = db.get(Credential, sid)
        if (
            session
            and credential
            and (credential.cookie, credential.csrftoken)
            == (original.cookie, original.csrftoken)
        ):
            revoke(db, session, "expired")
            db.commit()
