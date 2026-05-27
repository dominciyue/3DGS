# 3DGS-Agent — 图像到 Unity 可交互高斯场景生成系统

> An **Agent-orchestrated pipeline** that turns photos into an **interactive 3D Gaussian Splatting (3DGS) scene** you can browse, zoom, move, select and tune **inside Unity**.
>
> VRAR Game Design & Development · Group 13 (第 13 组)
> Xu Ke 许可 · Zheng Yuxuan 郑宇轩 · Zhu Yue 朱越

---

## 1. What this is

You upload one or more photos through a web page. An **LLM Agent** then drives a
fixed reconstruction pipeline end-to-end — camera estimation (COLMAP/SfM),
3D Gaussian Splatting training, format conversion, and packaging — and produces a
`.ply` Gaussian model that loads into **Unity**, where the user can **browse,
zoom, pan, select objects, and adjust display parameters** in real time.

```
 photos ─► [Agent backend] ─► COLMAP ─► 3DGS training ─► .ply ─► Unity ─► interact
            (FastAPI + Claude)                                   (aras-p importer)
```

The design principle that shapes everything here:

> **The Agent is a *supervisor* over a *deterministic* pipeline — not a free-form
> actor that improvises every step.**

3DGS reconstruction is a fixed DAG (preprocess → SfM → train → convert → package).
We run that deterministically for reliability, and let the Agent handle the parts
LLMs are actually good at: understanding a natural-language request, **picking
parameters/quality presets**, **deciding which optional stages to run**
(e.g. Mip-Splatting anti-aliasing), and **diagnosing failures and retrying**.
This directly addresses the risk flagged in our proposal — *"Agent 本身具有不确定性，
工具调用存在错误风险"* — by keeping non-determinism out of the critical path.

## 2. Architecture at a glance

```
                          ┌──────────────────────────────────────────┐
   Browser (frontend/)    │              Agent Backend                │
 ┌─────────────────────┐  │                (FastAPI)                  │
 │ drag-drop images +  │  │                                           │
 │ NL instruction box  │──┼─► POST /api/jobs ──► Job Store + Queue     │
 │ live progress/logs  │◄─┼── GET  /api/jobs/{id}/events (SSE)         │
 │ download model      │  │        ▲                     │            │
 └─────────────────────┘  │        │                     ▼            │
                          │  ┌─────┴──────┐        ┌──────────────┐    │
                          │  │   Agent     │ plan   │  Pipeline    │    │
                          │  │  Planner    │───────►│  Runner      │    │
                          │  │  (Claude    │ tools  │  (DAG exec)  │    │
                          │  │   tool-use) │◄───────│              │    │
                          │  └────────────┘ result └──────┬───────┘    │
                          └─────────────────────────────── ┼───────────┘
                                                            ▼
       preprocess ─► colmap(SfM) ─► train(3DGS) ─► convert ─► package
                                                            │
                                                            ▼
                                              point_cloud.ply (Gaussian model)
                                                            │
                                                            ▼
            Unity project (unity/) — aras-p GaussianSplat importer + our C# scripts
                     OrbitCamera · SceneManager · Selection · DisplayParam UI
```

Full design rationale: [`docs/02-architecture.md`](docs/02-architecture.md).

## 3. Repository layout

```
3DGS/
├── README.md                 ← you are here
├── LICENSE                   ← MIT for our code; upstream licenses differ (see third_party)
├── .gitignore                ← keeps .ply / checkpoints / datasets / Unity caches out of git
├── docs/                     ← the project's written brain
│   ├── 00-overview.md          project summary & glossary
│   ├── 01-roadmap.md           milestones (weeks 13–16) + task split + status
│   ├── 02-architecture.md      system design & component contracts
│   ├── 03-tech-research.md     survey: 3DGS, Mip-Splatting, 2DGS, Relightable, viewers
│   ├── 04-getting-started.md   environment setup (COLMAP, CUDA, conda, Unity)
│   ├── 05-pipeline.md          each stage's input/output/command, in detail
│   ├── 06-unity-integration.md import .ply → Unity, wire up interaction scripts
│   ├── 07-extensions.md        Mip-Splatting / 2DGS / Relighting / VR stretch goals
│   └── assets/                 original proposal PDF + slide deck
├── backend/                  ← Python: FastAPI server + Agent + pipeline (runnable)
│   ├── app/
│   │   ├── main.py             REST API + SSE
│   │   ├── jobs.py             job store + async worker
│   │   ├── agent/              Claude tool-use planner (planner/tools/prompts)
│   │   └── pipeline/           deterministic DAG: stages + runner
│   ├── tests/                  pytest — pipeline/job logic, runs WITHOUT GPU
│   └── requirements.txt
├── frontend/                 ← zero-build web dashboard (HTML/CSS/JS)
├── unity/                    ← Unity-side C# interaction scripts + setup guide
│   └── Assets/Scripts/
└── third_party/              ← setup instructions for the heavy upstream repos (not vendored)
```

## 4. Quickstart

> The **backend + frontend run on any machine** (the pipeline is mockable, tests
> pass with no GPU). The **actual 3DGS reconstruction needs a CUDA GPU + COLMAP**,
> and the **Unity demo needs Unity 6**. See [`docs/04-getting-started.md`](docs/04-getting-started.md).

### Backend (Agent + API)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY (optional; mock planner works without it)
uvicorn app.main:app --reload   # serves API on http://localhost:8000
```

Run the tests (no GPU required):

```bash
cd backend && pytest -q
```

### Frontend (task dashboard)

```bash
cd frontend
python -m http.server 5173      # then open http://localhost:5173
```

The dashboard talks to the backend at `http://localhost:8000`. Drag in photos,
type an instruction ("reconstruct this object, high quality, anti-aliased"),
and watch the pipeline run with live logs.

### Unity (interactive viewer)

See [`docs/06-unity-integration.md`](docs/06-unity-integration.md). In short: create a
Unity 6 project, install **[aras-p/UnityGaussianSplatting](https://github.com/aras-p/UnityGaussianSplatting)**,
import the produced `.ply`, drop in our `unity/Assets/Scripts`, press Play.

## 5. Status / honesty box

| Component | State | Needs |
|---|---|---|
| Backend API + job queue + SSE | ✅ runnable | Python only |
| Agent planner (Claude tool-use) | ✅ runnable; ⚙️ falls back to deterministic mock without API key | `ANTHROPIC_API_KEY` for the LLM path |
| Pipeline DAG + stage contracts | ✅ runnable in **mock mode** (synthetic outputs) | — |
| COLMAP / 3DGS training stages | ⚙️ real subprocess wrappers, **gated behind installed tools** | CUDA GPU, COLMAP, Inria 3DGS repo |
| Frontend dashboard | ✅ runnable | browser |
| Unity interaction scripts | ✅ written; integration points marked | Unity 6 + aras-p plugin |
| Mip-Splatting / 2DGS / Relighting / VR | 📋 documented as extensions | see `docs/07-extensions.md` |

**Single image vs. many:** vanilla 3DGS needs *multiple overlapping views* for
COLMAP to recover camera poses. **Multi-image is the supported MVP path.**
True single-image reconstruction needs a generative image-to-3D model and is
scoped as a stretch goal in `docs/07-extensions.md` — we don't fake it.

## 6. Team, timeline & where to start

| Member | Owns | Primary dirs |
|---|---|---|
| 许可 Xu Ke | Agent orchestration + 3DGS setup | `backend/app/agent`, `backend/app/pipeline`, `third_party` |
| 郑宇轩 Zheng Yuxuan | Unity scene import/organization + rendering optimization | `unity/`, `docs/06`, `docs/07` |
| 朱越 Zhu Yue | Frontend interface + interaction | `frontend/`, `unity/Assets/Scripts` (UI/interaction) |

**Week 13–14** basic pipeline · **Week 15** optimization + extensions · **Week 16** demo.
Detailed, checkbox-tracked plan: [`docs/01-roadmap.md`](docs/01-roadmap.md).

**Where to start right now:** read [`docs/04-getting-started.md`](docs/04-getting-started.md),
get one public 3DGS scene rendering in Unity (closes the *last* mile first so the
team always has a demo), then connect the backend pipeline behind it.

## 7. License & credits

Our original code is MIT (see [`LICENSE`](LICENSE)). This project **orchestrates**
third-party research code with **different, sometimes non-commercial licenses** —
read [`third_party/README.md`](third_party/README.md) before redistributing.
Key upstreams: Inria 3DGS, Mip-Splatting, 2D Gaussian Splatting, Relightable 3D
Gaussian, aras-p UnityGaussianSplatting, clarte53 VR viewer. Full citations in
[`docs/03-tech-research.md`](docs/03-tech-research.md).
