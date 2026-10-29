"""Public execution progress, never private model reasoning or tool arguments."""

import asyncio
import logging
import time

log = logging.getLogger("uvicorn.error.agent_progress")


class RunProgress:
    def __init__(self, run_id, emit, flush):
        self.run_id, self.emit, self.flush = run_id, emit, flush
        self.started = time.monotonic()
        self.last_report = self.started
        self.stage = "model_waiting"
        self.model_requests = 0
        self.task = None

    async def report(self):
        elapsed = int(time.monotonic() - self.started)
        await self.emit(
            self.run_id,
            "run.progress",
            {
                "stage": self.stage,
                "elapsed_seconds": elapsed,
                "model_requests": self.model_requests,
            },
        )
        log.info(
            "run=%s stage=%s elapsed_seconds=%s model_requests=%s",
            self.run_id,
            self.stage,
            elapsed,
            self.model_requests,
        )
        self.last_report = time.monotonic()

    async def phase(self, stage):
        if stage == "model_request":
            self.model_requests += 1
            stage = "model_waiting"
        if stage != self.stage or stage == "model_waiting":
            self.stage = stage
            await self.report()

    async def pulse(self):
        while True:
            await asyncio.sleep(0.2)
            await self.flush()
            if time.monotonic() - self.last_report >= 5:
                await self.report()

    async def start(self):
        await self.report()
        self.task = asyncio.create_task(self.pulse())

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
