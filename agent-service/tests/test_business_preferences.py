import time
import httpx
from conftest import ready, login, headers, BUSINESS, provider
from app.business_preferences import business_key


def logout(client):
    assert client.post("/api/logout", headers=headers(client)).status_code == 200


def test_relogin_restores_last_business_without_selection(client, app):
    ready(client)
    logout(client)
    session = login(client)
    assert session["status"] == "ready" and session["business"] == BUSINESS
    assert any(r.url.path.endswith("/gateway/check") for r in app.test_upstream.calls)


def test_permission_revoked_falls_back_to_business_picker(client, app):
    ready(client)
    logout(client)
    app.test_upstream.allow = False
    session = login(client)
    assert session["status"] == "business_required" and session["business"] is None


def test_removed_business_is_not_restored(client, app):
    ready(client)
    logout(client)

    def new_catalog(*args):
        cred, _ = provider(*args)
        return cred, [
            {**BUSINESS, "tenant_id": "b2", "businessId": "b2", "tenant_name": "Other"}
        ]

    app.state.login.provider = new_catalog
    session = login(client)
    assert session["status"] == "business_required" and session["business"] is None


def test_preference_is_not_shared_with_another_environment(client, app):
    ready(client)
    logout(client)
    result = client.post(
        "/api/login-attempts",
        headers=headers(client),
        json={"environment_id": "mirror"},
    ).json()
    for _ in range(100):
        status = client.get("/api/login-attempts/" + result["attempt_id"]).json()
        if status["status"] == "succeeded":
            break
        time.sleep(0.02)
    session = client.get("/api/session").json()
    assert (
        session["environment_id"] == "mirror"
        and session["status"] == "business_required"
    )


def test_preference_is_not_shared_with_another_account(client, app):
    ready(client)
    logout(client)

    def another_user(request):
        if request.url.path == "/ai/user/info":
            return httpx.Response(
                200, json={"result": {"code": 0, "username": "another-user"}}
            )
        return app.test_upstream(request)

    app.state.platform.transport = httpx.MockTransport(another_user)
    session = login(client)
    assert session["user"]["username"] == "another-user"
    assert session["status"] == "business_required"


def test_duplicate_business_id_requires_precise_selection_and_remembers_team(
    client, app
):
    team = {**BUSINESS, "type": "team", "team_id": "team-2", "team_name": "Team 2"}

    def catalog(*args):
        cred, _ = provider(*args)
        return cred, [BUSINESS, team]

    app.state.login.provider = catalog
    login(client)
    r = client.post(
        "/api/business-selection", headers=headers(client), json={"business_id": "b1"}
    )
    assert r.status_code == 409
    r = client.post(
        "/api/business-selection",
        headers=headers(client),
        json={"business_id": "b1", "selection_key": business_key(team)},
    )
    assert r.status_code == 200 and r.json()["business"]["team_id"] == "team-2"
    logout(client)
    restored = login(client)
    assert restored["status"] == "ready" and restored["business"]["team_id"] == "team-2"


def test_cancel_during_auto_restore_does_not_leave_authenticated_partial_session(
    client, app
):
    import threading
    from sqlalchemy import select
    from app.models import Credential

    ready(client)
    logout(client)
    started, release = threading.Event(), threading.Event()
    original = app.state.platform.gateway

    def slow(*args, **kwargs):
        started.set()
        assert release.wait(2)
        return original(*args, **kwargs)

    app.state.platform.gateway = slow
    attempt = client.post(
        "/api/login-attempts", headers=headers(client), json={"environment_id": "dev"}
    ).json()["attempt_id"]
    assert started.wait(2)
    # Use the original anonymous CSRF; GET /session could expose the pending verified identity.
    pending = client.get("/api/session").json()
    assert pending["status"] == "anonymous" and pending["user"] is None
    assert client.get("/api/businesses").status_code == 409
    csrf = pending["csrf_token"]
    response = client.post(
        "/api/login-attempts/" + attempt + "/cancel",
        headers={"Origin": "http://testserver", "X-Agent-CSRF": csrf},
    )
    release.set()
    assert response.status_code == 200
    for _ in range(100):
        if not app.state.login.busy():
            break
        time.sleep(0.01)
    assert client.get("/api/session").json()["status"] == "anonymous"
    with app.state.db() as db:
        assert db.scalar(select(Credential)) is None


def test_existing_account_bootstraps_preference_from_latest_conversation(client, app):
    from sqlalchemy import delete
    from app.models import UserPreference

    ready(client)
    assert client.post("/api/conversations", headers=headers(client)).status_code == 201
    with app.state.db() as db:
        db.execute(delete(UserPreference))
        db.commit()
    logout(client)
    assert login(client)["status"] == "ready"
