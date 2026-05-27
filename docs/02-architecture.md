# 02 · System Architecture

## Core decision: Agent *supervises*, pipeline *executes*

An LLM agent that freely decides every reconstruction step is unreliable — and our
proposal explicitly lists *"Agent 本身具有不确定性，工具调用存在错误风险"* as a top
risk. So we split responsibilities:

```
        non-deterministic, language-level                deterministic, data-level
   ┌────────────────────────────────────┐        ┌────────────────────────────────┐
   │            AGENT (Claude)           │ config │        PIPELINE RUNNER          │
   │  • parse NL request                 │───────►│  fixed DAG of typed stages      │
   │  • choose preset / params           │        │  preprocess→colmap→train→       │
   │  • decide optional stages           │        │  convert→package                │
   │  • read stage results, diagnose,    │◄───────│  each stage: validate I/O,      │
   │    retry or adjust                  │ result │  idempotent, retryable          │
   └────────────────────────────────────┘        └────────────────────────────────┘
```

- The **pipeline** is the source of truth for *what runs*. Stages have typed
  inputs/outputs and validate them. Given the same config, it does the same thing.
- The **Agent** decides *how the pipeline is configured* and *reacts to outcomes*.
  It calls a small set of tools (configure job, run stage/pipeline, inspect
  artifacts, set parameters). It never hand-writes Gaussians or bypasses a stage.
- If no `ANTHROPIC_API_KEY` is set, a **mock planner** produces a sensible default
  config from simple rules — so the whole system is demoable offline.

This keeps non-determinism *outside* the critical path while still getting the
Agent's value: natural-language intake, parameter judgment, and error recovery.

## Components & contracts

Each component has one job, a clear interface, and is testable in isolation.

### 1. Frontend (`frontend/`)
- **Does:** collect images + a natural-language instruction, POST a job, stream
  progress/logs, offer the result for download, show Unity next-steps.
- **Depends on:** the REST API only. Zero build step (static HTML/CSS/JS).
- **Interface:** the REST endpoints below.

### 2. Backend API (`backend/app/main.py`)
- **Does:** HTTP surface — accept uploads, create jobs, stream events, serve results.
- **Depends on:** the job store and the agent/pipeline modules.
- **Interface (REST):**

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | liveness + whether an LLM key is configured |
| `POST` | `/api/jobs` | create a job (multipart: images[] + `instruction` + optional `preset`) → `{job_id}` |
| `GET`  | `/api/jobs` | list jobs |
| `GET`  | `/api/jobs/{id}` | job status, config, stage states, artifacts |
| `GET`  | `/api/jobs/{id}/events` | **SSE** stream of status/log updates |
| `GET`  | `/api/jobs/{id}/result` | download the produced model (`.ply`) |
| `POST` | `/api/jobs/{id}/cancel` | request cancellation |

### 3. Job store + worker (`backend/app/jobs.py`)
- **Does:** own job lifecycle (`queued → planning → running → done/failed/cancelled`),
  persist each job under `data/jobs/<id>/`, run one background worker per job, and
  publish events to SSE subscribers.
- **Depends on:** the agent planner + pipeline runner.
- **Interface:** `create_job(...)`, `get_job(id)`, `list_jobs()`, `subscribe(id)`.

### 4. Agent planner (`backend/app/agent/`)
- **`prompts.py`** — system prompt describing the goal, the available stages, and the
  guardrail that it configures (not bypasses) the pipeline.
- **`tools.py`** — JSON-schema tool definitions + a dispatcher that maps tool calls
  onto pipeline operations. Tools: `set_pipeline_config`, `run_pipeline`,
  `inspect_artifact`, `finish`.
- **`planner.py`** — the agentic loop (Claude tool-use). Falls back to a deterministic
  `MockPlanner` if no API key. Output: a validated `PipelineConfig`.
- **Depends on:** Anthropic SDK (optional), pipeline types.

### 5. Pipeline (`backend/app/pipeline/`)
- **`stages.py`** — `Stage` base class, `StageResult`, and a registry. Each stage:
  `validate_inputs() → run() → produce artifacts → validate_outputs()`.
- **`runner.py`** — executes stages in DAG order from a `PipelineConfig`, emits
  progress events, supports `mock=True` (synthetic outputs, no external tools),
  cancellation, and per-stage retry.
- **`preprocess.py / colmap.py / train.py / convert.py / package.py`** — the stages.
  Real subprocess wrappers around COLMAP / the Inria trainer, each *gated*: if the
  tool isn't installed, the stage fails with an actionable message (or runs mock).
- **Depends on:** external tools (COLMAP, Inria 3DGS) — only at real-run time.

### 6. Unity project (`unity/`)
- **Does:** load the `.ply`, render it (aras-p plugin), and provide interactions.
- **Depends on:** aras-p/UnityGaussianSplatting + the produced `.ply`.
- **Interface:** drop our `Assets/Scripts` onto the scene; see `docs/06`.

## Data flow (one job)

```
1. Frontend POSTs images + instruction.
2. Job store saves images to data/jobs/<id>/input/, status=planning, starts worker.
3. Agent planner reads the instruction (+ image count/metadata) → PipelineConfig
   (quality preset, iterations, whether to run Mip-Splatting, etc.).
4. Runner executes the DAG, each stage writing to data/jobs/<id>/<stage>/ and
   emitting events the frontend streams over SSE:
       preprocess  → normalized images
       colmap      → cameras + sparse point cloud  (sparse/0/)
       train       → point_cloud/iteration_*/point_cloud.ply
       convert     → validated/optionally-compressed model
       package     → result/model.ply (+ manifest.json with metadata)
5. status=done; frontend enables download; user imports into Unity.
```

## Job state machine

```
queued ──► planning ──► running ──┬─► done
   │            │           │     └─► failed  (stage error after retries)
   └────────────┴───────────┴───────► cancelled  (user request)
```

## Why these boundaries

- The **API ↔ pipeline** split lets 朱越 build the frontend against a mock backend
  while 许可 wires real tools behind the same contract.
- The **Agent ↔ pipeline** split means a bad LLM decision can only produce a bad
  *config*, which stages still validate — it cannot corrupt the reconstruction logic.
- The **`.ply` contract** is the single hand-off to Unity, so 郑宇轩 can work against
  any conformant `.ply` (public sample or freshly trained) without backend coupling.

## Technology choices (and the alternatives we rejected)

| Choice | Why | Rejected alternative |
|---|---|---|
| FastAPI | async, typed (pydantic), trivial SSE, tiny | Flask (less async/typing); Django (too heavy) |
| In-process job worker | one box, simple, demo-friendly | Celery/Redis (ops overhead for a course demo) |
| Claude tool-use for the Agent | strong tool-use; supervises rather than executes | LangChain (opaque); fully-autonomous agent (unreliable) |
| Inria 3DGS trainer | the reference implementation; well documented | gsplat/nerfstudio (fine alternatives; more deps) |
| aras-p Unity importer | drag-drop `.ply`, GPU sort, Unity 6, no runtime CUDA | clarte53 VR viewer (kept for the VR stretch goal) |
| Vanilla JS frontend | zero build, runs anywhere, easy to grade/demo | React/Vite (build step; unnecessary here) |
