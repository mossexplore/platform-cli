import asyncio
import json
from uuid import UUID
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, delete
from .models import Conversation, Message, Run, Event, ToolCall, now
from .sessions import request_session, valid, protect, TERMINAL
from .errors import AppError
from .sanitize import clean
from .presentation import message_parts

router = APIRouter(prefix="/api")


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=16000)
    client_message_id: UUID


class RenameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)


@router.patch("/conversations/{key}")
def rename_conversation(key: str, body: RenameInput, request: Request):
    title = body.title.strip()
    if not title:
        raise AppError("EMPTY_TITLE", "请输入对话名称")
    with request.app.state.db() as db:
        s = request_session(request, db)
        protect(request, s)
        c = conversation(db, s, key)
        c.title = title
        db.commit()
        return {"id": c.id, "title": c.title}


@router.delete("/conversations/{key}")
async def delete_conversation(key: str, request: Request):
    state = request.app.state
    # Serialize with run creation so no new writer can start during deletion.
    async with state.runs.lock:
        with state.db() as db:
            s = request_session(request, db)
            protect(request, s)
            conversation(db, s, key)
            if db.scalar(select(Run.id).where(
                Run.conversation_id == key, Run.status.in_(["queued", "running"])
            )):
                raise AppError("RUN_ACTIVE", "请先停止该对话的当前执行，再删除对话", 409)
            ids = select(Run.id).where(Run.conversation_id == key)
            db.execute(delete(Event).where(Event.run_id.in_(ids)))
            db.execute(delete(ToolCall).where(ToolCall.run_id.in_(ids)))
            db.execute(delete(Message).where(Message.conversation_id == key))
            db.execute(delete(Run).where(Run.conversation_id == key))
            db.execute(delete(Conversation).where(Conversation.id == key))
            db.commit()
    return {"ok": True}


def conversation(db, s, key):
    c = db.get(Conversation, key)
    if not c or c.user_id != s.user_id or c.environment_id != s.environment_id:
        raise AppError("NOT_FOUND", "对话不存在", 404)
    return c


def message_timestamp(db, run_id, role):
    value = db.scalar(
        select(Message.created_at)
        .where(Message.run_id == run_id, Message.role == role)
        .order_by(Message.id.desc())
        .limit(1)
    )
    return value.isoformat() + "Z" if value else None


def run_owned(db, s, key):
    r = db.get(Run, key)
    if not r or r.session_id != s.id:
        raise AppError("NOT_FOUND", "运行不存在", 404)
    return r


@router.get("/conversations")
def conversations(request: Request, offset: int = Query(0, ge=0)):
    with request.app.state.db() as db:
        s = request_session(request, db)
        rows = db.scalars(
            select(Conversation)
            .where(
                Conversation.user_id == s.user_id,
                Conversation.environment_id == s.environment_id,
            )
            .order_by(Conversation.updated_at.desc())
            .offset(offset)
            .limit(50)
        )
        return [
            {
                "id": c.id,
                "title": c.title,
                "business": c.business,
                "updated_at": c.updated_at.isoformat() + "Z",
            }
            for c in rows
        ]


@router.post("/conversations", status_code=201)
def create_conversation(request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        protect(request, s)
        if s.status != "ready" or not s.business:
            raise AppError("BUSINESS_REQUIRED", "请先选择业务", 409)
        c = Conversation(
            user_id=s.user_id, environment_id=s.environment_id, business=s.business
        )
        s.last_activity = now()
        db.add(c)
        db.commit()
        return {"id": c.id, "title": c.title, "business": c.business}


@router.get("/conversations/{key}")
def get_conversation(key: str, request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        c = conversation(db, s, key)
        return {"id": c.id, "title": c.title, "business": c.business}


@router.get("/conversations/{key}/messages")
def messages(key: str, request: Request, before: int | None = Query(None, ge=1)):
    with request.app.state.db() as db:
        s = request_session(request, db)
        conversation(db, s, key)
        query = select(Message).where(Message.conversation_id == key)
        if before:
            query = query.where(Message.id < before)
        rows = list(db.scalars(query.order_by(Message.id.desc()).limit(50)))
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "created_at": m.created_at.isoformat() + "Z",
                "status": m.status,
                "run_id": m.run_id,
                "parts": message_parts(db, db.get(Run, m.run_id))
                if m.role == "assistant"
                else [],
            }
            for m in reversed(rows)
        ]


@router.post("/conversations/{key}/runs", status_code=202)
async def create_run(key: str, body: Input, request: Request):
    state = request.app.state
    if not body.message.strip():
        raise AppError("EMPTY_MESSAGE", "请输入问题")
    async with state.runs.lock:
        with state.db() as db:
            s = request_session(request, db)
            protect(request, s)
            c = conversation(db, s, key)
            if s.status != "ready" or not s.business or s.business != c.business:
                raise AppError("BUSINESS_REQUIRED", "请先选择该对话对应业务", 409)
            existing = db.scalar(
                select(Run).where(
                    Run.conversation_id == key,
                    Run.client_message_id == str(body.client_message_id),
                )
            )
            if existing:
                return {
                    "run_id": existing.id,
                    "status": existing.status,
                    "created_at": message_timestamp(db, existing.id, "user"),
                }
            if db.scalar(
                select(Run.id).where(
                    Run.session_id == s.id, Run.status.in_(["queued", "running"])
                )
            ):
                raise AppError("RUN_ACTIVE", "当前查询尚未结束", 409)
            message = clean(body.message.strip())
            r = Run(
                session_id=s.id,
                conversation_id=key,
                client_message_id=str(body.client_message_id),
            )
            db.add(r)
            db.flush()
            db.add(
                Message(conversation_id=key, run_id=r.id, role="user", content=message)
            )
            if c.title == "新对话":
                c.title = message[:60]
            c.updated_at = s.last_activity = now()
            db.commit()
            state.runs.start(r.id)
            return {
                "run_id": r.id,
                "status": r.status,
                "created_at": message_timestamp(db, r.id, "user"),
            }


@router.get("/runs/{key}")
def status(key: str, request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        r = run_owned(db, s, key)
        return {
            "id": r.id,
            "status": r.status,
            "answer": r.answer,
            "created_at": message_timestamp(db, r.id, "assistant"),
            "error": r.error,
            "parts": message_parts(db, r) if r.status in TERMINAL else [],
        }


@router.post("/runs/{key}/cancel")
async def cancel(key: str, request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        protect(request, s)
        run_owned(db, s, key)
    await request.app.state.runs.stop(key)
    return {"ok": True}


@router.get("/runs/{key}/events")
async def events(key: str, request: Request):
    state = request.app.state

    def owner():
        with state.db() as db:
            s = request_session(request, db)
            run_owned(db, s, key)
            return s.id

    sid = await asyncio.to_thread(owner)

    def read_batch(after):
        with state.db() as db:
            valid(db, state.config, sid)
            r = db.get(Run, key)
            if r is None:
                raise AppError("NOT_FOUND", "对话已删除", 404)
            rows = list(
                db.scalars(
                    select(Event)
                    .where(Event.run_id == key, Event.id > after)
                    .order_by(Event.id)
                    .limit(100)
                )
            )
            return (
                r.status,
                r.answer,
                r.error,
                message_timestamp(db, r.id, "assistant") if r.status in TERMINAL else None,
                message_parts(db, r) if r.status in TERMINAL else [],
                [(e.id, e.kind, e.payload) for e in rows],
            )

    try:
        cursor = max(0, int(request.headers.get("last-event-id", "0")))
    except ValueError:
        raise AppError("INVALID_CURSOR", "事件游标无效")

    async def stream():
        nonlocal cursor
        heartbeat = 0
        while not await request.is_disconnected():
            try:
                status, answer, error, created_at, parts, batch = await asyncio.to_thread(
                    read_batch, cursor
                )
            except AppError as error:
                if error.code == "NOT_FOUND":
                    yield 'event: stream.closed\ndata: {"status":"cancelled","message":"对话已删除"}\n\n'
                    return
                yield 'event: auth.expired\ndata: {"message":"登录已失效"}\n\n'
                return
            terminal = status in TERMINAL
            for event_id, kind, payload in batch:
                cursor = event_id
                if kind in {"run.completed", "run.failed", "run.cancelled"}:
                    payload = {**payload, "created_at": created_at}
                yield f"id: {cursor}\nevent: {kind}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if terminal and len(batch) < 100:
                yield (
                    "event: stream.closed\ndata: "
                    + json.dumps(
                        {
                            "status": status,
                            "created_at": created_at,
                            "answer": answer,
                            "message": error,
                            "parts": parts,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
                return
            heartbeat += 1
            if heartbeat % 40 == 0:
                yield ": heartbeat\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
