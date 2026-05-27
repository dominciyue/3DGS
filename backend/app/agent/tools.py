"""Tool schema the planning Agent uses, plus mapping its output to a PipelineConfig.

The planner currently exposes a single decision tool, ``submit_plan``. The
architecture (docs/02) supports extending this to a multi-tool loop
(run_pipeline / inspect_artifact / finish) for error-driven replanning; that is the
natural next increment.
"""
from __future__ import annotations

from typing import Any

from ..models import PipelineConfig

SUBMIT_PLAN_TOOL: dict[str, Any] = {
    "name": "submit_plan",
    "description": "Submit the chosen 3DGS pipeline configuration for this job.",
    "input_schema": {
        "type": "object",
        "properties": {
            "preset": {
                "type": "string",
                "enum": ["preview", "balanced", "high"],
                "description": "Coarse quality/speed setting.",
            },
            "train_backend": {
                "type": "string",
                "enum": ["vanilla", "mip", "2dgs", "relight"],
                "description": "Which trainer to use (see system prompt).",
            },
            "iterations": {
                "type": "integer",
                "minimum": 100,
                "maximum": 100000,
                "description": "Optional override of the preset's training iterations.",
            },
            "max_splats": {
                "type": "integer",
                "minimum": 1000,
                "description": "Optional cap on splat count for performance/VR/mobile.",
            },
            "emit_spz": {
                "type": "boolean",
                "description": "Emit a compact SPZ alongside the .ply.",
            },
            "notes": {
                "type": "string",
                "description": "One-line rationale for these choices.",
            },
        },
        "required": ["preset", "train_backend", "notes"],
    },
}


def plan_from_tool_input(data: dict[str, Any]) -> PipelineConfig:
    """Convert a validated ``submit_plan`` tool input into a PipelineConfig."""
    cfg = PipelineConfig.from_preset(data.get("preset", "balanced"))
    cfg.train.backend = data.get("train_backend", "vanilla")
    if data.get("iterations"):
        cfg.train.iterations = int(data["iterations"])
    if data.get("max_splats"):
        cfg.convert.max_splats = int(data["max_splats"])
    cfg.convert.emit_spz = bool(data.get("emit_spz", False))
    cfg.notes = data.get("notes", "")
    return cfg
