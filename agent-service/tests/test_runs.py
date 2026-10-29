import time
from uuid import uuid4
from conftest import ready, headers


def run_request(client):
    ready(client)
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    payload = {"message": "查询模型", "client_message_id": str(uuid4())}
    r = client.post(
        f"/api/conversations/{cid}/runs", json=payload, headers=headers(client)
    )
    assert r.status_code == 202, r.text
    return cid, payload, r.json()["run_id"]


def wait(client, rid):
    for _ in range(200):
        r = client.get("/api/runs/" + rid).json()
        if r["status"] not in ("queued", "running"):
            return r
        time.sleep(0.01)
    raise AssertionError("run not settled")


def test_real_service_chain_and_replay(client, app):
    cid, payload, rid = run_request(client)
    r = wait(client, rid)
    assert r["status"] == "completed", r
    duplicate = client.post(
        f"/api/conversations/{cid}/runs", json=payload, headers=headers(client)
    )
    assert duplicate.json()["run_id"] == rid
    events = client.get("/api/runs/" + rid + "/events")
    assert "tool.completed" in events.text and "run.completed" in events.text
    assert (
        "platform-secret-cookie" not in events.text and "should-hide" not in events.text
    )
    ids = [
        int(line[4:]) for line in events.text.splitlines() if line.startswith("id: ")
    ]
    assert ids == sorted(set(ids))
    replay = client.get(
        "/api/runs/" + rid + "/events", headers={"Last-Event-ID": str(ids[-1])}
    )
    assert "tool.started" not in replay.text and "stream.closed" in replay.text
    calls = app.test_upstream.calls
    model = next(r for r in calls if "/models/queryList" in r.url.path)
    assert model.headers["businessid"] == "b1"
    assert model.headers["cookie"] == "platform-secret-cookie"
    idx = calls.index(model)
    assert calls[idx - 1].url.path.endswith("/gateway/check")
    assert "推荐模型" in client.get(f"/api/conversations/{cid}/messages").text


def test_permission_revocation_during_run(client, app):
    ready(client)
    app.test_upstream.allow = False
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    rid = client.post(
        f"/api/conversations/{cid}/runs",
        json={"message": "查询", "client_message_id": str(uuid4())},
        headers=headers(client),
    ).json()["run_id"]
    assert wait(client, rid)["status"] == "failed"
    assert not any("/models/" in r.url.path for r in app.test_upstream.calls)


def test_normalization_preserves_content_and_formats_timezone():
    from app.sanitize import clean
    from decimal import Decimal

    value = clean(
        {
            "id": "00123456-1234-1234-1234-123456789012",
            "secret": "secret",
            "n": Decimal("4"),
            "time": "2026-10-29T02:00:00Z",
            "log": "token=abc",
        }
    )
    assert value["secret"] == "secret"
    assert value["n"] == 4 and type(value["n"]) is int
    assert value["time"] == "2026-10-29 10:00:00"
    assert value["log"] == "token=abc"
    assert value["id"] == "00123456-1234-1234-1234-123456789012"
