# 09 · 团队集成与使用全流程

> 给三人小组(许可 · 郑宇轩 · 朱越)用的"对齐 + 上手"文档。从空机器到能现场演示,**一篇看完所有人都知道自己要做什么、东西怎么接、怎么演**。
>
> 这一篇是导航 + 流程,**细节直接跳到对应的子文档**(链接在文末)。

---

## 1. 我们做的是什么(30 秒回顾)

```
用户上传/指定一个图片文件夹
        │
        ▼
[ 浏览器 (frontend/) ]  ← 朱越的工作:操作型 UI + 内嵌 3DGS 实时渲染 + Agent 聊天
        │  REST API
        ▼
[ 后端 (backend/) ]     ← 许可的工作:FastAPI + Agent 规划器 + 确定性流水线
        │  Agent 把自然语言翻成 PipelineConfig
        │  确定性 DAG: preprocess → COLMAP(SfM) → train(3DGS) → convert → package
        ▼
   point_cloud.ply (高斯模型)
        │
        ├──► 浏览器中央 canvas (mkkellogg/gaussian-splats-3d)    ← 主演示路径
        │
        └──► Unity 工程 (aras-p 插件)                           ← 郑宇轩的工作 + 备用 demo
                ├── tools/unity_3dgs_importer/agent_tool.py 一键导入(队友共同维护)
                └── 嵌入式 Studio UI (运行时三联面板, 可选)
```

**核心架构原则**:**Agent 是确定性流水线的调度者,不是执行者**。大模型只负责把人话翻成 `PipelineConfig`、出错时调参重试;**重建本身是固定 DAG,稳定可复现**。完整说明见 [`02-architecture.md`](02-architecture.md)。

---

## 2. 各人交付物的具体位置

| 成员 | 负责模块 | 仓库目录 / 关键文件 | 接口契约 |
|---|---|---|---|
| **许可 Xu Ke** | Agent 编排 + 3DGS 流水线 + 真实工具接入 | `backend/app/agent/` (planner / chat / tools)<br>`backend/app/pipeline/` (5 个阶段 + runner)<br>`backend/app/main.py` (REST 端点)<br>`backend/app/models.py` (PipelineConfig 等)<br>`third_party/` (COLMAP / Inria 3DGS 安装) | 提供:REST API(下面 §5) + `.ply` 输出契约(`docs/05` §convert) |
| **朱越 Zhu Yue** | 浏览器前端 + 运行时交互 | `frontend/index.html` (三列布局)<br>`frontend/styles.css` (暗色主题)<br>`frontend/app.js` (gsplat viewer + 任务/聊天 + SSE)<br>`tools/unity_3dgs_importer/Agent3DGSStudioUI.cs` (Unity 嵌入式三联面板) | 消费:同上 REST API。<br>`PipelineConfig` JSON 形状要跟许可对齐(`backend/app/models.py`) |
| **郑宇轩 Zheng Yuxuan** | Unity 场景导入 / 组织 / 渲染优化 | `unity/Assets/Scripts/` (轨道相机 / 多对象选择 / 调参面板 — 简版方案)<br>`tools/unity_3dgs_importer/agent_tool.py` (一键导入 — 重点维护)<br>四个 Editor / Runtime C# 脚本(agent_tool.py 自动写入到 Unity 工程) | 消费:`.ply` 文件(任意路径) + `cameras.json` / `cfg_args` |

**接口对齐的两个关键约定**:
1. **REST API**:见 §5,所有跨模块通信都走这里。改任何端点签名,**必须三人同步**。
2. **`.ply` 契约**:Inria 训练器原生输出格式(含 `nx,ny,nz` 法线 + `f_rest_0..44` SH3 + `opacity/scale_0..2/rot_0..3`)。任意环节如果换了格式(如 SPZ / 压缩),需要在 `convert` 阶段做兼容。

---

## 3. 一次性环境配置(各角色按需做)

### 3.1 所有人共同的部分(必做)

```bash
# 任意机器, 任意系统
git clone git@github.com:dominciyue/3DGS.git
cd 3DGS
```

### 3.2 许可(后端 / 流水线)

**Mock 模式**(零外部依赖,适合开发 Agent / 流水线编排逻辑):
```bash
cd backend
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 可选: 在 .env 里设 ANTHROPIC_API_KEY 让 Agent 走真 Claude
uvicorn app.main:app --port 8001
```

**真实 3DGS 重建模式**(需要 NVIDIA GPU + COLMAP + Inria 3DGS 仓库):
1. 详细安装步骤见 [`04-getting-started.md`](04-getting-started.md) §B
2. `.env` 里:
   ```
   PIPELINE_MOCK=0
   COLMAP_BIN=/path/to/colmap            (Windows: C:\Program Files\COLMAP\bin\colmap.exe)
   GS_REPO_DIR=../third_party/gaussian-splatting
   GS_PYTHON=/path/to/conda-env/bin/python
   ```
3. 重启 uvicorn,前端任务自动走真路径(同样 5 个阶段,train 这步真训)。

### 3.3 朱越(前端)

**不需要单独环境** — 跟着许可的后端就行。后端启动后浏览器开 `http://localhost:8001`。

开发时**必须开**:F12 → Network 标签 → **勾上 `Disable cache`**(否则改了 `app.js`/`index.html` 后浏览器一直跑旧版,**这是我们调试时踩过的最大坑**)。

### 3.4 郑宇轩(Unity 工程)

1. 装 **Unity 6 LTS** 或 **Unity 2022.3.17f1c1**(我们验证过这两个版本)。
2. Unity Hub 建空 3D 工程,路径例如 `E:\3DGS\UnityProjects\3DGSDemo`,**完全关闭 Editor** 后再做下一步。
3. 用许可那个 venv 跑一键工具:
   ```powershell
   python tools\unity_3dgs_importer\agent_tool.py `
     --gs-output-dir       "E:\3DGS\sample-scene" `
     --unity-project-dir   "E:\3DGS\UnityProjects\3DGSDemo" `
     --scene-name          "Demo3DGSScene" `
     --run-unity-import `
     --unity-exe           "C:\Program Files\Unity\Hub\Editor\2022.3.17f1c1\Editor\Unity.exe" `
     --graphics-api        d3d12
   ```
   它会:装 aras-p 包 → 复制 .ply → 写入 4 个 C# 脚本 → batchmode 启动 Unity → 自动出场景。
4. 工程一旦建好,**Project Settings → Player → Other Settings → Graphics API** 要切到 **D3D12 或 Vulkan**(DX11 不支持 aras-p 的 wave 指令 → 全黑,我们已经踩过)。
5. 完整步骤 + 故障排查:[`06-unity-integration.md`](06-unity-integration.md) 和 [`../tools/unity_3dgs_importer/README.md`](../tools/unity_3dgs_importer/README.md)。

---

## 4. 三套演示路径(按场合选)

### A · 浏览器一体化(**主推**,演示首选)

**适用**:答辩 / 课堂 / 远程演示 / 没装 Unity 的机器。
**流程**:
```
后端起在 8001 → 浏览器开 localhost:8001 → 一切都在这里
```
- 左侧:填图片文件夹路径 → 写自然语言指令 → "生成场景"
- 中央:任务跑完自动加载 `.ply` 到 gsplat viewer(WebGL2 实时渲染)
- 右侧:跟 Agent 多轮聊天

**首次部署后视感调优**:见 §6.4。

### B · Unity 嵌入式 Studio UI(郑宇轩 的备用方案)

**适用**:演示机就是装 Unity 的开发机时;想用飞行相机自由穿梭;走完队友定义的"在游戏里操作"链路。
**步骤**:
1. 跑 §3.4 的 `agent_tool.py` 生成工程。
2. 把 `tools/unity_3dgs_importer/Agent3DGSStudioUI.cs` 复制到工程的 `Assets/Agent3DGS/Runtime/`。
3. 场景里挂 `Agent3DGS/Studio UI`,Backend Base URL 填 `http://localhost:8001`。
4. Play → F2 切 Studio 面板 → 填路径 / 生成 / 聊天 → ↩ 把 .ply 加入当前场景。
5. 完整说明:[`../tools/unity_3dgs_importer/STUDIO_UI.md`](../tools/unity_3dgs_importer/STUDIO_UI.md)。

> 这条路 UX 有一个**已知问题**:Game 视图里 IMGUI 跟相机/鼠标锁定输入冲突(按 F2 + 鼠标解锁后能用,但答辩演示时**建议走 A 路径**)。

### C · 真实 3DGS 重建

**适用**:有 GPU 环境时的完整端到端 demo,不再用 mock 占位。
**前置**:许可按 §3.2 第二段配好真实模式。
**操作**:跟 A / B 完全一样,**填的"图片文件夹"换成你拍的几十张照片**(同一物体 70%+ 重叠,详见 [`04-getting-started.md`](04-getting-started.md) §"capture tips")。train 阶段实际花几十分钟到几小时,看 GPU 和 iters。

---

## 5. REST API(所有人务必熟悉这张表)

许可定义,朱越消费,郑宇轩(Studio UI 时)消费。

| 方法 | 路径 | 用途 | 谁会用 |
|---|---|---|---|
| `GET`  | `/api/health` | 存活检测 + `mock_pipeline` / `llm_enabled` 状态 | 前端启动时一次 |
| `POST` | `/api/jobs` | **multipart** 上传图片 + instruction + 可选 preset → `{job_id}` | (legacy,网页拖拽上传场景) |
| `POST` | `/api/jobs/from-path` | JSON `{path, instruction, preset?}`,后端可读到的绝对路径 → `{job_id}` | **新前端 / Unity Studio UI 用这个** |
| `GET`  | `/api/jobs` | 列出所有任务 | "最近任务"面板 |
| `GET`  | `/api/jobs/{id}` | 任务全状态(status / config / stages / result_path) | 重连 / 重刷 / 已完成任务回放 |
| `GET`  | `/api/jobs/{id}/events` | **SSE** 进度 + 日志流 | 跑任务时实时显示 |
| `GET`  | `/api/jobs/{id}/result` | 下载 `.ply` | 前端 viewer 装载;Unity Studio UI "↩ 导入" |
| `POST` | `/api/jobs/{id}/cancel` | 请求取消运行中的任务 | UI 取消按钮 |
| `POST` | `/api/chat` | **多轮**自由对话(`{messages:[{role,content}]}`) → `{reply, backend}` | 前端右侧聊天 / Unity Studio 聊天 |
| `GET`  | `/api/sample` | 直接下载预训练样本 `.ply`(`sample-scene/` 或 `data/sample-scene/`) | 前端"加载样本"按钮 |
| `GET`  | `/api/sample/debug` | 诊断 `_find_sample_ply()` 返回的真实路径 + 检索过程 | 排查"加载样本"为啥 404 |

### `PipelineConfig` JSON 形状(`backend/app/models.py`)

Agent 输出 / 前端展示用的同一份结构:
```json
{
  "preset": "preview | balanced | high",
  "max_image_edge": 1600,
  "colmap": { "use_gpu": true, "matcher": "exhaustive" },
  "train": { "backend": "vanilla | mip | 2dgs | relight", "iterations": 30000, "resolution": 1, "sh_degree": 3 },
  "convert": { "max_splats": null, "emit_spz": false },
  "notes": "..."
}
```
任何字段调整需**许可改 `models.py`、朱越同步前端展示**。

---

## 6. 联调测试 + 验收清单

### 6.1 后端单测(许可日常)

```bash
cd backend && pytest -q          # 应该 12/12 通过, 无需 GPU / 网络
```
覆盖:流水线 DAG、stages 校验、mock planner 关键词路由、Job lifecycle、SSE 事件订阅、`/api/jobs`、`/api/jobs/from-path`、`/api/chat`、`/api/sample`。

### 6.2 浏览器端 smoke test(朱越/演示前自检)

按顺序点一遍:
- [ ] 右上角徽章:`mock 流水线` / `mock 智能体`(或 `Claude` 如设了 key)
- [ ] **加载样本** → 中央 viewer 出现高斯点云、左键拖能转
- [ ] 左侧"图片文件夹"填一个有 jpg 的目录 → 生成场景 → 5 阶段进度条跑完
- [ ] 完成后中央自动加载结果 `.ply`(mock 是占位云,真训是清晰场景)
- [ ] 右侧聊天 → 输入"preview 和 high 差在哪"→ 拿到回复

### 6.3 Unity smoke test(郑宇轩)

- [ ] `agent_tool.py` `unity_exit_code: 0`
- [ ] Project Settings → Graphics API 在最上面是 D3D12 / Vulkan
- [ ] 打开生成的场景按 Play → WASD 走、鼠标看、F1 控制面板
- [ ] (可选)挂 Agent3DGSStudioUI → F2 → ↩ 导入 → 当前场景多出一个 splat

### 6.4 渲染视感对齐(已踩坑总结)

跟 Unity aras-p 视觉接近的浏览器侧配置(在 `frontend/app.js`):
- `antialiased: true`(开抗锯齿)
- `sphericalHarmonicsDegree: 3`(跟 Inria 默认 SH 阶数对齐)
- `splatAlphaRemovalThreshold: 80`(剔除低 opacity 噪声 splat)
- `outputColorSpace = SRGBColorSpace`(WebGL 默认线性,会过曝)
- `mesh.setSplatScale(0.7)`(全局尺寸,1.0 库默认会过曝)

调亮度时 F12 控制台直接试 `__dbg.setScale(N)`。

---

## 7. 数据 / 大文件如何流转

**进 git 的**:所有源代码、文档、配置模板、`docs/assets/` 里的开题 PDF + 开发 PPT。

**`.gitignore` 排除的(本机 / Release)**:
- `*.ply` / `*.splat` / `*.spz`(高斯模型,几十 MB ~ 几百 MB)
- `*.pth` / `*.ckpt` 检查点
- `data/` / `backend/data/`(任务工作目录,每个 job 几十 MB)
- `sample-scene/` 不在 ignore,但**约定不入仓**;每人本地解压一份给前端 `加载样本` 用
- COLMAP 中间产物 / Unity 缓存

**怎么共享样本**:解压同一份 `5c0f3ca9-4.zip`(或团队共享盘上拿)到`<repo-root>/sample-scene/`,前端 `/api/sample` 端点会**递归找** `point_cloud/iteration_*/point_cloud.ply`。

---

## 8. 常见坑(我们已经踩过的)

| 现象 | 真正原因 | 修法 |
|---|---|---|
| 改了 `app.js` 但浏览器还是旧效果 | ES 模块缓存极强,Ctrl+Shift+R 不一定够 | F12 → Network 标签 **勾上 Disable cache** + 刷新,或用 Ctrl+Shift+N 无痕窗口验证 |
| Unity Play Mode 全黑 / shader 报 `wavebasic` `waveballot` | 默认 Graphics API 是 DX11,aras-p 需要 DX12 / Vulkan | Project Settings → Player → 把 D3D12 拖到 Graphics APIs 列表最上 |
| 加载样本提示"没有样本场景" | `sample-scene/` 没解压 / 解多了一层 / 缺 `point_cloud/iteration_*` | 浏览器开 `http://localhost:8001/api/sample/debug` 看后端实际检索路径 |
| 端口 8001 占用 | 同机有别的 uvicorn / root 的旧服务 | 换端口 `--port 8002`(前端是同源,会自动跟随,无需改) |
| `from-path` 返回 400 "no images" | 填的是训练输出目录(里面只有 .ply),不是图片目录 | 填一个有 jpg/png 的目录;mock 演示时用 PowerShell 一行造占位 jpg(见 §A 备注) |
| 浏览器 viewer 整体过亮过曝 | WebGL 默认线性色空间 + Inria 训练有大量低 opacity "填充 splat" | 已修(sRGB + alpha 阈值 80 + setSplatScale 0.7);视感再调用 `__dbg.setScale(N)` |
| 浏览器画面全黑(无 wireframe 也无 splat) | gsplat 的 splat scale 全局乘数被默认设了某个怪值,或 SH degree 没对齐 | viewer 配置确保 `sphericalHarmonicsDegree: 3` 且加载后调用 `mesh.setSplatScale(0.7)` |
| `HEAD /api/sample` 404 但 `GET /api/sample` 200 | FastAPI `@app.get` 配 FileResponse 时 HEAD 自动路由有 bug | 已用 `@app.api_route(methods=["GET","HEAD"])` 修;前端也不再做 HEAD 预探测 |

---

## 9. 答辩 / 演示 4 分钟脚本(走主路径 A)

```
启动:服务器跑 uvicorn 在 8001 → 本地浏览器开 http://localhost:8001
准备好:F12 Network 勾 Disable cache + 一个有几张 jpg 的占位目录(展示用)

【开场 30s】
"我们是 13 组,题目是面向 3DGS 的 Agent 系统:用户上传几张照片,Agent 自动调度
COLMAP/3DGS/转换/打包整条流水线,最终在浏览器里直接看到可交互的高斯场景。"

【核心架构 30s】
指右上徽章:"Agent 我们做的是'监督者',不是'自由发挥的执行者' — 重建本身是确定性
DAG, Agent 只把你这句自然语言翻成 PipelineConfig.这直接对应开题列的风险."

【一键加载样本 30s】
点"加载样本" → 中央出现高斯点云 → 鼠标拖转
"这是我们预训练好的样本场景, mkkellogg/gaussian-splats-3d 在浏览器里 WebGL2 实时渲染.
跟 Unity 里 aras-p 看到的视感接近, 但不依赖装 Unity."

【完整流水线 mock 演示 90s】
左侧填 demo-photos 路径 + "高质量、抗锯齿" → 生成场景
指 Agent plan:"Agent 把这句话解析成了 preset=high + backend=mip(Mip-Splatting 抗锯齿)."
看 5 阶段进度条跑完 → 中央自动加载新 .ply(占位云,但流程通)
老实说一句:"重建用 mock 演示完整调度, 真重建需要 GPU + COLMAP, 装好开关一关就走真路径."

【Agent 聊天 30s】
右侧输入"preview 和 high 差在哪" → 回车 → 看回复
"自由对话也接好了, mock 模式走规则版, 配 API key 走 Claude 多轮."

【结束 30s】
"完整代码 + 文档 + 队友的 Unity 一键导入工具都开源在 github.com/dominciyue/3DGS,
基础成果已完成, 进阶 Mip-Splatting / 2DGS / VR 可挑一两个落地. 谢谢."
```

---

## 10. 文档地图(细节都在这些子文档里)

| 主题 | 文档 |
|---|---|
| 项目概念 + 术语 | [`00-overview.md`](00-overview.md) |
| 里程碑 + 分工 + 风险 | [`01-roadmap.md`](01-roadmap.md) |
| **系统架构详解** | [`02-architecture.md`](02-architecture.md) |
| 技术调研 (3DGS / Mip-Splatting / 2DGS / Relightable) | [`03-tech-research.md`](03-tech-research.md) |
| 环境搭建(COLMAP / CUDA / Unity) | [`04-getting-started.md`](04-getting-started.md) |
| **流水线 5 阶段输入/输出/命令** | [`05-pipeline.md`](05-pipeline.md) |
| Unity 端简版方案(我自己的 4 个脚本) | [`06-unity-integration.md`](06-unity-integration.md) |
| 进阶扩展(Mip-Splatting / 2DGS / Relight / VR) | [`07-extensions.md`](07-extensions.md) |
| **本文档(集成与使用)** | **`09-integration-guide.md`** |
| 后端模块说明 | [`../backend/README.md`](../backend/README.md) |
| 前端说明 + 离线部署 | [`../frontend/README.md`](../frontend/README.md) |
| Unity 端两套方案对比 | [`../unity/README.md`](../unity/README.md) |
| 一键 Unity 导入工具 | [`../tools/unity_3dgs_importer/README.md`](../tools/unity_3dgs_importer/README.md) |
| 嵌入式 Studio UI(Unity Play Mode 三联面板) | [`../tools/unity_3dgs_importer/STUDIO_UI.md`](../tools/unity_3dgs_importer/STUDIO_UI.md) |
| 上游 3DGS / 训练器 / 查看器许可证说明 | [`../third_party/README.md`](../third_party/README.md) |
