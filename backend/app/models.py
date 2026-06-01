"""Typed data models: pipeline configuration, jobs, stage state, and events.

These are the contracts every other module agrees on. The Agent fills in a
``PipelineConfig``; the runner reports ``StageState``; the API serialises ``Job``.
"""
from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Pipeline configuration (what the Agent decides)
# --------------------------------------------------------------------------- #

TrainBackend = Literal["vanilla", "mip", "2dgs", "relight"]
Preset = Literal["preview", "balanced", "high"]

# Preset -> concrete defaults. The Agent picks a preset; explicit fields override.
PRESETS: dict[str, dict[str, Any]] = {
    "preview": {"iterations": 7000, "resolution": 2, "max_image_edge": 1280},
    "balanced": {"iterations": 30000, "resolution": 1, "max_image_edge": 1600},
    "high": {"iterations": 30000, "resolution": 1, "max_image_edge": None},
}


class ColmapConfig(BaseModel):
    use_gpu: bool = True
    matcher: Literal["exhaustive", "sequential"] = "exhaustive"


class TrainConfig(BaseModel):
    backend: TrainBackend = "vanilla"
    iterations: int = Field(default=30000, ge=100, le=100_000)
    resolution: int = Field(default=1, ge=1, le=8)
    sh_degree: int = Field(default=3, ge=0, le=3)


class ConvertConfig(BaseModel):
    max_splats: Optional[int] = Field(default=None, ge=1000)
    emit_spz: bool = False


class PipelineConfig(BaseModel):
    """The full, validated plan for one reconstruction job."""

    preset: Preset = "balanced"
    max_image_edge: Optional[int] = Field(default=1600, ge=256, le=8192)
    colmap: ColmapConfig = Field(default_factory=ColmapConfig)
    train: TrainConfig = Field(default_factory=TrainConfig)
    convert: ConvertConfig = Field(default_factory=ConvertConfig)
    notes: str = ""

    @classmethod
    def from_preset(cls, preset: Preset = "balanced", **overrides: Any) -> "PipelineConfig":
        base = PRESETS[preset]
        cfg = cls(
            preset=preset,
            max_image_edge=base["max_image_edge"],
            train=TrainConfig(iterations=base["iterations"], resolution=base["resolution"]),
        )
        return cfg.model_copy(update=overrides) if overrides else cfg


# --------------------------------------------------------------------------- #
# Stage & job state
# --------------------------------------------------------------------------- #


class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class JobStatus(str, Enum):
    queued = "queued"
    planning = "planning"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class StageState(BaseModel):
    name: str
    status: StageStatus = StageStatus.pending
    progress: float = 0.0  # 0..1
    message: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    error: Optional[str] = None
    artifacts: dict[str, str] = Field(default_factory=dict)

    @property
    def duration(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return round(self.finished_at - self.started_at, 2)
        return None


STAGE_ORDER = ["preprocess", "colmap", "train", "convert", "package"]


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    status: JobStatus = JobStatus.queued
    instruction: str = ""
    requested_preset: Optional[Preset] = None
    image_count: int = 0
    config: Optional[PipelineConfig] = None
    stages: list[StageState] = Field(
        default_factory=lambda: [StageState(name=n) for n in STAGE_ORDER]
    )
    error: Optional[str] = None
    result_path: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def stage(self, name: str) -> StageState:
        for s in self.stages:
            if s.name == name:
                return s
        raise KeyError(name)

    def touch(self) -> None:
        self.updated_at = time.time()


# --------------------------------------------------------------------------- #
# SSE events
# --------------------------------------------------------------------------- #


class Event(BaseModel):
    type: str  # job_update | stage_started | stage_progress | stage_log |
    #            stage_finished | job_finished | job_failed | planning
    job_id: str
    stage: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)
    ts: float = Field(default_factory=time.time)


# --------------------------------------------------------------------------- #
# API request/response helpers
# --------------------------------------------------------------------------- #


class CreateJobResponse(BaseModel):
    job_id: str


class HealthResponse(BaseModel):
    status: str = "ok"
    mock_pipeline: bool
    llm_enabled: bool
    version: str


# --------------------------------------------------------------------------- #
# /api/jobs/from-path  (Unity client triggers reconstruction by server-side dir)
# --------------------------------------------------------------------------- #


class FromPathRequest(BaseModel):
    path: str
    instruction: str = ""
    preset: Optional[Preset] = None


# --------------------------------------------------------------------------- #
# /api/chat  (free-form multi-turn chat with the Agent)
# --------------------------------------------------------------------------- #


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    reply: str
    backend: str  # "claude" | "mock"
