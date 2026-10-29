"""Regression tests for database latency, cooperative streaming and cancellation."""

import asyncio
import threading
import time
from uuid import uuid4
from sqlalchemy import select
from app.models import Event, Run
from conftest import ready, headers
from test_runs import wait


def start(client):
    ready(client)
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    return client.post(
        f"/api/conversations/{cid}/runs",
        json={"message": "查询", "client_message_id": str(uuid4())},
        headers=headers(client),
    ).json()["run_id"]


class Burst:
    def __init__(self, forever=False):
        self.forever = forever
        self.ticks = 0
        self.thread = None
        self.stopped = threading.Event()

    async def run(self, history, message, context, invoke, delta, progress=None):
        self.thread = threading.get_ident()

        async def ticker():
            while True:
                await asyncio.sleep(0.01)
                self.ticks += 1

        ticker_task = asyncio.create_task(ticker())
        try:
            await progress("model_request")
            count = 0
            while self.forever or count < 2000:
                await delta("字")
                count += 1
            await asyncio.sleep(0.25)
            return "字" * 2000, [], {}
        finally:
            ticker_task.cancel()
            await asyncio.gather(ticker_task, return_exceptions=True)
            self.stopped.set()


def install_slow_store(app, engine):
    manager = app.state.runs
    checks = []
    writes = []
    original_check, original_emit = manager.check, manager.emit

    def check(*args):
        assert threading.get_ident() != engine.thread
        checks.append(True)
        time.sleep(0.03)
        return original_check(*args)

    def emit(*args):
        if engine.thread is not None:
            assert threading.get_ident() != engine.thread
        writes.append(args[1])
        time.sleep(0.03)
        return original_emit(*args)

    manager.check, manager.emit = check, emit
    manager.engine = engine
    return checks, writes


def test_burst_aggregates_db_access_and_does_not_block_event_loop(client, app):
    engine = Burst()
    checks, writes = install_slow_store(app, engine)
    rid = start(client)
    assert wait(client, rid)["status"] == "completed"
    assert len(checks) < 10  # Previously at least 2000 synchronous validations.
    assert len(writes) < 20
    assert engine.ticks >= 8
    with app.state.db() as db:
        events = list(
            db.scalars(
                select(Event)
                .where(Event.run_id == rid, Event.kind == "answer.delta")
                .order_by(Event.id)
            )
        )
        assert "".join(e.payload["text"] for e in events) == "字" * 2000
        usage = db.get(Run, rid).usage["runtime"]
        assert usage["output_chunks"] == 2000 and usage["db_wait_ms"] > 0


def test_busy_sdk_queue_still_honors_timeout(client, app):
    engine = Burst(forever=True)
    install_slow_store(app, engine)
    app.state.config.runtime.run_timeout_seconds = 0.25
    rid = start(client)
    result = wait(client, rid)
    assert result["status"] == "failed"
    assert "超时" in result["error"]
    assert engine.stopped.wait(1)


def test_stop_during_burst_does_not_become_completed(client, app):
    engine = Burst(forever=True)
    install_slow_store(app, engine)
    rid = start(client)
    for _ in range(100):
        if engine.thread is not None:
            break
        time.sleep(0.01)
    assert (
        client.post("/api/runs/" + rid + "/cancel", headers=headers(client)).status_code
        == 200
    )
    assert engine.stopped.wait(2)
    assert wait(client, rid)["status"] == "cancelled"


def test_sse_database_sessions_are_opened_in_worker_threads(client, app):
    rid = start(client)
    assert wait(client, rid)["status"] == "completed"
    original = app.state.db

    def factory(*args, **kwargs):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise AssertionError("SSE database session opened on event loop")
        time.sleep(0.01)
        return original(*args, **kwargs)

    app.state.db = factory
    response = client.get("/api/runs/" + rid + "/events")
    assert response.status_code == 200 and "stream.closed" in response.text
