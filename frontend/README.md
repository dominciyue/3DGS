# 前端 — 浏览器一体化工作室

零构建的单页应用，**三列布局**：

```
┌──────────┬──────────────────────┬──────────┐
│ 任务控制   │   3DGS 实时渲染视口    │ Agent 聊天 │
│ 路径输入   │   (mkkellogg/         │ 多轮对话   │
│ 预设/指令  │   gaussian-splats-3d │           │
│ 进度日志   │   WebGL2)            │ /api/chat │
└──────────┴──────────────────────┴──────────┘
```

操作型 UI 全在浏览器里（不在 Unity 中），现场演示只需打开浏览器。
**Unity 那套 (`tools/unity_3dgs_importer/Agent3DGSStudioUI.cs`) 保留为可选**:
真的有 Unity demo 需求时用,但默认路径是这个 Web 工作室。

## 运行

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8001   # 同时把这个目录托管在 /
```

浏览器打开 `http://localhost:8001` 即可。**首次加载需要联网**(从 jsDelivr 拉
gsplat 库 + Three.js,约 1–2 MB;浏览器之后会缓存)。

## 一键样本(无需训练)

后端在 `sample-scene/` 或 `data/sample-scene/` 找到训练好的 3DGS 输出
(`point_cloud/iteration_*/point_cloud.ply`)时,前端 **加载样本** 按钮就能用——
后端通过 `GET /api/sample` 把 .ply 直接送进浏览器渲染。**没有就报 404 + 文案**。

如何放样本:
- 把训练完的整个目录(含 `cameras.json` / `cfg_args` / `point_cloud/`)解压到
  `sample-scene/`(仓库根目录)或 `data/sample-scene/`(已被 `.gitignore` 排除,不入仓)。
- 后端不需要重启,刷新浏览器即可。

## 文件

- `index.html` — 三列布局 + import map 加载 gsplat
- `styles.css` — 暗色 grid 布局
- `app.js` — ESM 模块:`/api/jobs/from-path` 提任务、SSE 看进度、完成自动喂给
  viewer 渲染、`/api/chat` 多轮聊天

## 与后端对接

| 端点 | 用途 |
|---|---|
| `POST /api/jobs/from-path` | 不上传图,直接给后端可读到的文件夹路径 |
| `GET /api/jobs/{id}/events` | SSE 进度 + 日志 |
| `GET /api/jobs/{id}/result` | 任务完成后下载 `.ply`(同时也喂给 viewer) |
| `GET /api/sample` | 加载预训练样本 |
| `POST /api/chat` | 自由对话(`{ messages: [{role, content}, ...] }`) |

## 离线 / 内网部署

CDN 版本不可用时,可以把以下两个文件放到 `frontend/vendor/`,在 `index.html`
的 import map 里改成本地路径:

- `three@0.157.0/build/three.module.js`
- `@mkkellogg/gaussian-splats-3d@0.4.7/build/gaussian-splats-3d.module.js`

不需要构建步骤,改路径即可。
