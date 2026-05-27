# 03 · 技术调研 / 文献综述

本文对项目所使用或可扩展的方法进行有据可查的综述，并给出对我们系统的实际启示。
引用文献与代码仓库见文末。

## 3.1 为何不用网格 / 体素 / NeRF，而选择 3DGS

| 表示方法 | 基本思路 | 对我们的问题 |
|---|---|---|
| **网格（Mesh）** | 三角面 + 顶点 | 难以从照片自动生成；细薄/模糊的细节（毛发、植被）容易丢失 |
| **体素（Voxel）** | 将空间切割为立方体 | 内存占用爆炸；分辨率受限 |
| **NeRF** | 用 MLP 将（位置、方向）映射为（颜色、密度） | 神经网络*逐像素*执行 → 渲染慢；不适合实时引擎 |
| **3DGS** | 场景 = 一组显式 3D 高斯，经光栅化渲染 | GPU 实时渲染，质量高，**引擎/VR 友好** ✅ |

3DGS 在保持 NeRF 级别质量的同时，通过**光栅化**（无逐像素网络）进行渲染，
这正是它适用于 Unity 和 VR 的原因。

## 3.2 3D 高斯泼溅（3DGS）（基础方法）

**Kerbl et al., SIGGRAPH 2023 — "3D Gaussian Splatting for Real-Time Radiance Field
Rendering."** 每个高斯携带：位置（均值）、协方差（朝向 + 缩放）、不透明度，以及以
**球谐函数(SH)** 表示的视角相关颜色。渲染 = 将每个高斯投影（"splat"）为 2D 椭圆并
从前到后进行 alpha 混合——全程可微分，因此通过将渲染结果与输入照片对比、使用梯度下降
来优化场景。**自适应致密化**在重建不足的区域克隆/分裂高斯，并剪除接近透明的高斯点。

**流水线（我们的后端自动化的内容）：**

```
RGB images ─► COLMAP SfM (poses + sparse cloud) ─► init Gaussians from points
           ─► differentiable splat-rasterize ─► photometric loss + backprop
           ─► densify / prune ─► (repeat ~30k iters) ─► point_cloud.ply
```

**实际情况（已验证）：** 需要 CUDA GPU（计算能力 ≥ 7.0；完整质量约需 24 GB VRAM，
调整参数可适当降低）；处理自己的图像需要 **COLMAP** + **ImageMagick**（`convert.py`）；
在 50 系 GPU 上请使用 CUDA 12.8+/Python 3.11。输出为 `.ply` 文件，位于
`output/<name>/point_cloud/iteration_30000/`。

> **启示：** 这是我们的核心骨干。训练器输出的 `.ply` 是移交给 Unity 的产物。
> 对 GPU 的高要求是后端对训练阶段设置门控的原因，也是我们为演示保留一份公开
> `.ply` 的原因。

## 3.3 Mip-Splatting — 抗锯齿（进阶方向）

**Yu et al., CVPR 2024.** 原始 3DGS 在缩小或改变分辨率时会出现闪烁/锯齿，原因是
微小高斯的采样不稳定。Mip-Splatting 添加了一个 **3D 平滑滤波器**（将每个高斯的频率
上界限定为训练时所见的采样率）以及一个 **2D mip 滤波器**（用屏幕空间方框滤波器替代
膨胀后的 2D 高斯）。结果：跨尺度的渲染稳定、无锯齿。

> **启示：** 这是我们最自然的质量扩展方向。当用户要求"抗锯齿/远处稳定"时，
> Agent 可以选择使用 Mip-Splatting 变体进行训练。计划将其作为备用 `train` 后端。
> 详见 `docs/07`。

## 3.4 2D 高斯泼溅 — 表面重建（进阶方向）

**Huang et al., SIGGRAPH 2024.** 将 3D 椭球替换为有方向的 **2D 圆盘（面元/surfel）**。
每个基元定义一个局部切平面，提供视角一致的几何形状和清晰的**法线**，从而支持
高质量的**表面/网格提取**（通过 TSDF 融合），而这正是 3D 高斯所难以实现的。

> **启示：** 如果我们需要平面/表面表示，或需要为引擎导出网格，这是可行的方案。
> 不同的 `.ply` 语义意味着需要专用的查看器/转换器；范围需谨慎界定。详见 `docs/07`。

## 3.5 可重光照 3D 高斯（进阶方向）

**NJU-3DV, "Relightable 3D Gaussian."** 为每个高斯增加 BRDF 材质参数与法线，并烘焙
入射光（带光线追踪可见性），使场景可在新光照条件下进行**重光照**并支持材质编辑。

> **启示：** 满足"重光照/近似重光照"扩展目标。由于同时改变训练和渲染路径，这是
> 最重的扩展方案；在 Unity 中进行*近似*重光照（估计法线 + 在高斯点上应用简单 BRDF）
> 是较轻量的备选方案。详见 `docs/07`。

## 3.6 将 3DGS 引入 Unity

### aras-p / UnityGaussianSplatting — **我们的主要路径**
由 Aras Pranckevičius（前 Unity 员工）开发。直接导入原始 3DGS 的 `.ply`（以及 Scaniverse
**SPZ**）——在近期（2.x）版本中，你**将 `.ply` 拖入项目**，自定义导入器即会构建
`GaussianSplatAsset`；支持 GPU 加速排序；运行于 **Unity 6 LTS**，支持 PC/Mac/移动端；
**无需运行时 CUDA**。还包含编辑工具和质量/大小压缩选项。

> **启示：** 在普通硬件上实现所需交互（浏览/缩放/移动/选择/参数调整）的务实选择。
> 我们的演示基于此构建。

### clarte53 / GaussianSplattingVRViewerUnity — **VR 扩展路径**
将原始 **CUDA 差分光栅化器** 封装为 Unity 原生插件，构建 **OpenXR** VR 查看器
（Unity 2022，DirectX11）。推荐使用 **RTX 4070 以上** 的显卡；也可在无 OpenXR 的情况下
运行。保真度最高，硬件要求最重（需要运行时 CUDA + 头显）。

> **启示：** 桌面演示稳定后，保留作为 VR 扩展目标。

### 参考 / 启发来源
- **SIBR + OpenXR**（Inria `sibr_core`，`gaussian_code_release_openxr`）——原始研究级
  查看器；VR 渲染行为的参考。
- **VR-GS**（SIGGRAPH 2024）——基于物理的*交互式* 3DGS VR 系统（对高斯群组的包围笼
  应用 XPBD）。"抓取/形变物体"交互的北极星——远超我们的基线，但为高级选择/操控
  提供了很好的方向。

## 3.7 单张图像的问题（如实说明）

COLMAP SfM 需要**多张有重叠的视角**来三角化位姿 + 点云。
**一张照片无法驱动原始 3DGS。** 单图 → 三维需要*生成式*模型
（图像/视频扩散以合成多视角，或前向传播的图像到三维网络）。
因此我们将**多图作为支持的 MVP**，并在 `docs/07` 中将单图明确列为范围界定清晰的
生成式扩展目标——我们不假装基础训练器能做到这一点。

## 参考文献

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
