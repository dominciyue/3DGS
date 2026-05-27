# 04 · Getting Started (Environment Setup)

There are **three independent environments**. You do **not** need all three to start
contributing — pick the one for your role and use mock mode for the rest.

| Env | Who | Needs a GPU? |
|---|---|---|
| A. Backend + frontend (mock pipeline) | everyone | ❌ no |
| B. Real 3DGS reconstruction (COLMAP + Inria trainer) | 许可 | ✅ CUDA GPU |
| C. Unity viewer | 郑宇轩, 朱越 | 🟡 a decent GPU, no CUDA needed |

---

## A. Backend + frontend — runs anywhere (start here)

```bash
# Backend (Python 3.10+)
cd backend
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # optional: set ANTHROPIC_API_KEY for the real Agent
uvicorn app.main:app --reload # http://localhost:8000  (docs at /docs)

# Tests (no GPU, no external tools)
pytest -q

# Frontend (separate terminal)
cd frontend && python -m http.server 5173   # http://localhost:5173
```

With `PIPELINE_MOCK=1` (the default), the pipeline produces a synthetic `.ply` so you
can exercise the whole flow — upload → agent plan → staged progress → download —
without a GPU. This is enough to build and test the API, the Agent, and the UI.

**LLM key (optional):** without `ANTHROPIC_API_KEY` the Agent uses a deterministic
`MockPlanner`. With a key it uses Claude tool-use. Either way the pipeline is the same.

---

## B. Real 3DGS reconstruction — needs CUDA

Requirements (verified against the Inria repo): a CUDA-ready GPU (**compute ≥ 7.0**,
**~24 GB VRAM** for full quality; less works with smaller batches/resolution),
**COLMAP**, and **ImageMagick**.

### 1. COLMAP
- Linux: `sudo apt install colmap` (or build from source for CUDA features).
- Windows: download the prebuilt binary from https://colmap.github.io/ and add to PATH.
- Verify: `colmap -h`. If feature extraction lacks a GPU, the convert step can pass
  `--SiftExtraction.use_gpu 0 --SiftMatching.use_gpu 0` (slower, CPU-only).

### 2. Inria 3DGS trainer (cloned into `third_party/`, not vendored)
```bash
cd third_party
git clone https://github.com/graphdeco-inria/gaussian-splatting --recursive
cd gaussian-splatting
conda env create --file environment.yml     # creates the 'gaussian_splatting' env
conda activate gaussian_splatting
# Newer 40/50-series GPUs: use CUDA 12.x + Python 3.11 and install the matching
# torch/submodules if environment.yml fails — see the repo's issues.
```

### 3. End-to-end smoke test (one known-good scene)
```bash
# (a) prepare your own images -> COLMAP poses + sparse cloud
python convert.py -s /path/to/scene          # scene/input/*.jpg  ->  scene/sparse/0/, images/

# (b) train
python train.py -s /path/to/scene -m /path/to/output/scene

# (c) result:
#   /path/to/output/scene/point_cloud/iteration_30000/point_cloud.ply
```

Point the backend at these tools by setting `COLMAP_BIN`, `GS_REPO_DIR`, and
`GS_PYTHON` in `backend/.env` (see `.env.example`). The `train`/`colmap` stages then
shell out to them; otherwise they stay in mock mode.

**Capture tips for good results:** 30–200 photos, lots of overlap (~70–80%), orbit the
subject at 2–3 heights, even lighting, avoid motion blur and reflective/transparent
surfaces. Garbage in → garbage splats.

---

## C. Unity viewer — needs Unity 6 (no CUDA)

1. Install **Unity 6 LTS** (Unity Hub).
2. Create a 3D (URP or Built-in) project, or open `unity/` once a project is created
   there (only `Assets/`, `Packages/`, `ProjectSettings/` are tracked — see `.gitignore`).
3. Install **aras-p/UnityGaussianSplatting** (Package Manager → Add from git URL, or
   clone and add the local package). Follow its README.
4. Copy our scripts from `unity/Assets/Scripts/` into the project.
5. Import a `.ply` (a public sample to start) and press Play. Full steps: `docs/06`.

GPU: any modern discrete GPU handles a few hundred-thousand to a few-million splats.
Lower the splat count / use the importer's compression if it stutters.

---

## Troubleshooting quick hits

| Symptom | Fix |
|---|---|
| `submodule diff-gaussian-rasterization` build fails | ensure CUDA toolkit matches your PyTorch; clone with `--recursive`; check repo issues for your GPU gen |
| COLMAP finds too few images / fails to register | more overlap, more photos, better texture; try sequential matcher for video frames |
| Unity: "PLY is probably not a Gaussian Splat file" | it must be the **3DGS** `.ply` (per-Gaussian attrs), not a plain point cloud |
| Out of VRAM during training | lower `-r` (resolution), reduce densification, or train on CPU data loading |
| Agent does nothing / errors on key | leave `ANTHROPIC_API_KEY` unset to use the mock planner |
