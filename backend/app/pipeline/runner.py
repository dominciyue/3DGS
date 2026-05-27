"""PipelineRunner — execute the stage DAG in order, with events, retry and cancel.

The runner is the single place that knows the directory wiring between stages and
keeps the ``Job``'s per-stage state in sync while emitting events for the SSE stream.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..models import STAGE_ORDER, Event, Job, JobStatus, StageStatus
# importing the stage modules registers them in REGISTRY
from . import colmap, convert, package, preprocess, train  # noqa: F401
from .stages import REGISTRY, CancelledError, StageContext, StageError


def _input_dir(job_dir: Path, name: str) -> Path:
    return {
        "preprocess": job_dir / "input",
        "colmap": job_dir / "preprocess" / "images",
        "train": job_dir / "colmap",
        "convert": job_dir / "train",
        "package": job_dir / "convert",
    }[name]


class PipelineRunner:
    def __init__(self, settings: Settings):
        self.settings = settings

    def run(
        self,
        job: Job,
        job_dir: Path,
        emit_event: Callable[[Event], None],
        is_cancelled: Callable[[], bool],
    ) -> Path:
        """Run all stages. Returns the final model path. Raises on failure/cancel."""
        assert job.config is not None, "job.config must be set by the planner first"

        for name in STAGE_ORDER:
            stage = REGISTRY[name]
            st = job.stage(name)
            # the terminal stage writes the deliverable to result/ (see docs/05)
            work_dir = job_dir / ("result" if name == "package" else name)

            def emit(etype: str, data: dict, _name: str = name) -> None:
                if etype == "stage_progress":
                    s = job.stage(_name)
                    s.progress = float(data.get("pct", s.progress))
                    s.message = data.get("message", s.message)
                    job.touch()
                emit_event(Event(type=etype, job_id=job.id, stage=_name, data=data))

            ctx = StageContext(
                job_id=job.id, job_dir=job_dir, work_dir=work_dir,
                input_dir=_input_dir(job_dir, name), config=job.config,
                mock=self.settings.mock, settings=self.settings,
                emit=emit, is_cancelled=is_cancelled, stage_name=name,
            )

            st.status = StageStatus.running
            st.started_at = time.time()
            job.touch()
            emit("stage_started", {})

            attempt = 0
            while True:
                try:
                    if is_cancelled():
                        raise CancelledError()
                    result = stage.execute(ctx)
                    st.artifacts = result.artifacts
                    st.status = StageStatus.done
                    st.progress = 1.0
                    st.finished_at = time.time()
                    job.touch()
                    emit("stage_finished", {"artifacts": result.artifacts, "metrics": result.metrics})
                    break
                except CancelledError:
                    st.status = StageStatus.failed
                    st.error = "cancelled"
                    st.finished_at = time.time()
                    job.touch()
                    raise
                except Exception as exc:  # noqa: BLE001 - reported to user, then re-raised
                    attempt += 1
                    if attempt > self.settings.stage_max_retries:
                        st.status = StageStatus.failed
                        st.error = str(exc)
                        st.finished_at = time.time()
                        job.touch()
                        emit("stage_failed", {"error": str(exc)})
                        raise StageError(f"stage '{name}' failed: {exc}") from exc
                    emit("stage_log", {"line": f"error: {exc} — retry {attempt}/"
                                               f"{self.settings.stage_max_retries}"})
                    time.sleep(0.5 * attempt)

        return job_dir / "result" / "model.ply"
