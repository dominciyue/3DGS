# third_party — upstream components (NOT vendored)

This project **orchestrates** several research repos rather than copying them in. We
do not commit their source here (see the repo `.gitignore`: `third_party/*/` is
ignored, this README is kept). Clone what you need, then point the backend at it via
`backend/.env` (see `backend/.env.example`).

## Setup

```bash
cd third_party

# Base trainer (required for real reconstruction)
git clone https://github.com/graphdeco-inria/gaussian-splatting --recursive

# Optional extension backends (see docs/07)
git clone https://github.com/autonomousvision/mip-splatting        # anti-aliasing
git clone https://github.com/hbb1/2d-gaussian-splatting            # surfaces/mesh
git clone https://github.com/NJU-3DV/Relightable3DGaussian         # relighting
```

Then in `backend/.env`:

```
COLMAP_BIN=/usr/bin/colmap
GS_REPO_DIR=../third_party/gaussian-splatting
GS_PYTHON=/path/to/conda/envs/gaussian_splatting/bin/python
# MIP_REPO_DIR=../third_party/mip-splatting
# DGS2_REPO_DIR=../third_party/2d-gaussian-splatting
# RELIGHT_REPO_DIR=../third_party/Relightable3DGaussian
```

Unity viewers live in the Unity project, not here:
- Primary: https://github.com/aras-p/UnityGaussianSplatting (see `docs/06`)
- VR: https://github.com/clarte53/GaussianSplattingVRViewerUnity (see `docs/07`)

## ⚠️ Licenses — read before redistributing

These are **separate works under their own licenses**, several **non-commercial /
research-only**. Our MIT `LICENSE` does **not** cover them.

| Component | License (verify upstream) |
|---|---|
| Inria `gaussian-splatting` | **Gaussian-Splatting License — research / NON-COMMERCIAL only** |
| Mip-Splatting | Inria-derived; research / non-commercial — check repo |
| 2D Gaussian Splatting | check repo LICENSE |
| Relightable 3D Gaussian | check repo LICENSE |
| aras-p/UnityGaussianSplatting | MIT (but it embeds 3DGS concepts; data you make with the Inria trainer still carries the Inria terms) |
| clarte53 VR viewer | check repo LICENSE; wraps the Inria CUDA rasterizer |
| COLMAP | BSD |

For a course project this is fine (research/educational use). **Do not ship the
trained models or this pipeline commercially** without satisfying each upstream
license, especially Inria's non-commercial clause.
