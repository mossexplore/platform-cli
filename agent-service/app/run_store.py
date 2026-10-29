"""Synchronous transactions; callers must run them in a worker thread."""

import json
from sqlalchemy import select, update
from .models import Run, Event, Message, Conversation, ToolCall, now
from .sessions import valid, TERMINAL
from .sanitize import clean
from .errors import AppError
from .presentation import message_parts


class RunStore:
    def __init__(self, config, db):
        self.config, self.db = config, db

    def emit(self, run_id, kind, payload):
        with self.db() as db:
            event = Event(run_id=run_id, kind=kind, payload=clean(payload))
            db.add(event)
            db.commit()
            return event.id

    def check(self, run_id):
        with self.db() as db:
            r = db.get(Run, run_id)
            if not r or r.status != "running":
                raise AppError("RUN_CANCELLED", "运行已停止", 409)
            valid(db, self.config, r.session_id)

    def prepare(self, run_id):
        with self.db() as db:
            r = db.get(Run, run_id)
            if r.status != "queued":
                return None
            s = valid(db, self.config, r.session_id)
            r.status = "running"
            c = db.get(Conversation, r.conversation_id)
            message = db.scalar(
                select(Message).where(Message.run_id == r.id, Message.role == "user")
            ).content
            previous = list(
                db.scalars(
                    select(Run)
                    .where(
                        Run.conversation_id == c.id,
                        Run.status == "completed",
                        Run.id != r.id,
                    )
                    .order_by(Run.created_at.desc())
                    .limit(self.config.runtime.max_history_messages // 2)
                )
            )
            history = []
            chars = 0
            for old in previous:
                size = len(json.dumps(old.history, ensure_ascii=False))
                if chars + size > self.config.runtime.max_history_chars:
                    break
                history = old.history + history
                chars += size
            business, sid, cid = c.business, s.id, c.id
            context = {
                "environment": s.environment_id,
                "business": business.get("team_name") or business["tenant_name"],
                "business_id": business["businessId"],
            }
            db.commit()
        return history, message, business, sid, cid, context

    def complete(self, run_id, cid, final, items, usage):
        with self.db() as db:
            r = db.scalar(select(Run).where(Run.id == run_id).with_for_update())
            valid(db, self.config, r.session_id)
            if r.status != "running":
                raise AppError("RUN_CANCELLED", "运行已停止", 409)
            r.status, r.answer, r.history, r.usage = (
                "completed",
                clean(final),
                clean(items),
                dict(usage),
            )
            r.usage = {**r.usage, "presentation": message_parts(db, r, clean(final))}
            db.add(
                Message(
                    conversation_id=cid,
                    run_id=run_id,
                    role="assistant",
                    content=clean(final),
                )
            )
            db.get(Conversation, cid).updated_at = now()
            db.commit()
            return r.usage["presentation"]

    def fail(self, run_id, status, message, answer):
        with self.db() as db:
            r = db.get(Run, run_id)
            if r:
                if r.status == "cancelled":
                    status, message = "cancelled", "运行已停止"
                r.status, r.error, r.answer = status, message, clean(answer)
                db.add(
                    Message(
                        conversation_id=r.conversation_id,
                        run_id=r.id,
                        role="assistant",
                        content=clean(answer),
                        status=status,
                    )
                )
                db.execute(
                    update(ToolCall)
                    .where(ToolCall.run_id == run_id, ToolCall.status == "running")
                    .values(status=status)
                )
                db.flush()
                r.usage = {
                    **r.usage,
                    "presentation": message_parts(db, r, clean(answer)),
                }
                db.commit()
                return status, message, r.usage["presentation"]
        return status, message, []

    def start_tool(self, call_id, run_id, name, args):
        with self.db() as db:
            db.add(
                ToolCall(
                    id=call_id,
                    run_id=run_id,
                    name=name,
                    arguments=clean(args),
                    status="running",
                    request_id=call_id,
                )
            )
            db.commit()

    def end_tool(self, call_id, status, duration):
        with self.db() as db:
            call = db.get(ToolCall, call_id)
            if call:
                call.status, call.duration_ms = status, duration
                db.commit()

    def stop(self, run_id):
        with self.db() as db:
            r = db.get(Run, run_id)
            if r and r.status not in TERMINAL:
                r.status = "cancelled"
                db.commit()
