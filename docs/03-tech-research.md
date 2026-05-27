# 03 · Technology Research / Literature Survey

A grounded survey of the methods this project uses or can extend, with the
practical takeaway for our system. Citations and repos at the bottom.

## 3.1 Why not mesh / voxel / NeRF — and why 3DGS

| Representation | Idea | Problem for us |
|---|---|---|
| **Mesh** | triangles + vertices | hard to auto-generate from photos; thin/fuzzy detail (hair, foliage) lost |
| **Voxel** | space cut into cubes | memory blows up; resolution-limited |
| **NeRF** | an MLP maps (position, direction) → (color, density) | a neural net runs *per pixel* → slow to render; not real-time-engine friendly |
| **3DGS** | scene = explicit set of 3D Gaussians, rasterized | real-time on GPU, high quality, **engine/VR friendly** ✅ |

3DGS keeps NeRF-level quality while rendering by **rasterization** (no per-pixel
network), which is exactly why it suits Unity and VR.

## 3.2 3D Gaussian Splatting (the base method)

**Kerbl et al., SIGGRAPH 2023 — "3D Gaussian Splatting for Real-Time Radiance Field
Rendering."** Each Gaussian carries: position (mean), covariance (orientation +
scale), opacity, and view-dependent color as **spherical harmonics**. Rendering =
project ("splat") each Gaussian to a 2D ellipse and alpha-blend front-to-back —
fully differentiable, so the scene is optimized by comparing renders to the input
photos via gradient descent. **Adaptive density control** clones/splits Gaussians in
under-reconstructed areas and prunes near-transparent ones.

**Pipeline (what our backend automates):**

```
RGB images ─► COLMAP SfM (poses + sparse cloud) ─► init Gaussians from points
           ─► differentiable splat-rasterize ─► photometric loss + backprop
           ─► densify / prune ─► (repeat ~30k iters) ─► point_cloud.ply
```

**Practical facts (verified):** needs a CUDA GPU (compute ≥ 7.0; ~24 GB VRAM for
full quality, less with tweaks); needs **COLMAP** + **ImageMagick** to process your
own images (`convert.py`); on 50-series GPUs use CUDA 12.8+/Python 3.11. Output is a
`.ply` under `output/<name>/point_cloud/iteration_30000/`.

> **Takeaway:** this is our backbone. The trainer's `.ply` is the artifact we move
> into Unity. The heavy requirement (GPU) is why the backend gates the train stage
> and why we keep a public `.ply` for demos.

## 3.3 Mip-Splatting — anti-aliasing (advanced track)

**Yu et al., CVPR 2024.** Plain 3DGS shimmers/aliases when you zoom out or change
resolution, because tiny Gaussians are sampled unstably. Mip-Splatting adds a **3D
smoothing filter** (bounds each Gaussian's frequency by the sampling rate seen during
training) and a **2D mip filter** (a screen-space box filter replacing the dilated 2D
Gaussian). Result: stable, alias-free rendering across scales.

> **Takeaway:** our most natural quality extension. The Agent can choose to train
> with the Mip-Splatting variant when the user asks for "anti-aliased / stable at
> distance." Plan it as an alternate `train` backend. See `docs/07`.

## 3.4 2D Gaussian Splatting — surfaces (advanced track)

**Huang et al., SIGGRAPH 2024.** Replaces 3D ellipsoids with oriented **2D disks
(surfels)**. Each primitive defines a local tangent plane, giving view-consistent
geometry and clean **normals**, enabling high-quality **surface/mesh extraction**
(via TSDF fusion) that 3D Gaussians struggle with.

> **Takeaway:** the route if we want planar/surface representation or to export a
> mesh for the engine. Different `.ply` semantics → needs its own viewer/converter;
> scope carefully. See `docs/07`.

## 3.5 Relightable 3D Gaussian (advanced track)

**NJU-3DV, "Relightable 3D Gaussian."** Augments each Gaussian with BRDF material
params + normals and bakes incident light (with ray-traced visibility), so the scene
can be **relit** under novel lighting and supports material editing.

> **Takeaway:** satisfies the "relighting / approximate relighting" stretch goal. It
> changes both training and the rendering path, so it's the heaviest extension; an
> *approximate* relight in Unity (estimate normals + a simple BRDF over the splats)
> is a lighter fallback. See `docs/07`.

## 3.6 Bringing 3DGS into Unity

### aras-p / UnityGaussianSplatting — **our primary path**
By Aras Pranckevičius (ex-Unity). Imports the original 3DGS `.ply` (and Scaniverse
**SPZ**) directly — in recent (2.x) versions you **drag the `.ply` into the project**
and a custom importer builds a `GaussianSplatAsset`; GPU-accelerated sorting; runs on
**Unity 6 LTS**, PC/Mac/mobile; **no runtime CUDA** required. It includes editing
tooling and quality-vs-size compression options.

> **Takeaway:** the pragmatic choice for the required interactions (browse/zoom/
> move/select/params) on ordinary hardware. We build the demo on this.

### clarte53 / GaussianSplattingVRViewerUnity — **VR stretch path**
Wraps the original **CUDA differential rasterizer** as a Unity native plugin for an
**OpenXR** VR viewer (Unity 2022, DirectX11). Recommends **> RTX 4070**; also runs
without OpenXR. Highest fidelity, heaviest requirements (runtime CUDA + headset).

> **Takeaway:** reserve for the VR stretch goal once the desktop demo is solid.

### Reference / inspiration
- **SIBR + OpenXR** (Inria `sibr_core`, `gaussian_code_release_openxr`) — the original
  research-grade viewer; reference for VR rendering behavior.
- **VR-GS** (SIGGRAPH 2024) — physics-aware *interactive* 3DGS in VR (XPBD on a cage
  around groups of Gaussians). North star for "grab/deform an object" interaction —
  far beyond our baseline, but a great direction for advanced selection/manipulation.

## 3.7 The single-image question (be honest)

COLMAP SfM needs **multiple overlapping views** to triangulate poses + points.
**One photo cannot drive vanilla 3DGS.** Single-image → 3D requires a *generative*
model (image/video diffusion to synthesize views, or feed-forward image-to-3D).
We therefore make **multi-image the supported MVP**, and list single-image as a
clearly-scoped generative stretch goal in `docs/07` — we don't pretend the base
trainer does it.

## References

- **3DGS** — Kerbl, Kopanas, Leimkühler, Drettakis. SIGGRAPH 2023.
  https://github.com/graphdeco-inria/gaussian-splatting ·
  project: https://repo-sam.inria.fr/fungraph/3d-gaussian-splatting/
- **Mip-Splatting** — Yu et al., CVPR 2024. https://github.com/autonomousvision/mip-splatting
- **2D Gaussian Splatting** — Huang et al., SIGGRAPH 2024. https://github.com/hbb1/2d-gaussian-splatting
- **Relightable 3D Gaussian** — NJU-3DV. https://github.com/NJU-3DV/Relightable3DGaussian
- **VR-GS** — Jiang et al., SIGGRAPH 2024. "A Physical Dynamics-Aware Interactive
  Gaussian Splatting System in Virtual Reality."
- **Unity viewer (primary)** — https://github.com/aras-p/UnityGaussianSplatting
- **Unity VR viewer** — https://github.com/clarte53/GaussianSplattingVRViewerUnity
- **SIBR OpenXR** — https://gitlab.inria.fr/sibr/sibr_core/-/tree/gaussian_code_release_openxr
- **COLMAP** — Schönberger & Frahm, CVPR 2016. https://colmap.github.io/
