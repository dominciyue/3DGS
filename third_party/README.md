# third_party — 上游组件（未纳入仓库）

本项目**编排**多个研究仓库，而非将其源码复制进来。我们不在此提交其源码（参见仓库 `.gitignore`：`third_party/*/` 已被忽略，仅保留本 README）。按需克隆，然后通过 `backend/.env` 将后端指向对应路径（参见 `backend/.env.example`）。

## 配置

```bash
cd third_party

# Base trainer (required for real reconstruction)
git clone https://github.com/graphdeco-inria/gaussian-splatting --recursive

# Optional extension backends (see docs/07)
git clone https://github.com/autonomousvision/mip-splatting        # anti-aliasing
git clone https://github.com/hbb1/2d-gaussian-splatting            # surfaces/mesh
git clone https://github.com/NJU-3DV/Relightable3DGaussian         # relighting
```

然后在 `backend/.env` 中配置：

```
COLMAP_BIN=/usr/bin/colmap
GS_REPO_DIR=../third_party/gaussian-splatting
GS_PYTHON=/path/to/conda/envs/gaussian_splatting/bin/python
# MIP_REPO_DIR=../third_party/mip-splatting
# DGS2_REPO_DIR=../third_party/2d-gaussian-splatting
# RELIGHT_REPO_DIR=../third_party/Relightable3DGaussian
```

Unity 查看器位于 Unity 项目中，不在此处：
- 主要版本：https://github.com/aras-p/UnityGaussianSplatting（参见 `docs/06`）
- VR 版本：https://github.com/clarte53/GaussianSplattingVRViewerUnity（参见 `docs/07`）

## ⚠️ 许可证——再分发前请仔细阅读

这些均为**各自独立的作品，采用其自身的许可证**，其中多项为**非商业 / 仅限研究**用途。我们的 MIT `LICENSE` **不涵盖**这些组件。

| 组件 | 许可证（请核实上游） |
|---|---|
| Inria `gaussian-splatting` | **Gaussian-Splatting License — 仅限研究 / 非商业用途** |
| Mip-Splatting | 源自 Inria；仅限研究/非商业——请查阅仓库 |
| 2D Gaussian Splatting | 请查阅仓库 LICENSE |
| Relightable 3D Gaussian | 请查阅仓库 LICENSE |
| aras-p/UnityGaussianSplatting | MIT（但其中包含 3DGS 概念；使用 Inria 训练器生成的数据仍受 Inria 条款约束） |
| clarte53 VR 查看器 | 请查阅仓库 LICENSE；封装了 Inria CUDA 光栅化器 |
| COLMAP | BSD |

对于课程项目而言，这完全可行（研究/教育用途）。**未满足各上游许可证要求（尤其是 Inria 的非商业条款）前，请勿将训练模型或本流水线用于商业用途。**
