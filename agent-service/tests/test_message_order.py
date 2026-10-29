import json
from sqlalchemy import delete
from app.models import Event
from conftest import ready, headers
from test_runs import wait


class Narrative:
    async def run(self, history, message, context, invoke, delta, progress=None):
        await delta("先查询模型。")
        await invoke("list_models", {"page": 1, "page_size": 1})
        await delta("已查到模型，再核对一次。")
        await invoke("list_models", {"page": 1, "page_size": 1})
        await delta("最终")
        await delta("结果。")
        return "最终结果。", [], {}


def test_public_message_order_survives_terminal_event_history_and_event_cleanup(
    client, app
):
    ready(client)
    app.state.runs.engine = Narrative()
    cid = client.post("/api/conversations", headers=headers(client)).json()["id"]
    rid = client.post(
        f"/api/conversations/{cid}/runs",
        headers=headers(client),
        json={
            "message": "查询模型",
            "client_message_id": "00000000-0000-0000-0000-000000000002",
        },
    ).json()["run_id"]
    result = wait(client, rid)
    assert result["status"] == "completed"
    parts = result["parts"]
    assert [p["type"] for p in parts] == ["text", "tool", "text", "tool", "text"]
    assert [p["content"] for p in parts if p["type"] == "text"] == [
        "先查询模型。",
        "已查到模型，再核对一次。",
        "最终结果。",
    ]
    assert all(p["status"] == "completed" for p in parts if p["type"] == "tool")
    assert result["answer"] == "最终结果。"
    assistant = client.get(f"/api/conversations/{cid}/messages").json()[-1]
    assert assistant["parts"] == parts
    stream = client.get("/api/runs/" + rid + "/events").text
    completed = stream.split("event: run.completed\ndata: ")[1].split("\n\n")[0]
    assert json.loads(completed)["parts"] == parts
    with app.state.db() as db:
        db.execute(delete(Event).where(Event.run_id == rid))
        db.commit()
    assert client.get("/api/runs/" + rid).json()["parts"] == parts
    assert client.get(f"/api/conversations/{cid}/messages").json()[-1]["parts"] == parts
    replay = client.get("/api/runs/" + rid + "/events").text
    assert (
        json.loads(replay.split("event: stream.closed\ndata: ")[1].split("\n\n")[0])[
            "parts"
        ]
        == parts
    )
