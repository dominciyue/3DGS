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
from .config import settings
from .jobs import JobStore
from .models import CreateJobResponse, HealthResponse, JobStatus

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


# Serve the static frontend at / if present (added last so /api/* wins).
_frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend.is_dir():
    app.mount("/", StaticFiles(directory=str(_frontend), html=True), name="frontend")
