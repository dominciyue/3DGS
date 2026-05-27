# 00 · Project Overview

## Goal

Build an **Agent-driven system that turns images into an interactive 3D Gaussian
Splatting scene inside Unity**. The user provides photos through a web UI; an LLM
Agent automatically schedules 3DGS reconstruction, format conversion, scene
organization, render optimization, and Unity import; the output is a scene the
user can browse, zoom, move, select, and tune in Unity.

This is the system described in our 开题答辩 (proposal defense) and the 13组 slide
deck (both archived in [`assets/`](assets/)).

## The one-paragraph pitch

3DGS represents a scene as millions of colored, oriented 3D Gaussian "blobs"
instead of a mesh, a voxel grid, or a NeRF MLP. It renders in real time on a GPU
(rasterization, no per-pixel neural net), which makes it a great fit for Unity and
VR. But producing a 3DGS scene from raw photos is *not* one click — it is a
multi-tool pipeline (image prep → COLMAP camera estimation → Gaussian training →
format conversion → engine import → scene wiring). We use an **Agent** to drive
that pipeline from a single natural-language request, and Unity to make the result
interactive.

## Why each piece exists

| Piece | Why it's here |
|---|---|
| **3DGS** | Recovers 3D geometry + appearance from photos; renders in real time; engine/VR-friendly. |
| **COLMAP / SfM** | 3DGS needs per-image camera poses + a sparse point cloud to initialize from. COLMAP produces both. |
| **Agent** | Chains the tools, picks parameters, decides on optional stages, recovers from errors — from one NL request. |
| **Unity** | Turns a static `.ply` into an interactive experience (camera control, selection, parameter tuning, eventually VR). |

## Glossary (terms used across the docs)

- **3DGS / Gaussian Splatting** — scene = set of 3D Gaussians, each with position,
  covariance (≈ orientation + scale), opacity, and view-dependent color (spherical
  harmonics). Rendered by projecting ("splatting") each Gaussian to the image and
  alpha-blending front-to-back.
- **SfM (Structure-from-Motion)** — recovering camera poses + sparse 3D points from
  overlapping images. We use **COLMAP**.
- **`.ply`** — the file the Inria trainer writes (`point_cloud/iteration_30000/
  point_cloud.ply`); it stores per-Gaussian attributes. This is the artifact we move
  into Unity.
- **Densification / pruning** — during training, Gaussians are split/cloned in
  under-reconstructed regions and removed where transparent, controlling detail.
- **Mip-Splatting** — anti-aliasing variant: scale-aware filtering so the scene stays
  stable across zoom levels (no shimmering when far away).
- **2DGS** — replaces 3D ellipsoids with oriented 2D disks → better surfaces/meshes.
- **Relightable 3DGS** — bakes material/normal/lighting so the scene can be relit.
- **Splat / SPZ** — compact binary formats for Gaussian models (SPZ = Scaniverse's
  compressed format; supported by the aras-p Unity importer).

## Success criteria (from the proposal)

**Baseline (must-have):** an end-to-end pipeline — *input images → a 3DGS scene
loadable & interactive in Unity*, with basic browse / zoom / move / select /
display-parameter interactions.

**Advanced (stretch):** relighting or approximate relighting; Mip-Splatting /
anti-aliasing; 2DGS planar/surface representation; VR viewing.

**Deliverables:** a Unity demo, a frontend task UI, an Agent backend scheduler, and
a handful of example scenes reconstructed from input photos.

## Read next

- New to the codebase? → [`04-getting-started.md`](04-getting-started.md)
- Want the plan & who-does-what? → [`01-roadmap.md`](01-roadmap.md)
- Want the design rationale? → [`02-architecture.md`](02-architecture.md)
