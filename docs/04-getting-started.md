# 04 · 快速入门（环境配置）

共有**三个相互独立的环境**。你**不需要**全部配置好才能开始贡献代码——根据你的分工选择对应的环境，其余部分使用 mock 模式（占位/模拟）即可。

| 环境 | 对应成员 | 是否需要 GPU？ |
|---|---|---|
| A. 后端 + 前端（mock 流水线） | 所有人 | ❌ 不需要 |
| B. 真实 3DGS 重建（COLMAP + Inria 训练器） | 许可 | ✅ 需要 CUDA GPU |
| C. Unity 查看器 | 郑宇轩, 朱越 | 🟡 需要性能较好的 GPU，无需 CUDA |

---

## A. 后端 + 前端——在任何机器上均可运行（从这里开始）

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

将 `PIPELINE_MOCK=1`（默认值）时，流水线会生成一个合成的 `.ply` 文件，让你可以走完整个流程——上传 → Agent 规划 → 分阶段进度展示 → 下载——而无需 GPU。这已足够用于开发和测试 API、Agent 和 UI。

**LLM 密钥（可选）：** 不设置 `ANTHROPIC_API_KEY` 时，Agent 使用确定性的 `MockPlanner`；设置后则使用 Claude tool-use。无论哪种方式，流水线本身保持不变。

---

## B. 真实 3DGS 重建——需要 CUDA

依赖要求（已在 Inria 仓库验证）：支持 CUDA 的 GPU（**算力 ≥ 7.0**，**~24 GB VRAM** 以获得完整质量；使用较小的批次/分辨率时可适当降低），以及 **COLMAP** 和 **ImageMagick**。

### 1. COLMAP
- Linux：`sudo apt install colmap`（或从源码编译以启用 CUDA 特性）。
- Windows：从 https://colmap.github.io/ 下载预编译二进制文件并添加到 PATH。
- 验证：`colmap -h`。如果特征提取不支持 GPU，convert 步骤可传入
  `--SiftExtraction.use_gpu 0 --SiftMatching.use_gpu 0`（速度较慢，仅使用 CPU）。

### 2. Inria 3DGS 训练器（克隆至 `third_party/`，不作为内嵌依赖）
```bash
cd third_party
git clone https://github.com/graphdeco-inria/gaussian-splatting --recursive
cd gaussian-splatting
conda env create --file environment.yml     # creates the 'gaussian_splatting' env
conda activate gaussian_splatting
# Newer 40/50-series GPUs: use CUDA 12.x + Python 3.11 and install the matching
# torch/submodules if environment.yml fails — see the repo's issues.
```

### 3. 端到端冒烟测试（使用一个已知可行的场景）
```bash
# (a) prepare your own images -> COLMAP poses + sparse cloud
python convert.py -s /path/to/scene          # scene/input/*.jpg  ->  scene/sparse/0/, images/

# (b) train
python train.py -s /path/to/scene -m /path/to/output/scene

# (c) result:
#   /path/to/output/scene/point_cloud/iteration_30000/point_cloud.ply
```

通过在 `backend/.env` 中设置 `COLMAP_BIN`、`GS_REPO_DIR` 和 `GS_PYTHON`（参见 `.env.example`），将后端指向这些工具。`train`/`colmap` 阶段随后会调用它们；否则将保持 mock 模式（占位/模拟）。

**拍摄技巧（以获得良好效果）：** 30–200 张照片，大量重叠（约 70–80%），在 2–3 个高度环绕拍摄对象，光线均匀，避免运动模糊以及反光/透明表面。垃圾输入 → 垃圾高斯点（splat）。

---

## C. Unity 查看器——需要 Unity 6（无需 CUDA）

1. 安装 **Unity 6 LTS**（Unity Hub）。
2. 创建一个 3D（URP 或 Built-in）项目，或在创建项目后打开 `unity/`（仅跟踪 `Assets/`、`Packages/`、`ProjectSettings/`——详见 `.gitignore`）。
3. 安装 **aras-p/UnityGaussianSplatting**（Package Manager → Add from git URL，或克隆后添加本地包）。参照其 README 进行操作。
4. 将我们的脚本从 `unity/Assets/Scripts/` 复制到项目中。
5. 导入一个 `.ply` 文件（可先使用公开示例）并点击 Play。完整步骤见 `docs/06`。

GPU：任何现代独立 GPU 均可处理数十万至数百万个高斯点（splat）。如果出现卡顿，可降低高斯点（splat）数量或使用导入器的压缩功能。

---

## 常见问题快速排查

| 现象 | 解决方法 |
|---|---|
| `submodule diff-gaussian-rasterization` 编译失败 | 确认 CUDA toolkit 与 PyTorch 版本匹配；使用 `--recursive` 克隆；在仓库 issues 中查找对应 GPU 型号的解决方案 |
| COLMAP 识别到的图片太少 / 注册失败 | 增加重叠度、增加照片数量、保证纹理丰富；视频帧可尝试 sequential matcher |
| Unity 提示 "PLY is probably not a Gaussian Splat file" | 必须使用 **3DGS** 格式的 `.ply`（含逐高斯属性），而非普通点云文件 |
| 训练时 VRAM 不足 | 降低 `-r`（分辨率），减少致密化，或使用 CPU 数据加载进行训练 |
| Agent 无响应 / 密钥报错 | 不设置 `ANTHROPIC_API_KEY` 以使用 mock 规划器 |
