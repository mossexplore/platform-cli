"""Bounded single-process execution with persisted events and cancellation fences."""

import asyncio
import json
import time
from uuid import uuid4
from sqlalchemy import select, update
from .models import Run, Event, Message, Conversation, ToolCall, now
from .sessions import valid, TERMINAL
from .sanitize import clean
from .errors import AppError
from .agent_engine import AgentEngine


class RunManager:
    def __init__(self, config, db, platform, engine=None):
        self.config, self.db, self.platform = config, db, platform
        self.engine = engine or AgentEngine(config)
        self.tasks = {}
        self.lock = asyncio.Lock()

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

    def start(self, run_id):
        task = asyncio.create_task(self._run(run_id))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def stop(self, run_id):
        with self.db() as db:
            r = db.get(Run, run_id)
            if r and r.status not in TERMINAL:
                r.status = "cancelled"
                db.commit()
        if task := self.tasks.get(run_id):
            task.cancel()

    async def shutdown(self):
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    async def _run(self, run_id):
        answer = ""
        buffer = ""
        last_flush = time.monotonic()
        tool_count = 0
        tool_lock = asyncio.Lock()

        async def delta(text):
            nonlocal answer, buffer, last_flush
            self.check(run_id)
            answer += text
            buffer += text
            if len(buffer) >= 120 or time.monotonic() - last_flush >= 0.15:
                self.emit(run_id, "answer.delta", {"text": buffer})
                buffer = ""
                last_flush = time.monotonic()

        try:
            with self.db() as db:
                r = db.get(Run, run_id)
                if r.status != "queued":
                    return
                s = valid(db, self.config, r.session_id)
                r.status = "running"
                c = db.get(Conversation, r.conversation_id)
                message = db.scalar(
                    select(Message).where(
                        Message.run_id == r.id, Message.role == "user"
                    )
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
            self.emit(run_id, "run.started", context)

            async def invoke(name, args):
                nonlocal tool_count
                async with tool_lock:
                    self.check(run_id)
                    tool_count += 1
                    if tool_count > self.config.runtime.max_tool_calls:
                        raise AppError(
                            "TOOL_LIMIT", "工具调用次数已达上限，请缩小问题范围"
                        )
                    call_id, started = str(uuid4()), time.monotonic()
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
                    self.emit(
                        run_id, "tool.started", {"tool_call_id": call_id, "name": name}
                    )
                    status = "completed"
                    try:
                        result = await asyncio.to_thread(
                            self.platform.execute,
                            sid,
                            run_id,
                            business,
                            name,
                            args,
                            call_id,
                        )
                        self.check(run_id)
                    except asyncio.CancelledError:
                        status = "cancelled"
                        raise
                    except AppError:
                        status = "failed"
                        raise
                    except Exception:
                        status = "failed"
                        result = {
                            "ok": False,
                            "error": {
                                "code": "PLATFORM_QUERY_FAILED",
                                "message": "平台查询未成功，请核对参数或缩小范围后重试",
                            },
                        }
                    finally:
                        with self.db() as db:
                            call = db.get(ToolCall, call_id)
                            call.status, call.duration_ms = (
                                status,
                                int((time.monotonic() - started) * 1000),
                            )
                            db.commit()
                    self.emit(
                        run_id,
                        "tool.completed",
                        {"tool_call_id": call_id, "name": name, "status": status},
                    )
                    return result

            async with asyncio.timeout(self.config.runtime.run_timeout_seconds):
                final, items, usage = await self.engine.run(
                    history, message, context, invoke, delta
                )
            self.check(run_id)
            with self.db() as db:
                r = db.get(Run, run_id)
                if r.status != "running":
                    raise AppError("RUN_CANCELLED", "运行已停止", 409)
                r.status, r.answer, r.history, r.usage = (
                    "completed",
                    clean(final),
                    clean(items),
                    usage,
                )
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
            if buffer:
                self.emit(run_id, "answer.delta", {"text": buffer})
            self.emit(run_id, "run.completed", {"answer": clean(final), "usage": usage})
        except BaseException as exc:
            if not isinstance(exc, (Exception, asyncio.CancelledError)):
                raise
            cancelled = (
                isinstance(exc, asyncio.CancelledError)
                or isinstance(exc, AppError)
                and exc.code == "RUN_CANCELLED"
            )
            status = "cancelled" if cancelled else "failed"
            message = (
                "运行已停止"
                if cancelled
                else (
                    "运行超时，请缩小查询范围"
                    if isinstance(exc, TimeoutError)
                    else exc.message
                    if isinstance(exc, AppError)
                    else "Agent 请求失败，请检查模型配置、接口兼容性和网络"
                )
            )
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
                    db.commit()
            self.emit(
                run_id,
                "run.cancelled" if status == "cancelled" else "run.failed",
                {"message": message, "answer": clean(answer)},
            )
