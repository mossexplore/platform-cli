"""Build a durable ordered view of public text and tool steps, without model internals."""

from sqlalchemy import select
from .models import Event, ToolCall


def message_parts(db, run, answer=None):
    if "presentation" in run.usage:
        return run.usage["presentation"]
    blocks = []
    tools = {}
    rows = db.scalars(
        select(Event)
        .where(
            Event.run_id == run.id,
            Event.kind.in_(["answer.delta", "tool.started", "tool.completed"]),
        )
        .order_by(Event.id)
    )
    for event in rows:
        p = event.payload
        if event.kind == "answer.delta":
            if not blocks or blocks[-1]["type"] != "text":
                blocks.append({"type": "text", "content": ""})
            blocks[-1]["content"] += p.get("text", "")
        elif event.kind == "tool.started":
            block = {
                "type": "tool",
                "id": p["tool_call_id"],
                "name": p["name"],
                "status": "running",
            }
            tools[block["id"]] = block
            blocks.append(block)
        elif p.get("tool_call_id") in tools:
            tools[p["tool_call_id"]]["status"] = p["status"]
    for call in db.scalars(select(ToolCall).where(ToolCall.run_id == run.id)):
        if call.id in tools:
            tools[call.id]["status"] = call.status
            tools[call.id]["duration_ms"] = call.duration_ms
    final = run.answer if answer is None else answer
    combined = "".join(b["content"] for b in blocks if b["type"] == "text")
    if final and final != combined:
        if not blocks or blocks[-1]["type"] != "text":
            blocks.append({"type": "text", "content": ""})
        if final.startswith(combined):
            blocks[-1]["content"] += final[len(combined) :]
        else:
            blocks[-1]["content"] = final
    return blocks
