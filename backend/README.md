# Backend — Agent + Pipeline (FastAPI)

The orchestration brain: a FastAPI server that accepts images + a natural-language
instruction, has the **Agent** plan a `PipelineConfig`, and runs a **deterministic
pipeline** (preprocess → COLMAP → train 3DGS → convert → package) to produce a `.ply`.

Design rationale: [`../docs/02-architecture.md`](../docs/02-architecture.md).

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional edits
uvicorn app.main:app --reload # http://localhost:8000  (interactive docs at /docs)
```

`scripts/run_dev.sh` does the `.env` copy + launch for you.

It runs in **mock mode by default** (`PIPELINE_MOCK=1`): stages emit synthetic outputs
and the trained `.ply` is a small but format-correct Gaussian cloud — so the whole
flow (upload → plan → staged progress → download) works with no GPU, tools, or API key.

## Test

```bash
pytest -q          # no GPU / network required
```

## Layout

```
app/
├── main.py          FastAPI routes + SSE; serves ../frontend at /
├── config.py        env-driven settings (mock flag, tool paths, API key)
├── models.py        PipelineConfig, Job, StageState, Event (pydantic)
├── jobs.py          job store, per-job worker thread, SSE pub/sub
├── agent/
│   ├── planner.py   ClaudePlanner (tool-use) + MockPlanner fallback
│   ├── tools.py     submit_plan tool schema -> PipelineConfig
│   └── prompts.py   planner system prompt
└── pipeline/
    ├── runner.py    DAG executor: events, retry, cancel, mock
    ├── stages.py    Stage base + StageContext (subprocess helper)
    ├── preprocess.py / colmap.py / train.py / convert.py / package.py
    └── _ply.py      Gaussian .ply read/write/validate/decimate
```

## Going real (GPU)

Set `PIPELINE_MOCK=0` and point the tool paths in `.env` at an installed COLMAP and the
Inria trainer repo (see [`../docs/04-getting-started.md`](../docs/04-getting-started.md)
and [`../third_party/README.md`](../third_party/README.md)). Stages that need a missing
tool fail with an actionable message rather than pretending to work.

## API

| Method | Path | Purpose |
|---|---|---|
| GET  | `/api/health` | liveness + mock/LLM flags |
| POST | `/api/jobs` | multipart `images[]` + `instruction` + optional `preset` → `{job_id}` |
| GET  | `/api/jobs` · `/api/jobs/{id}` | list / status + config + stage states |
| GET  | `/api/jobs/{id}/events` | SSE progress + logs |
| GET  | `/api/jobs/{id}/result` | download `model.ply` |
| POST | `/api/jobs/{id}/cancel` | request cancellation |
