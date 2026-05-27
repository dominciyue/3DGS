# 07 · Advanced Extensions (Stretch Goals)

These are the proposal's "进阶成果". **None block the baseline (M1).** Each is an
*alternate or additional* pipeline backend the Agent can select, or a Unity-side
feature. Pick **one or two** for M2 (Week 15) — don't spread thin.

Difficulty / payoff at a glance:

| Extension | Effort | Where it changes things | Recommended? |
|---|---|---|---|
| **Mip-Splatting** (anti-aliasing) | 🟢 low–med | `train` backend + Unity render | ⭐ best first extension |
| **VR viewer** | 🟡 med | swap Unity viewer (clarte53) | ⭐ great demo if hardware allows |
| **2DGS** (surfaces/mesh) | 🟡 med | `train` backend + converter/viewer | strong if you want geometry/mesh |
| **Relightable 3DGS** | 🔴 high | `train` + render path | most impressive, most work |
| **Single-image generative** | 🔴 high | new front stage (generative) | research-y; only if time |

---

## A. Mip-Splatting — anti-aliasing  ⭐ start here

**What:** alias-free 3DGS that stays stable across zoom/resolution (`docs/03 §3.3`).

**Integration:** add a trainer backend. Clone
`https://github.com/autonomousvision/mip-splatting` into `third_party/`; it's a
near-drop-in fork of the Inria trainer, so `train.py` gains
`backend="mip"` → run the mip trainer instead of vanilla. Output is still a `.ply`
the aras-p importer reads. The Agent selects it when the user asks for
"anti-aliased / stable when zoomed out / no shimmering."

**Demo:** side-by-side vanilla vs. mip at a far zoom — the shimmer difference sells it.

---

## B. VR viewing  ⭐ (if you have the hardware)

**What:** view/walk the scene in a headset.

**Integration:** swap the Unity viewer for
`https://github.com/clarte53/GaussianSplattingVRViewerUnity` (Unity 2022, OpenXR +
DX11, native CUDA rasterizer, **> RTX 4070**, headset as default OpenXR runtime). Keep
the same `.ply` contract. Our `OrbitCameraController` is desktop-only, so VR uses the
viewer's XR rig; `SplatSceneManager`/selection concepts still apply.

**Stretch within stretch — interaction:** VR-GS (`docs/03 §3.6`) does physics-aware
grab/deform via a deformable cage around groups of Gaussians. A *lite* version:
select a splat group (bounds proxy) and move/scale it with the controller.

---

## C. 2D Gaussian Splatting — surfaces & mesh

**What:** disk-based primitives → clean normals + mesh extraction (`docs/03 §3.4`).

**Integration:** add `backend="2dgs"` to `train` (clone
`https://github.com/hbb1/2d-gaussian-splatting`). Its `.ply` semantics differ from 3D
Gaussians, so it needs its **own viewer/converter** — either use the 2DGS repo's
renderer, or extract a mesh (TSDF) and import that as a normal Unity mesh. Decide the
target (splat surfels vs. exported mesh) before starting.

**Demo:** show extracted geometry/normals — crisp flat surfaces where vanilla 3DGS is
fuzzy.

---

## D. Relightable 3D Gaussian — relighting

**What:** per-Gaussian BRDF + normals + baked light → relight under new lighting
(`docs/03 §3.5`).

**Two tiers:**
- **Full:** train with `https://github.com/NJU-3DV/Relightable3DGaussian`
  (`backend="relight"`); needs its custom render path in Unity → heaviest option.
- **Approximate (lighter, recommended fallback):** estimate normals for the splats and
  apply a simple BRDF + a movable light in a custom Unity shader over the existing
  `.ply`. Not physically exact, but demonstrates "approximate relighting" (which the
  proposal explicitly allows) at a fraction of the cost.

---

## E. Single-image reconstruction (generative)

**What:** one photo → 3D, which vanilla 3DGS/COLMAP **cannot** do (needs multiple
views; `docs/03 §3.7`).

**Integration:** a new *front* stage before COLMAP — a generative image-to-3D model
(image/video-diffusion to synthesize novel views, then run the normal pipeline; or a
feed-forward image→3DGS model). This is a research effort; attempt only with spare
time, and keep it isolated so it never destabilizes the multi-image baseline.

---

## How the Agent chooses an extension

The `train.backend` field in `PipelineConfig` (`docs/05`) is the switch. The Agent
maps user phrasing → backend:

| User says… | Agent picks |
|---|---|
| "anti-aliased", "stable when far", "no flicker" | `mip` |
| "I want the surface / a mesh / flat walls clean" | `2dgs` |
| "relight it", "change the lighting" | `relight` (or approximate path) |
| (default) | `vanilla` |

Each backend must be installed in `third_party/` and enabled via `backend/.env`;
otherwise the stage reports a clear "backend not installed" error and the Agent falls
back to `vanilla`.
