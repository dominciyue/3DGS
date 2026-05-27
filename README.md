# 3DGS-Agent — 图像到 Unity 可交互高斯场景生成系统

> 一套以 **Agent 编排的流水线**，将照片转化为可在 **Unity** 中浏览、缩放、移动、选择并调节参数的 **交互式 3D 高斯泼溅（3DGS）场景**。
>
> VRAR Game Design & Development · Group 13 (第 13 组)
> Xu Ke 许可 · Zheng Yuxuan 郑宇轩 · Zhu Yue 朱越

---

## 1. 项目简介

你通过网页上传一张或多张照片，**LLM Agent** 随即端到端驱动一条固定的重建流水线——相机位姿估计（COLMAP/SfM）、3D 高斯泼溅（3DGS）训练、格式转换与打包——最终生成一个可加载进 **Unity** 的 `.ply` 高斯模型，用户可在 Unity 中**实时浏览、缩放、平移、选择对象并调整显示参数**。

```
 photos ─► [Agent backend] ─► COLMAP ─► 3DGS training ─► .ply ─► Unity ─► interact
            (FastAPI + Claude)                                   (aras-p importer)
```

贯穿整个设计的核心原则：

> **Agent 是 *确定性* 流水线的 *监督/调度者*，而非在每一步即兴发挥的自由行动者。**

3DGS 重建是一条固定的 DAG（预处理 → SfM → 训练 → 转换 → 打包）。我们确定性地执行它以保证可靠性，让 Agent 处理 LLM 真正擅长的部分：理解自然语言请求、**选择参数与质量预设**、**决定运行哪些可选阶段**（例如 Mip-Splatting 抗锯齿），以及**诊断故障并重试**。这直接应对了提案中指出的风险——*"Agent 本身具有不确定性，工具调用存在错误风险"*——通过将不确定性排除在关键路径之外来加以规避。

## 2. 架构概览

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

完整设计说明：[`docs/02-architecture.md`](docs/02-architecture.md)。

## 3. 仓库结构

```
3DGS/
├── README.md                 ← 当前文件
├── LICENSE                   ← 我们代码采用 MIT 协议；上游代码许可不同（见 third_party）
├── .gitignore                ← 排除 .ply / 检查点 / 数据集 / Unity 缓存
├── docs/                     ← 项目文档
│   ├── 00-overview.md          项目概述与术语表
│   ├── 01-roadmap.md           里程碑（第 13–16 周）+ 任务分工 + 进度
│   ├── 02-architecture.md      系统设计与组件接口
│   ├── 03-tech-research.md     调研：3DGS、Mip-Splatting、2DGS、重光照、查看器
│   ├── 04-getting-started.md   环境搭建（COLMAP、CUDA、conda、Unity）
│   ├── 05-pipeline.md          每个阶段的输入/输出/命令详解
│   ├── 06-unity-integration.md 导入 .ply 至 Unity、接入交互脚本
│   ├── 07-extensions.md        Mip-Splatting / 2DGS / 重光照 / VR 扩展目标
│   └── assets/                 原始提案 PDF + 幻灯片
├── backend/                  ← Python：FastAPI 服务器 + Agent + 流水线（可运行）
│   ├── app/
│   │   ├── main.py             REST API + SSE
│   │   ├── jobs.py             任务存储 + 异步执行器
│   │   ├── agent/              Claude tool-use 规划器（planner/tools/prompts）
│   │   └── pipeline/           确定性 DAG：各阶段 + 执行器
│   ├── tests/                  pytest — 流水线/任务逻辑，无需 GPU 即可运行
│   └── requirements.txt
├── frontend/                 ← 无构建步骤的网页仪表盘（HTML/CSS/JS）
├── unity/                    ← Unity 端 C# 交互脚本 + 配置指南
│   └── Assets/Scripts/
└── third_party/              ← 大型上游仓库的配置说明（非 vendored）
```

## 4. 快速开始

> **后端 + 前端可在任意机器上运行**（流水线可进入 mock 模式（占位/模拟），测试无需 GPU 即可通过）。**实际 3DGS 重建需要 CUDA GPU + COLMAP**，**Unity 演示需要 Unity 6**。详见 [`docs/04-getting-started.md`](docs/04-getting-started.md)。

### 后端（Agent + API）

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # add your ANTHROPIC_API_KEY (optional; mock planner works without it)
uvicorn app.main:app --reload   # serves API on http://localhost:8000
```

运行测试（无需 GPU）：

```bash
cd backend && pytest -q
```

### 前端（任务仪表盘）

```bash
cd frontend
python -m http.server 5173      # then open http://localhost:5173
```

仪表盘通过 `http://localhost:8000` 与后端通信。拖入照片，输入指令（例如："reconstruct this object, high quality, anti-aliased"），即可实时查看流水线运行日志。

### Unity（交互式查看器）

详见 [`docs/06-unity-integration.md`](docs/06-unity-integration.md)。简而言之：创建 Unity 6 项目，安装 **[aras-p/UnityGaussianSplatting](https://github.com/aras-p/UnityGaussianSplatting)**，导入生成的 `.ply`，放入我们的 `unity/Assets/Scripts`，点击运行。

## 5. 当前状态 / 如实说明

| 组件 | 状态 | 依赖条件 |
|---|---|---|
| 后端 API + 任务队列 + SSE | ✅ 可运行 | 仅需 Python |
| Agent 规划器（Claude tool-use） | ✅ 可运行；⚙️ 无 API key 时回退到确定性 mock 模式（占位/模拟） | LLM 路径需要 `ANTHROPIC_API_KEY` |
| 流水线 DAG + 阶段接口 | ✅ 可在 **mock 模式（占位/模拟）** 下运行（合成输出） | — |
| COLMAP / 3DGS 训练阶段 | ⚙️ 真实子进程封装，**依赖已安装的工具** | CUDA GPU、COLMAP、Inria 3DGS 仓库 |
| 前端仪表盘 | ✅ 可运行 | 浏览器 |
| Unity 交互脚本 | ✅ 已编写；集成点已标注 | Unity 6 + aras-p 插件 |
| Mip-Splatting / 2DGS / 重光照 / VR | 📋 已作为扩展功能记录 | 见 `docs/07-extensions.md` |

**单张图片与多张图片：** 原版 3DGS 需要*多张重叠视角的图像*，COLMAP 才能恢复相机位姿。**多图是受支持的 MVP 路径。** 真正的单图重建需要生成式图像到三维模型，已列为 `docs/07-extensions.md` 中的扩展目标——我们不会伪造此功能。

## 6. 团队、时间线与入门建议

| 成员 | 负责模块 | 主要目录 |
|---|---|---|
| 许可 Xu Ke | Agent 编排 + 3DGS 环境搭建 | `backend/app/agent`, `backend/app/pipeline`, `third_party` |
| 郑宇轩 Zheng Yuxuan | Unity 场景导入/组织 + 渲染优化 | `unity/`, `docs/06`, `docs/07` |
| 朱越 Zhu Yue | 前端界面 + 交互 | `frontend/`, `unity/Assets/Scripts`（UI/交互） |

**第 13–14 周** 基础流水线 · **第 15 周** 优化 + 扩展 · **第 16 周** 演示。
详细的带复选框追踪计划：[`docs/01-roadmap.md`](docs/01-roadmap.md)。

**现在从哪里入手：** 阅读 [`docs/04-getting-started.md`](docs/04-getting-started.md)，先让某个公开 3DGS 场景在 Unity 中渲染出来（优先打通*最后一公里*，确保团队随时有可演示的成果），再将后端流水线接在其后。

## 7. 许可证与致谢

我们的原创代码采用 MIT 协议（见 [`LICENSE`](LICENSE)）。本项目**编排**了第三方研究代码，这些代码拥有**不同的、有时为非商业**许可证——在再分发前请阅读 [`third_party/README.md`](third_party/README.md)。主要上游仓库：Inria 3DGS、Mip-Splatting、2D Gaussian Splatting、Relightable 3D Gaussian、aras-p UnityGaussianSplatting、clarte53 VR 查看器。完整引用见 [`docs/03-tech-research.md`](docs/03-tech-research.md)。
