"""Stage framework: the contract every pipeline stage implements.

A stage:
  * reads from ``ctx.input_dir`` (previous stage's output) and writes to ``ctx.work_dir``
  * implements ``run`` (real, may call external tools) and ``run_mock`` (synthetic)
  * reports progress/logs via ``ctx`` and is cancellable
  * returns a ``StageResult`` listing its artifacts
"""
from __future__ import annotations

import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..models import PipelineConfig


class StageError(RuntimeError):
    """Raised when a stage fails in a way the runner should treat as an error."""


class CancelledError(Exception):
    """Raised internally when the job has been cancelled."""


@dataclass
class StageResult:
    artifacts: dict[str, str] = field(default_factory=dict)
    metrics: dict[str, float | int | str] = field(default_factory=dict)


@dataclass
class StageContext:
    job_id: str
    job_dir: Path
    work_dir: Path          # this stage's output dir
    input_dir: Path         # dir this stage reads from
    config: PipelineConfig
    mock: bool
    settings: Settings
    emit: Callable[[str, dict], None]
    is_cancelled: Callable[[], bool]
    stage_name: str = ""

    # --- reporting helpers ---------------------------------------------------
    def log(self, line: str) -> None:
        self.emit("stage_log", {"line": line.rstrip()})

    def progress(self, pct: float, message: str = "") -> None:
        self.emit("stage_progress", {"pct": max(0.0, min(1.0, pct)), "message": message})

    def check_cancel(self) -> None:
        if self.is_cancelled():
            raise CancelledError()

    # --- subprocess helper (real stages) ------------------------------------
    def run_cmd(self, cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
        """Run a command, streaming its output to the log; raise StageError on failure."""
        self.log("$ " + " ".join(str(c) for c in cmd))
        try:
            proc = subprocess.Popen(
                [str(c) for c in cmd],
                cwd=str(cwd) if cwd else None,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError as exc:
            raise StageError(f"command not found: {cmd[0]} ({exc})") from exc

        assert proc.stdout is not None
        for line in proc.stdout:
            self.check_cancel()
            self.log(line)
        code = proc.wait()
        if code != 0:
            raise StageError(f"command failed (exit {code}): {' '.join(str(c) for c in cmd)}")


class Stage(ABC):
    """Base class for all stages."""

    name: str = "stage"

    @abstractmethod
    def run(self, ctx: StageContext) -> StageResult:
        """Real execution (may require external tools / GPU)."""

    @abstractmethod
    def run_mock(self, ctx: StageContext) -> StageResult:
        """Synthetic execution: no external tools, deterministic, fast."""

    def execute(self, ctx: StageContext) -> StageResult:
        ctx.work_dir.mkdir(parents=True, exist_ok=True)
        return self.run_mock(ctx) if ctx.mock else self.run(ctx)


# Stage registry, populated by the concrete stage modules at import time.
REGISTRY: dict[str, Stage] = {}


def register(stage: Stage) -> Stage:
    REGISTRY[stage.name] = stage
    return stage
