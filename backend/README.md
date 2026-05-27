# 后端 — Agent + 流水线 (FastAPI)

编排核心：一个 FastAPI 服务器，接收图片和自然语言指令，由 **Agent（智能体）** 规划 `PipelineConfig`，并运行**确定性流水线**（预处理 → COLMAP → 训练 3DGS → 转换 → 打包），最终生成 `.ply` 文件。

设计原理：[`../docs/02-architecture.md`](../docs/02-architecture.md)。

## 运行

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # optional edits
uvicorn app.main:app --reload # http://localhost:8000  (interactive docs at /docs)
```

`scripts/run_dev.sh` 会自动完成 `.env` 复制和服务启动。

默认以 **mock 模式（占位/模拟）运行**（`PIPELINE_MOCK=1`）：各阶段输出合成结果，训练所得 `.ply` 为体积小但格式正确的高斯点云——因此整个流程（上传 → 规划 → 分阶段进度 → 下载）无需 GPU、工具或 API 密钥即可运行。

## 测试

```bash
pytest -q          # no GPU / network required
```

## 目录结构

```
app/
├── main.py          FastAPI routes + SSE; serves ../frontend at /
├── config.py        env-driven settings (mock flag, tool paths, API key)
├── models.py        PipelineConfig, Job, StageState, Event (pydantic)
├── jobs.py          job store, per-job worker thread, SSE pub/sub
├── agent/
│   ├── planner.py   ClaudePlanner (tool-use) + MockPlanner fallback
│   ├── tools.py     submit_plan tool schema -> PipelineConfig
│   └── prompts.py   planner system prompt
└── pipeline/
    ├── runner.py    DAG executor: events, retry, cancel, mock
    ├── stages.py    Stage base + StageContext (subprocess helper)
    ├── preprocess.py / colmap.py / train.py / convert.py / package.py
    └── _ply.py      Gaussian .ply read/write/validate/decimate
```

## 使用真实 GPU 运行

将 `PIPELINE_MOCK=0`，并在 `.env` 中指定已安装的 COLMAP 和 Inria 训练器仓库的路径（参见 [`../docs/04-getting-started.md`](../docs/04-getting-started.md) 和 [`../third_party/README.md`](../third_party/README.md)）。若某阶段缺少必要工具，将给出明确的错误提示，而不会假装成功。

## API

| 方法 | 路径 | 用途 |
|---|---|---|
| GET  | `/api/health` | 存活检测 + mock/LLM 标志 |
| POST | `/api/jobs` | multipart `images[]` + `instruction` + 可选 `preset` → `{job_id}` |
| GET  | `/api/jobs` · `/api/jobs/{id}` | 列表 / 状态 + 配置 + 各阶段状态 |
| GET  | `/api/jobs/{id}/events` | SSE 进度 + 日志 |
| GET  | `/api/jobs/{id}/result` | 下载 `model.ply` |
| POST | `/api/jobs/{id}/cancel` | 请求取消任务 |
