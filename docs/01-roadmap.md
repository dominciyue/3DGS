# 01 · Roadmap & Task Split

Timeline from the proposal: **Week 13–14** basic pipeline · **Week 15** render
optimization + advanced extensions · **Week 16** results demo. (Today's anchor for
status tracking: 2026-05-27.)

## Guiding strategy: close the last mile first

The biggest risk is integration, not any single component. So we **build the
pipeline back-to-front**:

1. **First** get a *pre-trained, public* 3DGS `.ply` rendering and interactive in
   Unity. Now the team always has a demo, and the Unity/interaction work (郑宇轩,
   朱越) is unblocked without waiting on training.
2. **Then** get the Inria trainer producing a `.ply` from a known good image set.
3. **Then** wire the Agent + backend + frontend in front of it.
4. **Only then** add extensions (Mip-Splatting, 2DGS, relighting, VR).

This way every week ends with something runnable.

## Milestones

### M0 — Foundations (now → end of Week 13)
- [x] Repo scaffold, `.gitignore`, docs, backend/frontend/unity skeletons
- [ ] Each member has their environment working (see `04-getting-started.md`)
- [ ] **Unity renders a public sample `.ply`** (aras-p plugin) — *the unblocking milestone*
- [ ] Backend API + frontend talk to each other in **mock pipeline** mode (no GPU)

### M1 — Baseline end-to-end pipeline (Week 13–14) — *the required deliverable*
- [ ] COLMAP runs on a sample image set (via `convert.py`) → poses + sparse cloud
- [ ] Inria 3DGS trains → `point_cloud.ply`
- [ ] `convert` + `package` stages locate the final `.ply` and expose it for download
- [ ] Agent planner turns a NL request into a concrete pipeline config (real or mock LLM)
- [ ] Frontend: upload → run → live progress/logs → download model
- [ ] Unity: import produced `.ply`; interactions: **orbit, zoom, pan, select, display-param sliders**
- [ ] One full demo scene reconstructed from our own photos

### M2 — Optimization & extensions (Week 15)
- [ ] **Mip-Splatting** path (anti-aliasing) selectable by the Agent — see `07-extensions.md`
- [ ] Render optimization in Unity (quality vs. perf presets; LOD/culling notes)
- [ ] Pick **one** advanced track and land it: 2DGS *or* Relightable 3DGS *or* VR viewer
- [ ] Scene organization: multiple objects in one scene; per-object selection

### M3 — Polish & demo (Week 16)
- [ ] 3–5 example scenes; short capture-to-Unity walkthrough
- [ ] Demo script + slides; record fallback video in case of live-demo risk
- [ ] README/docs final pass; tag a release; attach sample `.ply` assets to the Release

## Task split (from the deck)

| Member | Responsibility | Main files/dirs | First concrete task |
|---|---|---|---|
| **许可 Xu Ke** | Agent orchestration + 3DGS setup | `backend/app/agent`, `backend/app/pipeline`, `third_party/` | Get COLMAP + Inria trainer producing a `.ply`; wire the `train`/`colmap` stages to real subprocess calls |
| **郑宇轩 Zheng Yuxuan** | Unity scene import/organization + render optimization | `unity/`, `docs/06`, `docs/07` | Render a public `.ply` in Unity 6 via aras-p; set up scene organization + quality presets |
| **朱越 Zhu Yue** | Frontend interface + interaction | `frontend/`, `unity/Assets/Scripts` (interaction) | Polish the dashboard; implement the Unity interaction scripts (orbit/select/params) |

Interfaces between members are the **REST API** (`docs/02-architecture.md` §API) and
the **`.ply` contract** (`docs/05-pipeline.md`) — agree on these early so work
proceeds in parallel.

## Risk register (from the proposal, with mitigations)

| Risk | Mitigation |
|---|---|
| 3DGS env config / GPU/VRAM demands | Use a smaller-VRAM config; `--SiftExtraction.use_gpu 0` fallback; rent a GPU box; keep a public `.ply` for the demo. |
| Agent non-determinism / tool-call errors | Agent only *configures* a deterministic DAG; every stage validates I/O and is retryable; mock planner as fallback. |
| Unity format incompatibility | Standardize on Inria `.ply` + aras-p importer (known-good); convert/version-check in the `convert` stage. |
| Render perf bottlenecks / stutter | Quality presets, GPU sort, decimation/compression, Mip-Splatting for stability; profile early. |
| Optimization is hard | Treat extensions as *optional* M2 tracks; baseline (M1) never depends on them. |

## Definition of done (baseline)

A teammate on a fresh machine can: start the backend + frontend, drop in a photo
set, watch the Agent run the pipeline, download a `.ply`, open the Unity project,
import it, and **orbit / zoom / pan / select an object / change a display
parameter** — all documented in `docs/`.
