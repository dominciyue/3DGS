# 05 · The Reconstruction Pipeline

The pipeline is a **deterministic DAG** of typed stages. The Agent only chooses the
`PipelineConfig`; the runner executes the stages in order. Each stage reads from the
previous stage's output dir and writes to its own, under `data/jobs/<id>/`.

```
input/ ─► preprocess ─► colmap ─► train ─► convert ─► package ─► result/model.ply
```

Every stage is **idempotent** (safe to re-run), **validated** (checks its inputs
exist and its outputs are well-formed), **retryable**, and **mockable**
(`PIPELINE_MOCK=1` → synthetic outputs, no external tools).

## Job working directory layout

```
data/jobs/<job_id>/
├── input/                     raw uploaded images
├── preprocess/images/         normalized/renamed images
├── colmap/                    COLMAP workspace
│   ├── database.db
│   ├── sparse/0/              cameras.bin, images.bin, points3D.bin
│   └── images/                undistorted images
├── train/
│   └── point_cloud/iteration_30000/point_cloud.ply
├── convert/model.ply          validated (optionally compressed) model
├── result/
│   ├── model.ply              the artifact the frontend serves
│   └── manifest.json          metadata (config, stage timings, splat count, sha256)
├── job.json                   job record (status, config, stage states)
└── logs/<stage>.log
```

## Stages

### 1. `preprocess` (`pipeline/preprocess.py`)
- **In:** `input/*.{jpg,png,...}` · **Out:** `preprocess/images/*`
- **Does:** validate count/format, strip problematic EXIF rotation, optionally
  downscale to a target max edge, normalize filenames. Warns if `< 20` images
  (COLMAP usually needs more) or if exactly 1 image (multi-view path can't proceed —
  see the single-image note in `docs/03`).
- **External tools:** none required (Pillow optional for resize).

### 2. `colmap` (`pipeline/colmap.py`)
- **In:** `preprocess/images/` · **Out:** `colmap/sparse/0/` + undistorted `images/`
- **Does:** Structure-from-Motion → camera intrinsics/extrinsics + sparse point cloud.
  Mirrors the Inria `convert.py` flow: `feature_extractor → exhaustive_matcher →
  mapper → image_undistorter`.
- **External tools:** **COLMAP** (`COLMAP_BIN`). GPU optional
  (`--SiftExtraction.use_gpu 0 --SiftMatching.use_gpu 0` for CPU).
- **Validates:** at least one reconstructed model in `sparse/0/` with a healthy
  fraction of images registered.

### 3. `train` (`pipeline/train.py`)
- **In:** `colmap/` (poses + sparse cloud + images) · **Out:**
  `train/point_cloud/iteration_<N>/point_cloud.ply`
- **Does:** run the Inria trainer (`train.py -s <colmap> -m <out>`). Config controls
  iterations (e.g. 7k preview vs 30k full), resolution `-r`, SH degree, and **which
  trainer backend** (vanilla 3DGS vs **Mip-Splatting** vs **2DGS** — see `docs/07`).
- **External tools:** the Inria repo (`GS_REPO_DIR`, `GS_PYTHON`) + CUDA GPU.
- **Validates:** the expected `.ply` exists and parses.

### 4. `convert` (`pipeline/convert.py`)
- **In:** trained `.ply` · **Out:** `convert/model.ply`
- **Does:** locate the highest-iteration `.ply`, verify it's a *Gaussian* `.ply`
  (has the expected per-Gaussian properties the Unity importer needs), and optionally
  compress/decimate (cap splat count, or emit SPZ) for engine performance.
- **External tools:** none required for the basic copy+validate; optional compressors.
- **Why it exists:** Unity import fails on non-Gaussian `.ply` ("PLY is probably not a
  Gaussian Splat file"). This stage is the compatibility gate before the engine.

### 5. `package` (`pipeline/package.py`)
- **In:** `convert/model.ply` · **Out:** `result/model.ply` + `result/manifest.json`
- **Does:** finalize the deliverable, write a manifest (config used, per-stage timings,
  splat count, file size, sha256), so the frontend can show stats and Unity import is
  reproducible.
- **External tools:** none.

## `PipelineConfig` (what the Agent fills in)

```jsonc
{
  "preset": "preview | balanced | high",   // coarse quality/speed knob
  "max_image_edge": 1600,                   // preprocess downscale (px), or null
  "colmap": { "use_gpu": true, "matcher": "exhaustive" },
  "train": {
    "backend": "vanilla | mip | 2dgs",      // which trainer (mip = anti-aliased)
    "iterations": 30000,
    "resolution": 1,                         // Inria -r
    "sh_degree": 3
  },
  "convert": { "max_splats": null, "emit_spz": false },
  "notes": "free-text the Agent leaves for humans"
}
```

Presets expand to concrete values (e.g. `preview` → 7k iters, `-r 2`, GPU on). The
Agent picks a preset + toggles from the user's instruction; the runner enforces the
rest. The config is validated (pydantic) before anything runs.

## Events (what the frontend streams)

Each stage emits, over SSE:
`stage_started`, `stage_progress {pct, message}`, `stage_log {line}`,
`stage_finished {artifacts}`, and terminal `job_finished {status}` /
`job_failed {stage, error}`. The mock runner emits the same events with simulated
timing, so the UI is fully developable offline.

## Failure & retry

A stage that throws is retried up to `STAGE_MAX_RETRIES` (default 1) with backoff.
On final failure the job is `failed`, the offending stage + log are recorded, and
(when the LLM Agent is active) the planner is given the error so it can *adjust the
config and propose one bounded retry* — e.g. drop COLMAP to CPU, lower resolution on
OOM. Retries never change stage *logic*, only config.
