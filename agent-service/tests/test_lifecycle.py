import asyncio
import threading
import time
from uuid import uuid4
from sqlalchemy import select
from app.models import Credential, Run, User, Session
from conftest import ready, headers
from test_runs import wait


class WaitingEngine:
    def __init__(self):
        self.started = threading.Event()
        self.stopped = threading.Event()

    async def run(self, history, message, context, invoke, delta, progress=None):
        self.started.set()
        try:
            await asyncio.sleep(60)
        finally:
            self.stopped.set()


def start_waiting(client, app):
    ready(client)
    engine = WaitingEngine()
    app.state.runs.engine = engine
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    rid = client.post(
        f"/api/conversations/{cid}/runs",
        json={"message": "等待取消", "client_message_id": str(uuid4())},
        headers=headers(client),
    ).json()["run_id"]
    assert engine.started.wait(2)
    return engine, cid, rid


def test_cancel_and_concurrent_run_rejected(client, app):
    engine, cid, rid = start_waiting(client, app)
    r = client.post(
        f"/api/conversations/{cid}/runs",
        json={"message": "第二次", "client_message_id": str(uuid4())},
        headers=headers(client),
    )
    assert r.status_code == 409
    assert client.get("/api/session").json()["active_run"]["id"] == rid
    assert (
        client.post("/api/runs/" + rid + "/cancel", headers=headers(client)).status_code
        == 200
    )
    assert engine.stopped.wait(2)
    assert wait(client, rid)["status"] == "cancelled"


def test_logout_cancels_model_and_deletes_credentials(client, app):
    engine, cid, rid = start_waiting(client, app)
    assert client.post("/api/logout", headers=headers(client)).status_code == 200
    assert engine.stopped.wait(2)
    with app.state.db() as db:
        assert db.scalar(select(Credential)) is None
        assert db.get(Run, rid).status == "cancelled"
    assert client.get("/api/runs/" + rid).status_code == 401


def test_second_authenticated_user_cannot_read_first_history(client, app):
    ready(client)
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    client.cookies.clear()
    ready(client)
    # Assign this independently authenticated session a distinct verified identity.
    from app.sessions import digest

    with app.state.db() as db:
        s = db.scalar(
            select(Session).where(
                Session.token_hash
                == digest(client.cookies.get("wiserec_agent_session"))
            )
        )
        u = User(environment_id="dev", username="second-user")
        db.add(u)
        db.flush()
        s.user_id = u.id
        db.commit()
    assert client.get("/api/conversations/" + cid).status_code == 404
    assert client.get("/api/conversations/" + cid + "/messages").status_code == 404
    assert client.get("/api/conversations").json() == []


def test_auth_rejected_revokes_credentials_before_business_call(client, app):
    ready(client)
    app.test_upstream.identity_valid = False
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    response = client.post(
        f"/api/conversations/{cid}/runs",
        json={"message": "查询", "client_message_id": str(uuid4())},
        headers=headers(client),
    )
    assert response.status_code == 202
    for _ in range(100):
        with app.state.db() as db:
            gone = db.scalar(select(Credential)) is None
        if gone:
            break
        time.sleep(0.01)
    assert gone
    assert not any("/models/" in r.url.path for r in app.test_upstream.calls)
