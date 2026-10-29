from dataclasses import replace
from datetime import timedelta
import httpx
import pytest
from sqlalchemy import select
from app.models import Session, Credential, now
from app.credential_activity import confirm_activity
from app.errors import AppError
from conftest import ready, headers


def setup_session(client, app, handler=None):
    ready(client)
    with app.state.db() as db:
        s = db.scalar(select(Session).where(Session.status == "ready"))
        c = db.get(Credential, s.id)
        c.cookie = "sid=old; csrftoken=old-csrf"
        c.csrftoken = "old-csrf"
        c.expires_at = now() + timedelta(
            seconds=app.state.config.session.credential_ttl_seconds - 601
        )
        s.expires_at = now() + timedelta(seconds=100)
        sid = s.id
        db.commit()
    calls = []

    def upstream(request):
        calls.append(request)
        if request.url.path.endswith("queryTeamList"):
            if handler:
                return handler(request, sid)
            return httpx.Response(
                200,
                json={"result": {"code": 0}},
                headers=[
                    ("set-cookie", "sid=new; Path=/"),
                    ("set-cookie", "csrftoken=new-csrf; Path=/"),
                ],
            )
        return app.test_upstream(request)

    app.state.platform.transport = httpx.MockTransport(upstream)
    return sid, calls


def test_keepalive_rotates_cookies_and_slides_all_expirations(client, app):
    sid, calls = setup_session(client, app)
    before = now()
    app.state.keepalive.tick()
    with app.state.db() as db:
        c = db.get(Credential, sid)
        s = db.get(Session, sid)
        assert "sid=new" in c.cookie and c.csrftoken == "new-csrf"
        assert c.expires_at > before + timedelta(seconds=1700)
        assert s.expires_at > before + timedelta(hours=7)
        assert s.last_activity >= before
    probe = next(r for r in calls if r.url.path.endswith("queryTeamList"))
    assert (
        probe.headers["businessid"] == "b1" and probe.headers["csrftoken"] == "old-csrf"
    )
    assert calls[calls.index(probe) - 1].url.path.endswith("/gateway/check")
    count = len(calls)
    app.state.keepalive.tick()
    assert len(calls) == count


def test_transient_failure_never_extends_or_erases_credentials(client, app):
    sid, calls = setup_session(client, app, lambda *_: httpx.Response(503))
    with app.state.db() as db:
        before = db.get(Credential, sid).expires_at
    app.state.keepalive.tick()
    with app.state.db() as db:
        assert db.get(Credential, sid).expires_at == before
        assert db.get(Session, sid).status == "ready"
    count = len(calls)
    app.state.keepalive.tick()
    assert len(calls) == count


def test_platform_auth_expiry_stops_keepalive(client, app):
    sid, calls = setup_session(client, app, lambda *_: httpx.Response(401))
    app.state.keepalive.tick()
    with app.state.db() as db:
        assert db.get(Credential, sid) is None
        assert db.get(Session, sid).status == "expired"
    count = len(calls)
    app.state.keepalive.tick()
    assert len(calls) == count


def test_logout_during_probe_cannot_resurrect_credentials(client, app):
    def logout(request, sid):
        from app.sessions import revoke

        with app.state.db() as db:
            revoke(db, db.get(Session, sid))
            db.commit()
        return httpx.Response(200, json={"result": {"code": 0}})

    sid, calls = setup_session(client, app, logout)
    app.state.keepalive.tick()
    with app.state.db() as db:
        assert db.get(Credential, sid) is None
        assert db.get(Session, sid).status == "revoked"


def test_old_snapshot_cannot_overwrite_new_login_or_rotation(client, app):
    sid, _ = setup_session(client, app)
    _, _, original = app.state.platform.context(sid)
    with app.state.db() as db:
        db.get(Credential, sid).cookie = "sid=other"
        db.commit()
    with pytest.raises(AppError, match="凭据已更新"):
        confirm_activity(
            app.state.db,
            app.state.config,
            sid,
            original,
            replace(original, cookie="sid=stale"),
        )
    with app.state.db() as db:
        assert db.get(Credential, sid).cookie == "sid=other"


def test_ordinary_success_extends_without_background_model_call(client, app):
    sid, _ = setup_session(client, app)
    with app.state.db() as db:
        s = db.get(Session, sid)
        business = s.business
        before = db.get(Credential, sid).expires_at
    app.state.platform.execute(
        sid,
        None,
        business,
        "list_models",
        {"page": 1, "page_size": 10},
        "activity-test",
    )
    with app.state.db() as db:
        c = db.get(Credential, sid)
        assert c.expires_at > before
        assert c.cookie == "sid=old; csrftoken=old-csrf"


def test_disabled_keepalive_preserves_fixed_timeouts(client, app):
    sid, calls = setup_session(client, app)
    app.state.config.session.keepalive_enabled = False
    app.state.keepalive.tick()
    assert calls == []


def test_browser_cookie_get_session_renews_but_never_renews_platform_ttl(client, app):
    sid, _ = setup_session(client, app)
    with app.state.db() as db:
        before = db.get(Credential, sid).expires_at
    response = client.get("/api/session")
    assert "Max-Age=31536000" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    with app.state.db() as db:
        assert db.get(Credential, sid).expires_at == before


def test_real_logout_removes_probe_eligibility(client, app):
    sid, calls = setup_session(client, app)
    client.post("/api/logout", headers=headers(client))
    app.state.keepalive.tick()
    assert not calls


def test_config_rejects_keepalive_after_credential_expiry(settings):
    from app.settings import Settings
    from pydantic import ValidationError

    data = settings.model_dump()
    data["session"]["credential_ttl_seconds"] = 300
    with pytest.raises(ValidationError):
        Settings.model_validate(data)
    data["session"]["keepalive_enabled"] = False
    assert Settings.model_validate(data)


def test_identity_rotated_cookie_is_used_by_keepalive_request(client, app):
    sid, calls = setup_session(
        client, app, lambda *_: httpx.Response(200, json={"result": {"code": 0}})
    )
    original = app.test_upstream

    def rotated(request):
        if request.url.path == "/ai/user/info":
            return httpx.Response(
                200,
                json={"result": {"code": 0, "username": "zhangsan"}},
                headers=[
                    ("set-cookie", "sid=identity-new; Path=/"),
                    ("x-csrftoken", "identity-csrf"),
                ],
            )
        return original(request)

    app.test_upstream = rotated
    app.state.keepalive.tick()
    probe = next(r for r in calls if r.url.path.endswith("queryTeamList"))
    assert "sid=identity-new" in probe.headers["cookie"]
    assert probe.headers["csrftoken"] == "identity-csrf"
    with app.state.db() as db:
        c = db.get(Credential, sid)
        assert "sid=identity-new" in c.cookie and c.csrftoken == "identity-csrf"


def test_keepalive_permission_denial_does_not_send_platform_business_request(
    client, app
):
    sid, calls = setup_session(client, app)
    app.test_upstream.allow = False
    with app.state.db() as db:
        before = db.get(Credential, sid).expires_at
    app.state.keepalive.tick()
    assert not any(r.url.path.endswith("queryTeamList") for r in calls)
    with app.state.db() as db:
        assert db.get(Credential, sid).expires_at == before


async def test_keepalive_shutdown_stops_scan(settings):
    from app.keepalive import KeepaliveManager
    from types import SimpleNamespace
    import asyncio

    manager = KeepaliveManager(settings, None, SimpleNamespace())
    calls = []
    manager.tick = lambda: calls.append(True)
    manager.start()
    await asyncio.sleep(0.05)
    await manager.close()
    assert calls and manager.task.done() and manager.stop.is_set()


def test_identity_rotation_survives_following_transient_probe_failure_without_ttl_extension(
    client, app
):
    sid, calls = setup_session(client, app, lambda *_: httpx.Response(503))
    with app.state.db() as db:
        before = db.get(Credential, sid).expires_at
    original = app.test_upstream

    def rotated(request):
        if request.url.path == "/ai/user/info":
            return httpx.Response(
                200,
                json={"result": {"code": 0, "username": "zhangsan"}},
                headers={"set-cookie": "sid=rotated-before-outage; Path=/"},
            )
        return original(request)

    app.test_upstream = rotated
    app.state.keepalive.tick()
    with app.state.db() as db:
        c = db.get(Credential, sid)
        assert "sid=rotated-before-outage" in c.cookie
        assert c.expires_at == before and db.get(Session, sid).status == "ready"
