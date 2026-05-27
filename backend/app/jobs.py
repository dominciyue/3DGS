"""Job store: lifecycle, persistence, a background worker per job, and SSE pub/sub.

The reconstruction pipeline is blocking (subprocess, file IO), so each job runs in a
worker thread via ``asyncio.to_thread``. Events emitted from that thread are delivered
to SSE subscribers on the event loop using ``call_soon_threadsafe``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from .agent import get_planner
from .config import Settings
from .config import settings as default_settings
from .models import Event, Job, JobStatus
from .pipeline.runner import PipelineRunner
from .pipeline.stages import CancelledError

log = logging.getLogger(__name__)

TERMINAL = {JobStatus.done, JobStatus.failed, JobStatus.cancelled}


class JobStore:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or default_settings
        self.settings.ensure_dirs()
        self._jobs: dict[str, Job] = {}
        self._events: dict[str, list[Event]] = {}
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._cancelled: set[str] = set()
        self._tasks: dict[str, asyncio.Task] = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._load_persisted()

    # --- paths ---------------------------------------------------------------
    def job_dir(self, job_id: str) -> Path:
        return self.settings.jobs_dir / job_id

    def result_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "result" / "model.ply"

    # --- persistence ---------------------------------------------------------
    def _persist(self, job: Job) -> None:
        (self.job_dir(job.id)).mkdir(parents=True, exist_ok=True)
        (self.job_dir(job.id) / "job.json").write_text(job.model_dump_json(indent=2))

    def _load_persisted(self) -> None:
        if not self.settings.jobs_dir.exists():
            return
        for jd in self.settings.jobs_dir.iterdir():
            rec = jd / "job.json"
            if rec.is_file():
                try:
                    job = Job.model_validate_json(rec.read_text())
                    # mark interrupted (server restarted mid-run) jobs as failed
                    if job.status not in TERMINAL:
                        job.status = JobStatus.failed
                        job.error = "interrupted by server restart"
                    self._jobs[job.id] = job
                    self._events.setdefault(job.id, [])
                except Exception as exc:  # noqa: BLE001
                    log.warning("could not load job %s: %s", jd.name, exc)

    # --- queries -------------------------------------------------------------
    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list(self) -> list[Job]:
        return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    # --- event delivery (called from worker thread) -------------------------
    def _deliver(self, event: Event, final: bool) -> None:
        self._events.setdefault(event.job_id, []).append(event)
        for q in list(self._subscribers.get(event.job_id, set())):
            q.put_nowait(event)
            if final:
                q.put_nowait(None)  # sentinel: closes the SSE stream

    def _emit(self, event: Event, final: bool = False) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._deliver, event, final)
        else:
            self._deliver(event, final)

    async def subscribe(self, job_id: str):
        """Async generator of events for a job: replay buffer, then live stream."""
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.setdefault(job_id, set()).add(q)
        # No await between registering q and snapshotting → no missed/duplicated events.
        snapshot = list(self._events.get(job_id, []))
        try:
            for ev in snapshot:
                yield ev
            job = self._jobs.get(job_id)
            if job and job.status in TERMINAL and q.empty():
                return
            while True:
                ev = await q.get()
                if ev is None:
                    break
                yield ev
        finally:
            self._subscribers.get(job_id, set()).discard(q)

    # --- lifecycle -----------------------------------------------------------
    async def create_job(self, instruction: str, preset, files: list[tuple[str, bytes]]) -> Job:
        job = Job(instruction=instruction, requested_preset=preset, image_count=len(files))
        self._jobs[job.id] = job
        self._events[job.id] = []
        self._subscribers.setdefault(job.id, set())

        input_dir = self.job_dir(job.id) / "input"
        input_dir.mkdir(parents=True, exist_ok=True)
        for name, data in files:
            safe = os.path.basename(name) or "image"
            (input_dir / safe).write_bytes(data)
        self._persist(job)

        self._loop = asyncio.get_running_loop()
        self._tasks[job.id] = asyncio.create_task(asyncio.to_thread(self._execute, job))
        return job

    def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if not job or job.status in TERMINAL:
            return False
        self._cancelled.add(job_id)
        return True

    def _is_cancelled(self, job_id: str) -> bool:
        return job_id in self._cancelled

    # --- the worker (runs in a thread) --------------------------------------
    def _execute(self, job: Job) -> None:
        try:
            job.status = JobStatus.planning
            job.touch()
            self._emit(Event(type="job_update", job_id=job.id, data={"status": "planning"}))

            planner = get_planner(self.settings)
            cfg = planner.plan(job.instruction, job.image_count)
            if job.requested_preset:  # explicit user preset wins on the quality knob
                base = type(cfg).from_preset(job.requested_preset)
                base.train.backend = cfg.train.backend
                base.convert = cfg.convert
                base.notes = f"{cfg.notes} | preset set to '{job.requested_preset}' by user"
                cfg = base
            job.config = cfg
            self._persist(job)
            self._emit(Event(type="planned", job_id=job.id,
                             data={"config": cfg.model_dump(), "planner": getattr(planner, "name", "?")}))

            if self._is_cancelled(job.id):
                raise CancelledError()

            job.status = JobStatus.running
            job.touch()
            self._emit(Event(type="job_update", job_id=job.id, data={"status": "running"}))

            runner = PipelineRunner(self.settings)
            result = runner.run(job, self.job_dir(job.id), self._emit,
                                lambda: self._is_cancelled(job.id))
            job.result_path = str(result)
            job.status = JobStatus.done
            self._emit(Event(type="job_finished", job_id=job.id,
                             data={"status": "done", "result": str(result)}))
        except CancelledError:
            job.status = JobStatus.cancelled
            job.error = "cancelled by user"
            self._emit(Event(type="job_finished", job_id=job.id, data={"status": "cancelled"}))
        except Exception as exc:  # noqa: BLE001 - surfaced to the client
            job.status = JobStatus.failed
            job.error = str(exc)
            log.exception("job %s failed", job.id)
            self._emit(Event(type="job_failed", job_id=job.id, data={"error": str(exc)}))
        finally:
            job.touch()
            self._persist(job)
            self._cancelled.discard(job.id)
            self._emit(Event(type="job_update", job_id=job.id,
                             data={"status": job.status.value}), final=True)
