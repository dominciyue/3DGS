# 02 · 系统架构

## 核心设计决策：Agent *负责调度*，流水线*负责执行*

让 LLM Agent 自由决定重建的每个步骤是不可靠的——我们的提案明确将
*"Agent 本身具有不确定性，工具调用存在错误风险"* 列为首要风险。因此我们
拆分职责：

```
        non-deterministic, language-level                deterministic, data-level
   ┌────────────────────────────────────┐        ┌────────────────────────────────┐
   │            AGENT (Claude)           │ config │        PIPELINE RUNNER          │
   │  • parse NL request                 │───────►│  fixed DAG of typed stages      │
   │  • choose preset / params           │        │  preprocess→colmap→train→       │
   │  • decide optional stages           │        │  convert→package                │
   │  • read stage results, diagnose,    │◄───────│  each stage: validate I/O,      │
   │    retry or adjust                  │ result │  idempotent, retryable          │
   └────────────────────────────────────┘        └────────────────────────────────┘
```

- **流水线**是*执行内容*的权威来源。各阶段具有类型化的输入/输出并对其进行验证。
  给定相同的配置，执行结果总是一致的。
- **Agent** 决定*如何配置流水线*以及*如何响应执行结果*。它调用一组有限的工具
  （配置任务、运行阶段/流水线、检查产物、设置参数），从不直接手写高斯或绕过某个阶段。
- 如果未设置 `ANTHROPIC_API_KEY`，则由 **mock 模式（占位/模拟）规划器** 通过简单规则
  生成合理的默认配置——使整个系统可在离线状态下演示。

这样既将不确定性*置于关键路径之外*，又保留了 Agent 的价值：自然语言输入、参数判断
以及错误恢复。

## 组件与接口契约

每个组件职责单一、接口清晰，并可独立测试。

### 1. 前端 (`frontend/`)
- **职责：** 收集图像与自然语言指令，POST 提交任务，流式传输进度/日志，提供结果下载，
  展示 Unity 后续步骤。
- **依赖：** 仅依赖 REST API。无需构建步骤（纯静态 HTML/CSS/JS）。
- **接口：** 见下方 REST 端点。

### 2. 后端 API (`backend/app/main.py`)
- **职责：** HTTP 接口层——接收上传、创建任务、流式推送事件、提供结果下载。
- **依赖：** 任务存储及 Agent/流水线模块。
- **接口（REST）：**

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET`  | `/api/health` | 存活检测 + 是否已配置 LLM 密钥 |
| `POST` | `/api/jobs` | 创建任务（multipart：images[] + `instruction` + 可选 `preset`）→ `{job_id}` |
| `GET`  | `/api/jobs` | 列出所有任务 |
| `GET`  | `/api/jobs/{id}` | 任务状态、配置、各阶段状态及产物 |
| `GET`  | `/api/jobs/{id}/events` | **SSE** 状态/日志更新流 |
| `GET`  | `/api/jobs/{id}/result` | 下载生成的模型（`.ply`） |
| `POST` | `/api/jobs/{id}/cancel` | 请求取消任务 |

### 3. 任务存储与工作线程 (`backend/app/jobs.py`)
- **职责：** 管理任务生命周期（`queued → planning → running → done/failed/cancelled`），
  将每个任务持久化至 `data/jobs/<id>/`，为每个任务启动后台工作线程，并向 SSE
  订阅者推送事件。
- **依赖：** Agent 规划器 + 流水线执行器。
- **接口：** `create_job(...)`, `get_job(id)`, `list_jobs()`, `subscribe(id)`。

### 4. Agent 规划器 (`backend/app/agent/`)
- **`prompts.py`** — 系统提示词，描述目标、可用阶段，以及"配置（而非绕过）流水线"的护栏。
- **`tools.py`** — JSON schema 工具定义 + 将工具调用映射到流水线操作的分发器。工具包括：
  `set_pipeline_config`、`run_pipeline`、`inspect_artifact`、`finish`。
- **`planner.py`** — Agent 循环（Claude 工具调用）。无 API 密钥时回退至确定性
  `MockPlanner`。输出：经过验证的 `PipelineConfig`。
- **依赖：** Anthropic SDK（可选）、流水线类型定义。

### 5. 流水线 (`backend/app/pipeline/`)
- **`stages.py`** — `Stage` 基类、`StageResult` 及注册表。每个阶段：
  `validate_inputs() → run() → 生成产物 → validate_outputs()`。
- **`runner.py`** — 按 DAG（有向无环图）顺序执行 `PipelineConfig` 中的各阶段，推送进度
  事件，支持 `mock=True`（合成输出，无需外部工具）、取消以及按阶段重试。
- **`preprocess.py / colmap.py / train.py / convert.py / package.py`** — 各阶段实现。
  封装 COLMAP / Inria 训练器的子进程调用，每个阶段均有*门控*：若工具未安装，则以
  可操作的错误信息失败（或以 mock 模式运行）。
- **依赖：** 外部工具（COLMAP、Inria 3DGS）——仅在真实运行时需要。

### 6. Unity 项目 (`unity/`)
- **职责：** 加载 `.ply`，使用 aras-p 插件渲染，并提供交互功能。
- **依赖：** aras-p/UnityGaussianSplatting + 生成的 `.ply`。
- **接口：** 将 `Assets/Scripts` 拖入场景；详见 `docs/06`。

## 数据流（单个任务）

```
1. Frontend POSTs images + instruction.
2. Job store saves images to data/jobs/<id>/input/, status=planning, starts worker.
3. Agent planner reads the instruction (+ image count/metadata) → PipelineConfig
   (quality preset, iterations, whether to run Mip-Splatting, etc.).
4. Runner executes the DAG, each stage writing to data/jobs/<id>/<stage>/ and
   emitting events the frontend streams over SSE:
       preprocess  → normalized images
       colmap      → cameras + sparse point cloud  (sparse/0/)
       train       → point_cloud/iteration_*/point_cloud.ply
       convert     → validated/optionally-compressed model
       package     → result/model.ply (+ manifest.json with metadata)
5. status=done; frontend enables download; user imports into Unity.
```

## 任务状态机

```
queued ──► planning ──► running ──┬─► done
   │            │           │     └─► failed  (stage error after retries)
   └────────────┴───────────┴───────► cancelled  (user request)
```

## 边界划分的原因

- **API ↔ 流水线**的拆分使 朱越 可以针对 mock 后端开发前端，而 许可 则在同一契约背后
  接入真实工具。
- **Agent ↔ 流水线**的拆分意味着 LLM 的错误决策最多只能产生一份错误的*配置*，各阶段
  仍会对其进行验证——无法破坏重建逻辑本身。
- **`.ply` 契约**是移交给 Unity 的唯一接口，因此 郑宇轩 可以基于任意符合规范的 `.ply`
  （公开样本或新鲜训练的结果）工作，无需与后端耦合。

## 技术选型（以及被排除的备选方案）

| 选型 | 原因 | 被排除的备选方案 |
|---|---|---|
| FastAPI | 异步、类型化（pydantic）、SSE 支持简单、体量小 | Flask（异步/类型化较弱）；Django（对课程演示过重） |
| 进程内任务工作线程 | 单机部署、简单、演示友好 | Celery/Redis（课程演示运维开销过高） |
| Claude 工具调用实现 Agent | 工具调用能力强；监督而非执行 | LangChain（过于不透明）；全自主 Agent（不可靠） |
| Inria 3DGS 训练器 | 参考实现；文档完善 | gsplat/nerfstudio（可行备选；依赖更多） |
| aras-p Unity 导入器 | 拖放 `.ply`、GPU 排序、支持 Unity 6、无需运行时 CUDA | clarte53 VR 查看器（保留用于 VR 扩展目标） |
| 原生 JS 前端 | 无需构建、随处可运行、易于评分/演示 | React/Vite（需要构建步骤；此处不必要） |
