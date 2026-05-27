"""The planning Agent.

``ClaudePlanner`` uses the Anthropic SDK (Claude Opus 4.7) with a single forced
tool call to turn a natural-language request into a validated ``PipelineConfig``.
``MockPlanner`` is a deterministic keyword-rule fallback used whenever no API key is
configured or the LLM call fails — so the system is fully demoable offline.
"""
from __future__ import annotations

import logging

from ..config import Settings
from ..config import settings as default_settings
from ..models import PipelineConfig
from .prompts import SYSTEM_PROMPT
from .tools import SUBMIT_PLAN_TOOL, plan_from_tool_input

log = logging.getLogger(__name__)


def _any_in(text: str, words: list[str]) -> bool:
    return any(w in text for w in words)


class MockPlanner:
    """Deterministic, rule-based planner. No network, no API key."""

    name = "mock"

    def plan(self, instruction: str, image_count: int = 0) -> PipelineConfig:
        text = (instruction or "").lower()
        preset = "balanced"
        if _any_in(text, ["quick", "preview", "fast", "draft", "rapid", "快", "预览", "草稿"]):
            preset = "preview"
        elif _any_in(text, ["high quality", "highest", "best quality", "high-res",
                            "high res", "maximum", "高质量", "最高", "最好"]):
            preset = "high"

        backend = "vanilla"
        if _any_in(text, ["anti-alias", "antialias", "anti alias", "aliasing", "shimmer",
                          "flicker", "mip", "抗锯齿", "锯齿", "闪烁"]):
            backend = "mip"
        elif _any_in(text, ["surface", "mesh", "2dgs", "2d gaussian", "planar", "flat wall",
                            "表面", "网格", "平面"]):
            backend = "2dgs"
        elif _any_in(text, ["relight", "re-light", "relighting", "lighting", "重光照",
                            "光照", "打光"]):
            backend = "relight"

        max_splats = None
        if _any_in(text, ["mobile", "vr", "headset", "performance", "lightweight",
                          "low-end", "卡顿", "性能", "移动", "轻量"]):
            max_splats = 1_000_000

        cfg = PipelineConfig.from_preset(preset)  # type: ignore[arg-type]
        cfg.train.backend = backend  # type: ignore[assignment]
        if max_splats:
            cfg.convert.max_splats = max_splats
        notes = f"[mock planner] preset={preset}, backend={backend}"
        if max_splats:
            notes += f", max_splats={max_splats}"
        cfg.notes = notes
        return cfg


class ClaudePlanner:
    """LLM planner: Claude chooses the config via the ``submit_plan`` tool."""

    name = "claude"

    def __init__(self, settings: Settings):
        self.settings = settings
        self._fallback = MockPlanner()
        from anthropic import Anthropic  # lazy import — optional dependency

        self._client = Anthropic(api_key=settings.anthropic_api_key)

    def plan(self, instruction: str, image_count: int = 0) -> PipelineConfig:
        try:
            msg = self._client.messages.create(
                model=self.settings.agent_model,  # claude-opus-4-7
                max_tokens=1024,
                # System + tool form a stable prefix; cache_control is harmless and
                # helps once the prompt grows past the model's min cacheable size.
                system=[{"type": "text", "text": SYSTEM_PROMPT,
                         "cache_control": {"type": "ephemeral"}}],
                tools=[SUBMIT_PLAN_TOOL],
                tool_choice={"type": "tool", "name": "submit_plan"},
                messages=[{"role": "user", "content": (
                    f"Uploaded images: {image_count}\n"
                    f"User instruction: {instruction or '(none provided)'}\n\n"
                    "Choose the pipeline configuration and call submit_plan."
                )}],
            )
            for block in msg.content:
                if getattr(block, "type", None) == "tool_use" and block.name == "submit_plan":
                    cfg = plan_from_tool_input(block.input)
                    log.info("planner(claude): %s", cfg.notes or cfg.preset)
                    return cfg
            log.warning("planner: model did not call submit_plan; using mock fallback")
        except Exception as exc:  # noqa: BLE001 - never let planning crash a job
            log.warning("planner: Claude call failed (%s); using mock fallback", exc)
        return self._fallback.plan(instruction, image_count)


def get_planner(settings: Settings | None = None):
    """Return a ClaudePlanner if an API key is set and the SDK imports, else MockPlanner."""
    settings = settings or default_settings
    if settings.llm_enabled:
        try:
            return ClaudePlanner(settings)
        except Exception as exc:  # noqa: BLE001
            log.warning("planner: could not initialise Claude (%s); using mock", exc)
    return MockPlanner()
