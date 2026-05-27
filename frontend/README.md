# 前端 — 任务控制台

一个无需构建的单页应用（纯 HTML/CSS/JS），用于驱动 3DGS-Agent 后端：拖放上传图片、向 Agent（智能体）输入自然语言指令、实时查看流水线运行进度（Server-Sent Events），然后下载 `.ply` 文件并查看 Unity 后续步骤。

## 运行

两种方式：

**A. 由后端托管（最简单）。** FastAPI 应用将本目录挂载至 `/`，只需启动后端并访问：
```bash
cd ../backend && uvicorn app.main:app --reload   # http://localhost:8000
```

**B. 独立静态服务器**（独立源；后端 CORS 已允许）：
```bash
python -m http.server 5173      # open http://localhost:5173
```
`app.js` 会自动检测 API 基础地址：由后端托管时使用同源（方式 A），否则使用 `http://localhost:8000`（方式 B）。

## 文件说明

- `index.html` — 页面布局：上传、指令输入、预设、任务视图、近期任务。
- `styles.css` — 深色技术主题，不依赖外部字体或 CDN（可离线使用）。
- `app.js` — 上传 → `POST /api/jobs`，通过 `EventSource` 监听 `/api/jobs/{id}/events` 实时更新，含阶段进度、日志流、结果下载。

无需 `package.json`，无需打包工具——直接打开即可使用。（如日后需要构建步骤，`node_modules/` 和 `dist/` 已在仓库 `.gitignore` 中覆盖。）
