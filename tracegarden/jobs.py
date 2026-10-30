"""Bounded, cancellable tracing in disposable CPU worker processes."""

from __future__ import annotations
import asyncio
import multiprocessing as mp
import time
import uuid
from dataclasses import dataclass, field


def _worker(connection, data, config):
    try:
        from .core import trace, Options

        connection.send({"result": trace(data, Options.model_validate(config))})
    except BaseException as exc:
        connection.send({"error": str(exc) or type(exc).__name__})
    finally:
        connection.close()


@dataclass
class Job:
    id: str
    state: str = "queued"
    created: float = field(default_factory=time.monotonic)
    result: dict | None = None
    error: str | None = None
    process: object | None = None
    task: asyncio.Task | None = None
    bytes: int = 0

    def public(self):
        return {
            "id": self.id,
            "state": self.state,
            "result": self.result,
            "error": self.error,
        }


class JobManager:
    def __init__(self, timeout=120):
        self.jobs = {}
        self.gate = asyncio.Semaphore(1)
        self.timeout = timeout

    def prune(self):
        for ident, job in list(self.jobs.items()):
            if (
                job.state not in {"queued", "running"}
                and time.monotonic() - job.created > 600
            ):
                self.jobs.pop(ident, None)

    def submit(self, data, options):
        self.prune()
        if (
            len(self.jobs) >= 20
            or sum(j.bytes for j in self.jobs.values()) + len(data) > 100 * 1024 * 1024
        ):
            raise ValueError("Job queue is full. Finish or clear existing jobs first.")
        job = Job(uuid.uuid4().hex, bytes=len(data))
        self.jobs[job.id] = job
        job.task = asyncio.create_task(self._run(job, data, options.model_dump()))
        return job

    async def _run(self, job, data, options):
        parent = None
        child = None
        try:
            async with self.gate:
                if job.state == "cancelled":
                    return
                parent, child = mp.get_context("spawn").Pipe(duplex=False)
                process = mp.get_context("spawn").Process(
                    target=_worker, args=(child, data, options), daemon=True
                )
                job.process = process
                job.state = "running"
                process.start()
                child.close()
                started = time.monotonic()
                while job.state == "running":
                    if parent.poll():
                        payload = await asyncio.to_thread(parent.recv)
                        job.result = payload.get("result")
                        job.error = payload.get("error")
                        job.state = "failed" if job.error else "complete"
                        break
                    if not process.is_alive():
                        job.state = "failed"
                        job.error = "The tracing worker stopped unexpectedly."
                        break
                    if time.monotonic() - started > self.timeout:
                        job.state = "failed"
                        job.error = "Tracing exceeded the time limit. Reduce image size or detail."
                        break
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            job.state = "cancelled"
        except Exception as exc:
            job.state = "failed"
            job.error = str(exc)
        finally:
            process = job.process
            if process:
                if process.is_alive():
                    process.terminate()
                await asyncio.to_thread(process.join, 2)
                if process.is_alive():
                    process.kill()
                    await asyncio.to_thread(process.join, 1)
                process.close()
                job.process = None
            if parent:
                parent.close()
            if child:
                child.close()
            job.bytes = 0

    def cancel(self, ident):
        job = self.jobs[ident]
        if job.state in {"queued", "running"}:
            job.state = "cancelled"
            if job.task:
                job.task.cancel()
        return job

    async def close(self):
        for ident in list(self.jobs):
            self.cancel(ident)
        await asyncio.gather(
            *(j.task for j in self.jobs.values() if j.task), return_exceptions=True
        )
