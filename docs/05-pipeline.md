# 05 · 重建流水线

该流水线是一个由类型化阶段组成的**确定性有向无环图（DAG）**。Agent 只负责选择 `PipelineConfig`；运行器按顺序执行各阶段。每个阶段从上一阶段的输出目录读取数据，并将结果写入自己的目录，路径为 `data/jobs/<id>/`。

```
input/ ─► preprocess ─► colmap ─► train ─► convert ─► package ─► result/model.ply
```

每个阶段均具备**幂等**性（可安全重复执行）、**已校验**（检查输入是否存在、输出是否格式正确）、**可重试**，以及**可 mock**（`PIPELINE_MOCK=1` → 合成输出，无需外部工具）的特性。

## 作业工作目录结构

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

## 各阶段说明

### 1. `preprocess` (`pipeline/preprocess.py`)
- **输入：** `input/*.{jpg,png,...}` · **输出：** `preprocess/images/*`
- **功能：** 校验图片数量与格式，去除可能导致问题的 EXIF 旋转信息，可选择将图片缩放至目标最大边长，并规范化文件名。若图片数量 `< 20` 则发出警告（COLMAP 通常需要更多），若恰好只有 1 张图片也发出警告（多视角流程无法继续——参见 `docs/03` 中的单图说明）。
- **外部工具：** 无必须依赖（Pillow 为可选，用于缩放）。

### 2. `colmap` (`pipeline/colmap.py`)
- **输入：** `preprocess/images/` · **输出：** `colmap/sparse/0/` + 去畸变后的 `images/`
- **功能：** 运动恢复结构(SfM) → 相机内外参数 + 稀疏点云。流程参照 Inria 的 `convert.py`：`feature_extractor → exhaustive_matcher → mapper → image_undistorter`。
- **外部工具：** **COLMAP**（`COLMAP_BIN`）。GPU 可选（CPU 模式使用 `--SiftExtraction.use_gpu 0 --SiftMatching.use_gpu 0`）。
- **校验：** `sparse/0/` 中至少存在一个重建模型，且已注册的图片占比达到合理比例。

### 3. `train` (`pipeline/train.py`)
- **输入：** `colmap/`（位姿 + 稀疏点云 + 图片） · **输出：**
  `train/point_cloud/iteration_<N>/point_cloud.ply`
- **功能：** 运行 Inria 训练器（`train.py -s <colmap> -m <out>`）。配置项包括迭代次数（如 7k 预览 vs 30k 完整）、分辨率 `-r`、SH 阶数，以及**所用训练后端**（原版 3DGS vs **Mip-Splatting** vs **2DGS**——参见 `docs/07`）。
- **外部工具：** Inria 仓库（`GS_REPO_DIR`，`GS_PYTHON`）+ CUDA GPU。
- **校验：** 预期的 `.ply` 文件存在且可正常解析。

### 4. `convert` (`pipeline/convert.py`)
- **输入：** 已训练的 `.ply` · **输出：** `convert/model.ply`
- **功能：** 定位迭代次数最高的 `.ply`，验证其为*高斯*格式的 `.ply`（含 Unity 导入器所需的逐高斯属性），并可选择压缩/抽稀（限制高斯点（splat）数量，或输出 SPZ 格式）以提升引擎性能。
- **外部工具：** 基本的复制+校验无需外部工具；可选压缩器。
- **存在意义：** Unity 在导入非高斯格式的 `.ply` 时会失败（"PLY is probably not a Gaussian Splat file"）。该阶段是进入引擎前的兼容性门控。

### 5. `package` (`pipeline/package.py`)
- **输入：** `convert/model.ply` · **输出：** `result/model.ply` + `result/manifest.json`
- **功能：** 完成最终交付物的打包，写入清单(manifest)文件（包含所用配置、各阶段耗时、高斯点（splat）数量、文件大小、sha256），供前端展示统计信息，并使 Unity 导入过程可复现。
- **外部工具：** 无。

## `PipelineConfig`（Agent 填写的内容）

```jsonc
{
  "preset": "preview | balanced | high",   // 粗粒度的质量/速度调节旋钮
  "max_image_edge": 1600,                   // preprocess 缩放的最大边长（像素），或 null
  "colmap": { "use_gpu": true, "matcher": "exhaustive" },
  "train": {
    "backend": "vanilla | mip | 2dgs",      // 选择训练后端（mip = 抗锯齿）
    "iterations": 30000,
    "resolution": 1,                         // Inria -r
    "sh_degree": 3
  },
  "convert": { "max_splats": null, "emit_spz": false },
  "notes": "Agent 留给人类的自由文本备注"
}
```

预设会展开为具体数值（例如 `preview` → 7k 次迭代，`-r 2`，开启 GPU）。Agent 根据用户指令选择预设并进行微调；其余内容由运行器强制执行。配置在运行前经过校验（pydantic）。

## 事件（前端流式接收的内容）

每个阶段通过 SSE 发送以下事件：
`stage_started`、`stage_progress {pct, message}`、`stage_log {line}`、
`stage_finished {artifacts}`，以及终态事件 `job_finished {status}` /
`job_failed {stage, error}`。mock 运行器以模拟时序发送相同的事件，因此 UI 可在完全离线的状态下进行开发。

## 失败与重试

若某阶段抛出异常，将按指数退避重试最多 `STAGE_MAX_RETRIES` 次（默认 1 次）。最终失败后，该作业状态变为 `failed`，出错阶段及日志均会被记录；当 LLM Agent 处于激活状态时，规划器会收到错误信息，从而*调整配置并提出一次有限制的重试*——例如将 COLMAP 切换为 CPU 模式、在 OOM 时降低分辨率。重试只改变配置，不改变阶段的*逻辑*。
