import asyncio
import time
from sqlalchemy import select
from app.models import Event
from conftest import ready, headers
from test_runs import wait


class PausedOutput:
    async def run(self, history, message, context, invoke, delta, progress=None):
        await progress("model_request")
        await delta("少量文字")
        await asyncio.sleep(1)
        return "少量文字", [], {}


def test_short_output_flushes_while_model_is_still_waiting(client, app):
    ready(client)
    app.state.runs.engine = PausedOutput()
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    rid = client.post(
        f"/api/conversations/{cid}/runs",
        headers=headers(client),
        json={
            "message": "查询",
            "client_message_id": "00000000-0000-0000-0000-000000000001",
        },
    ).json()["run_id"]
    for _ in range(60):
        with app.state.db() as db:
            delta = db.scalar(
                select(Event).where(Event.run_id == rid, Event.kind == "answer.delta")
            )
        if delta:
            break
        time.sleep(0.01)
    assert delta and delta.payload["text"] == "少量文字"
    assert client.get("/api/runs/" + rid).json()["status"] == "running"
    assert wait(client, rid)["status"] == "completed"
    with app.state.db() as db:
        events = list(
            db.scalars(
                select(Event).where(Event.run_id == rid, Event.kind == "run.progress")
            )
        )
    assert any(e.payload["model_requests"] == 1 for e in events)
    assert any(e.payload["stage"] == "model_output" for e in events)
    assert all(
        set(e.payload) == {"stage", "elapsed_seconds", "model_requests"} for e in events
    )


async def test_progress_closes_heartbeat_task():
    from app.progress import RunProgress

    events = []
    flushed = []
    p = RunProgress(
        "run", lambda *args: events.append(args), lambda: flushed.append(True)
    )
    p.start()
    await p.phase("model_request")
    await p.phase("tool_running")
    await asyncio.sleep(0.22)
    await p.close()
    assert flushed and p.task.done()
    count = len(events)
    await asyncio.sleep(0.22)
    assert len(events) == count
