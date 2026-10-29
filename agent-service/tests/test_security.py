from datetime import timedelta
from sqlalchemy import select
from app.models import Credential, Session, now
from conftest import headers, login, ready


def test_anonymous_cannot_chat(client):
    assert client.post("/api/conversations", headers=headers(client)).status_code == 401


def test_csrf_origin_and_environment(client):
    h = headers(client)
    assert (
        client.post("/api/login-attempts", json={"environment_id": "dev"}).status_code
        == 403
    )
    assert (
        client.post(
            "/api/login-attempts",
            json={"environment_id": "dev"},
            headers={**h, "Origin": "http://evil.test"},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/login-attempts", json={"environment_id": "unconfigured"}, headers=h
        ).status_code
        == 400
    )


def test_login_rotates_token_and_does_not_leak(client, app):
    headers(client)
    old = client.cookies.get("wiserec_agent_session")
    session = login(client)
    assert client.cookies.get("wiserec_agent_session") != old
    assert session["user"]["username"] == "zhangsan"
    assert "cookie" not in str(session) and "csrf-secret" not in str(session)
    assert session["status"] == "business_required"
    assert client.post("/api/conversations", headers=headers(client)).status_code == 409
    assert (
        client.post(
            "/api/business-selection",
            json={"business_id": "other"},
            headers=headers(client),
        ).status_code
        == 403
    )


def test_permission_denial_blocks_business(client, app):
    login(client)
    app.test_upstream.allow = False
    response = client.post(
        "/api/business-selection", json={"business_id": "b1"}, headers=headers(client)
    )
    assert response.status_code == 403
    assert all("/models/" not in r.url.path for r in app.test_upstream.calls)


def test_logout_deletes_credentials_and_revokes(client, app):
    ready(client)
    h = headers(client)
    assert client.post("/api/logout", headers=h).status_code == 200
    with app.state.db() as db:
        assert db.scalar(select(Credential)) is None
        assert (
            db.scalar(select(Session).where(Session.user_id.is_not(None))).status
            == "revoked"
        )
    assert client.get("/api/businesses").status_code == 401


def test_expiry_erases_credentials(client, app):
    ready(client)
    with app.state.db() as db:
        c = db.scalar(select(Credential))
        c.expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/businesses").status_code == 401
    with app.state.db() as db:
        assert db.scalar(select(Credential)) is None


def test_attempt_and_conversation_ownership(client, app):
    ready(client)
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    # Separate browser cookie jar; same app lifecycle.
    old = dict(client.cookies)
    client.cookies.clear()
    headers(client)
    assert client.get("/api/conversations/" + cid + "/messages").status_code == 401
    client.cookies.update(old)


def test_security_headers_and_markup(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "在 Edge 中登录" in r.text
    assert client.get("/", headers={"host": "evil.test"}).status_code == 400
