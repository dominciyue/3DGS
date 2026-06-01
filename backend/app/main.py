"""FastAPI surface for the 3DGS-Agent backend.

Endpoints (see docs/02-architecture.md §API):
    GET  /api/health
    POST /api/jobs                      multipart: images[] + instruction + preset
    GET  /api/jobs                      list
    GET  /api/jobs/{id}                 status + config + stage states
    GET  /api/jobs/{id}/events          Server-Sent Events stream
    GET  /api/jobs/{id}/result          download model.ply
    POST /api/jobs/{id}/cancel
Also serves the static frontend at / when ../frontend exists (one-command demo).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import __version__
from .agent.chat import get_chat
from .config import settings
from .jobs import JobStore
from .models import (ChatRequest, ChatResponse, CreateJobResponse, FromPathRequest,
                     HealthResponse, JobStatus)

app = FastAPI(title="3DGS-Agent", version=__version__)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

store = JobStore(settings)

VALID_PRESETS = {"preview", "balanced", "high"}


@app.get("/api/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(mock_pipeline=settings.mock, llm_enabled=settings.llm_enabled,
                          version=__version__)


@app.post("/api/jobs", response_model=CreateJobResponse)
async def create_job(
    images: list[UploadFile] = File(...),
    instruction: str = Form(""),
    preset: Optional[str] = Form(None),
) -> CreateJobResponse:
    if not images:
        raise HTTPException(400, "at least one image is required")
    if preset is not None and preset not in VALID_PRESETS:
        raise HTTPException(400, f"preset must be one of {sorted(VALID_PRESETS)}")
    files: list[tuple[str, bytes]] = []
    for f in images:
        data = await f.read()
        if data:
            files.append((f.filename or "image", data))
    if not files:
        raise HTTPException(400, "uploaded images were empty")
    job = await store.create_job(instruction=instruction, preset=preset, files=files)
    return CreateJobResponse(job_id=job.id)


@app.get("/api/jobs")
async def list_jobs():
    return [j.model_dump() for j in store.list()]


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    return job.model_dump()


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    if not store.get(job_id):
        raise HTTPException(404, "job not found")

    async def stream():
        agen = store.subscribe(job_id)
        try:
            while True:
                try:
                    ev = await asyncio.wait_for(agen.__anext__(), timeout=15.0)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"  # heartbeat keeps the connection alive
                    continue
                except StopAsyncIteration:
                    break
                yield f"data: {ev.model_dump_json()}\n\n"
        finally:
            await agen.aclose()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/jobs/{job_id}/result")
async def job_result(job_id: str):
    job = store.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.status != JobStatus.done:
        raise HTTPException(409, f"job is '{job.status.value}', no result available")
    path = store.result_file(job_id)
    if not path.exists():
        raise HTTPException(404, "result file missing")
    return FileResponse(path, media_type="application/octet-stream",
                        filename=f"{job_id}_model.ply")


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str):
    if not store.get(job_id):
        raise HTTPException(404, "job not found")
    ok = store.cancel(job_id)
    return {"cancelled": ok}


# --------------------------------------------------------------------------- #
# /api/sample  — serve a pre-trained sample .ply for the in-browser viewer, so
# the frontend can show a real 3DGS scene with one click (no training needed).
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _find_sample_ply() -> Path | None:
    bases = [REPO_ROOT / "sample-scene", REPO_ROOT / "data" / "sample-scene"]
    for base in bases:
        if not base.is_dir():
            continue
        cands = sorted(base.glob("point_cloud/iteration_*/point_cloud.ply"),
                       key=lambda p: int(p.parent.name.split("_")[-1]) if "_" in p.parent.name else -1)
        if cands:
            return cands[-1]
        direct = base / "point_cloud.ply"
        if direct.is_file():
            return direct
    return None


@app.get("/api/sample")
async def sample_scene():
    """Serve a pre-trained sample .ply if one is available under sample-scene/ or data/sample-scene/."""
    p = _find_sample_ply()
    if p is None:
        raise HTTPException(
            404,
            "no sample scene available — extract a trained 3DGS output to "
            "sample-scene/ (or data/sample-scene/) at the repo root",
        )
    return FileResponse(p, media_type="application/octet-stream", filename="sample.ply")


# --------------------------------------------------------------------------- #
# /api/jobs/from-path  — Unity client triggers a job by handing us a server-side
# folder of images, instead of uploading them via multipart.
# --------------------------------------------------------------------------- #

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


@app.post("/api/jobs/from-path", response_model=CreateJobResponse)
async def create_job_from_path(req: FromPathRequest) -> CreateJobResponse:
    p = Path(req.path).expanduser().resolve()
    if not p.is_dir():
        raise HTTPException(400, f"not a directory: {p}")
    files: list[tuple[str, bytes]] = []
    for img in sorted(p.iterdir()):
        if img.is_file() and img.suffix.lower() in IMAGE_EXTS:
            try:
                files.append((img.name, img.read_bytes()))
            except OSError as exc:
                raise HTTPException(400, f"cannot read {img.name}: {exc}") from exc
    if not files:
        raise HTTPException(400, f"no images found in {p}")
    job = await store.create_job(instruction=req.instruction or "",
                                 preset=req.preset, files=files)
    return CreateJobResponse(job_id=job.id)


# --------------------------------------------------------------------------- #
# /api/chat  — multi-turn free-form chat with the Agent (separate from the
# planner; used by the Unity studio UI's chat box).
# --------------------------------------------------------------------------- #

_chat_handler = None  # lazy, single instance


def _chat():
    global _chat_handler
    if _chat_handler is None:
        _chat_handler = get_chat(settings)
    return _chat_handler


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    if not req.messages:
        raise HTTPException(400, "messages cannot be empty")
    if req.messages[-1].role != "user":
        raise HTTPException(400, "last message must be from user")
    handler = _chat()
    payload = [m.model_dump() for m in req.messages]
    reply = await asyncio.to_thread(handler.reply, payload)
    return ChatResponse(reply=reply, backend=getattr(handler, "name", "?"))


# Serve the static frontend at / if present (added last so /api/* wins).
_frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
