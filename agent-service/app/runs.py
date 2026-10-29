"""Async execution with bounded output batches and worker-owned database sessions."""

import asyncio
import time
from uuid import uuid4
from .errors import AppError
from .agent_engine import AgentEngine
from .progress import RunProgress
from .run_store import RunStore
from .tool_catalog import DISCOVERY_NAME, discover


class RunManager:
    def __init__(self, config, db, platform, engine=None):
        self.config, self.db, self.platform = config, db, platform
        self.store = RunStore(config, db)
        self.engine = engine or AgentEngine(config)
        self.tasks = {}
        self.lock = asyncio.Lock()

    def emit(self, *args):
        return self.store.emit(*args)

    def check(self, run_id):
        return self.store.check(run_id)

    def start(self, run_id):
        task = asyncio.create_task(self._run(run_id))
        self.tasks[run_id] = task
        task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    async def stop(self, run_id):
        if task := self.tasks.get(run_id):
            task.cancel()
        await asyncio.to_thread(self.store.stop, run_id)

    async def shutdown(self):
        for task in list(self.tasks.values()):
            task.cancel()
        await asyncio.gather(*list(self.tasks.values()), return_exceptions=True)

    async def _run(self, run_id):
        parts, pending = [], []
        pending_chars = 0
        last_check = 0.0
        started_at = time.monotonic()
        first_output = None
        chunks = 0
        db_wait_ms = 0.0
        tool_count = 0
        discovery_count = 0
        tool_lock, io_lock, flush_lock = asyncio.Lock(), asyncio.Lock(), asyncio.Lock()

        async def io(function, *args):
            # Retain serialization until an in-flight worker finishes even on cancellation.
            # A worker owns its entire SQLAlchemy session; no session crosses threads.
            nonlocal db_wait_ms
            async with io_lock:
                began = time.monotonic()
                task = asyncio.create_task(asyncio.to_thread(function, *args))
                try:
                    return await asyncio.shield(task)
                except asyncio.CancelledError:
                    await asyncio.gather(task, return_exceptions=True)
                    raise
                finally:
                    db_wait_ms += (time.monotonic() - began) * 1000

        async def emit(kind, payload):
            return await io(self.emit, run_id, kind, payload)

        async def progress_emit(key, kind, payload):
            return await emit(kind, payload)

        async def flush():
            nonlocal pending, pending_chars, last_check
            async with flush_lock:
                if time.monotonic() - last_check >= 1:
                    await io(self.check, run_id)
                    last_check = time.monotonic()
                if pending:
                    batch = "".join(pending)
                    pending, pending_chars = [], 0
                    await emit("answer.delta", {"text": batch})

        progress = RunProgress(run_id, progress_emit, flush)

        async def delta(text):
            nonlocal pending_chars, first_output, chunks
            chunks += 1
            if first_output is None:
                first_output = time.monotonic() - started_at
            parts.append(text)
            pending.append(text)
            pending_chars += len(text)
            if progress.stage != "model_output":
                await progress.phase("model_output")
            if pending_chars >= 4096:
                await flush()
            # Queue-fed SDK streams may have thousands of immediately available chunks.
            # Yield explicitly so cancellation, heartbeat and timeout callbacks can run.
            await asyncio.sleep(0)

        try:
            prepared = await io(self.store.prepare, run_id)
            if prepared is None:
                return
            history, message, business, sid, cid, context = prepared
            await emit("run.started", context)
            await progress.start()

            async def invoke(name, args):
                nonlocal tool_count, discovery_count
                async with tool_lock:
                    await io(self.check, run_id)
                    tool_count += 1
                    if tool_count > self.config.runtime.max_tool_calls:
                        raise AppError(
                            "TOOL_LIMIT", "工具调用次数已达上限，请缩小问题范围"
                        )
                    call_id, started = str(uuid4()), time.monotonic()
                    await io(self.store.start_tool, call_id, run_id, name, args)
                    await flush()
                    await progress.phase("tool_running")
                    await emit("tool.started", {"tool_call_id": call_id, "name": name})
                    status = "completed"
                    try:
                        if name == DISCOVERY_NAME:
                            discovery_count += 1
                            if discovery_count > self.config.runtime.max_discovery_calls:
                                status = "failed"
                                result = {"ok": False, "error": "DISCOVERY_LIMIT",
                                          "message": "工具发现次数已达上限，请使用已加载工具或拆分问题"}
                            else:
                                result = discover(args)
                        else:
                            result = await asyncio.to_thread(
                                self.platform.execute,
                                sid,
                                run_id,
                                business,
                                name,
                                args,
                                call_id,
                            )
                        await io(self.check, run_id)
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
                        await io(
                            self.store.end_tool,
                            call_id,
                            status,
                            int((time.monotonic() - started) * 1000),
                        )
                    await emit(
                        "tool.completed",
                        {"tool_call_id": call_id, "name": name, "status": status},
                    )
                    await progress.phase("model_waiting")
                    return result

            async with asyncio.timeout(self.config.runtime.run_timeout_seconds):
                engine_task = asyncio.create_task(
                    self.engine.run(
                        history,
                        message,
                        context,
                        invoke,
                        delta,
                        progress=progress.phase,
                    )
                )
                try:
                    done, _ = await asyncio.wait(
                        (engine_task, progress.task),
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if progress.task in done:
                        # Propagate periodic session expiry / database failure even if the
                        # model is waiting silently; never leave an unobserved monitor error.
                        progress.task.result()
                        raise RuntimeError("progress monitor ended unexpectedly")
                    final, items, usage = engine_task.result()
                    await progress.close()
                    await flush()
                    await io(self.check, run_id)
                finally:
                    if not engine_task.done():
                        engine_task.cancel()
                    await asyncio.gather(engine_task, return_exceptions=True)
            usage = dict(usage)
            usage["runtime"] = {
                "first_output_seconds": round(first_output, 3)
                if first_output is not None
                else None,
                "elapsed_seconds": round(time.monotonic() - started_at, 3),
                "db_wait_ms": round(db_wait_ms, 1),
                "output_chunks": chunks,
            }
            presentation = await io(
                self.store.complete, run_id, cid, final, items, usage
            )
            await emit(
                "run.completed",
                {"answer": final, "usage": usage, "parts": presentation},
            )
        except BaseException as exc:
            if not isinstance(exc, (Exception, asyncio.CancelledError)):
                raise
            await progress.close()
            cancelled = (
                isinstance(exc, asyncio.CancelledError)
                or isinstance(exc, AppError)
                and exc.code == "RUN_CANCELLED"
            )
            status = "cancelled" if cancelled else "failed"
            message = (
                "运行已停止"
                if cancelled
                else "运行超时，请缩小查询范围"
                if isinstance(exc, TimeoutError)
                else exc.message
                if isinstance(exc, AppError)
                else "Agent 请求失败，请检查模型配置、接口兼容性和网络"
            )
            answer = "".join(parts)
            status, message, presentation = await io(
                self.store.fail, run_id, status, message, answer
            )
            await emit(
                "run.cancelled" if status == "cancelled" else "run.failed",
                {"message": message, "answer": answer, "parts": presentation},
            )
        finally:
            await progress.close()
