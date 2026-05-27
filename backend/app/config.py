"""Runtime configuration, all driven by environment variables (see .env.example).

Defaults are chosen so the whole system runs out-of-the-box in *mock* mode with no
GPU, no external tools, and no API key. Set the relevant vars to enable the real
COLMAP / 3DGS / Claude paths.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:  # optional: load a .env file if python-dotenv is installed
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is optional
    pass


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    return Path(raw).expanduser().resolve() if raw else default


BACKEND_DIR = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    # --- core ---
    data_dir: Path = field(default_factory=lambda: _path("DATA_DIR", BACKEND_DIR / "data"))
    # When true, stages produce synthetic outputs and never call external tools.
    mock: bool = field(default_factory=lambda: _bool("PIPELINE_MOCK", True))
    # Per-step delay in mock mode so the UI shows progress; set 0 in tests.
    mock_delay: float = field(default_factory=lambda: float(os.getenv("MOCK_STAGE_DELAY", "0.3")))
    stage_max_retries: int = field(default_factory=lambda: int(os.getenv("STAGE_MAX_RETRIES", "1")))

    # --- agent / LLM ---
    anthropic_api_key: str | None = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY") or None)
    agent_model: str = field(default_factory=lambda: os.getenv("AGENT_MODEL", "claude-opus-4-7"))

    # --- external tools (only needed when mock=False) ---
    colmap_bin: str = field(default_factory=lambda: os.getenv("COLMAP_BIN", "colmap"))
    gs_repo_dir: str | None = field(default_factory=lambda: os.getenv("GS_REPO_DIR") or None)
    gs_python: str = field(default_factory=lambda: os.getenv("GS_PYTHON", "python"))
    mip_repo_dir: str | None = field(default_factory=lambda: os.getenv("MIP_REPO_DIR") or None)
    dgs2_repo_dir: str | None = field(default_factory=lambda: os.getenv("DGS2_REPO_DIR") or None)
    relight_repo_dir: str | None = field(default_factory=lambda: os.getenv("RELIGHT_REPO_DIR") or None)

    # --- server ---
    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv(
            "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
        ).split(",")
    )

    @property
    def jobs_dir(self) -> Path:
        return self.data_dir / "jobs"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    def trainer_repo_for(self, backend: str) -> str | None:
        return {
            "vanilla": self.gs_repo_dir,
            "mip": self.mip_repo_dir,
            "2dgs": self.dgs2_repo_dir,
            "relight": self.relight_repo_dir,
        }.get(backend)

    def ensure_dirs(self) -> None:
        self.jobs_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
