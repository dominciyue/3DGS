# Agent3DGS Studio UI —— Unity 运行时三联面板

在 `agent_tool.py` 已经自动生成的场景之上，再加一个**运行时 UI**：

```
┌───────────────┬──────────────────────────────────┬────────────────────┐
│  左面板        │      中央：3DGS 场景               │  右面板             │
│  · 图片文件夹  │     （aras-p 渲染器全屏背景）      │  · 与 Agent 对话    │
│  · NL 指令     │                                  │  · 多轮聊天历史     │
│  · 质量预设    │                                  │  · 文本框 + 发送    │
│  · 生成场景    │                                  │                    │
│  · 任务状态     │                                  │                    │
│  · 日志        │                                  │                    │
└───────────────┴──────────────────────────────────┴────────────────────┘
```

`F2` 切换面板显隐（与原有的 `F1` 控制面板互不影响，可同时存在）。

## 一、安装

1. 把同目录的 `Agent3DGSStudioUI.cs` 拷贝到 Unity 工程的 `Assets/Agent3DGS/Runtime/`。
2. 打开自动生成的场景（默认在 `Assets/Generated3DGS/<场景名>/<场景名>.unity`）。
3. 新建一个空 GameObject（名字随意，如 `Agent3DGS Studio`），Inspector 里 `Add Component` →
   **`Agent3DGS/Studio UI (folder + status + chat)`**。
4. 在 Inspector 把 `Backend Base Url` 设成后端实际地址（默认 `http://localhost:8001`）。

进入 Play Mode 即可看到三联面板。

## 二、后端依赖

需要后端提供两个接口（已在仓库 `backend/app/main.py` 内置）：

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/jobs/from-path` | 不上传文件，直接给一个**后端能读到的文件夹绝对路径**，触发任务 |
| `POST` | `/api/chat` | 多轮自由对话（有 `ANTHROPIC_API_KEY` 走 Claude，没有走规则版 mock） |

后端启动：

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --port 8001
```

## 三、左面板使用

- **图片文件夹**：填**后端宿主机**上能直接 `ls` 到的绝对路径，例如：
  - 本机演示：`/home/ygwang/vr/data/sample-scene/`（仓库自带的样本）
  - 真实拍摄：`/some/path/to/photos/`
- **指令**：自然语言，如 `高质量、抗锯齿、远处稳定`。
- **质量预设**：留 `自动` 让 Agent 决定；或选 `preview / balanced / high`。
- 点 **生成场景** → 调 `/api/jobs/from-path` → 轮询 `/api/jobs/{id}` 直到 `done`。
- 日志区会显示各阶段实时进度。

## 四、右面板使用

- 文本框输入任何问题（"参数怎么选"、"COLMAP 报错怎么排查"、"Mip-Splatting 和 vanilla 差在哪"），
  点 **发送** → 调 `/api/chat`。
- 标题栏会显示当前后端：`claude` 或 `mock`。

## 五、把结果拉回 Unity（一键 ↩）

任务跑到 `done` 之后，左面板会出现一个按钮：

```
↩ 把 .ply 加入当前场景
```

点一下即可（**仅在 Unity Editor 内有效**；标准 player 构建里这块代码被剥离）：

1. 把后端 `data/jobs/<id>/result/model.ply` 复制到 `Assets/Generated3DGS/jobs/<id>/`（如果
   后端不在本机，则改走 `GET /api/jobs/{id}/result` 下载）；
2. 反射调用 aras-p 公开的 `GaussianSplatting.Editor.GaussianSplatAssetCreator`
   （等同 `Tools > Gaussian Splats > Create GaussianSplatAsset`），把 `.ply` 转成
   `GaussianSplatAsset`；
3. 在**当前活动场景**新建一个 `GameObject` + `GaussianSplatRenderer`，把生成的 asset 赋
   过去，标记场景已修改。**不新建场景、不替换场景**，与队友的 `Agent3DGSAutoImporter`/
   `Agent3DGSSceneBuilder` 完全独立，没有任何修改。

如果按钮置灰 / 一直转：通常是 aras-p 插件还没被 Package Manager 装完，等右下角
编译条转完再点一次。

### 备用手动路径

不想用按钮的话仍可走原来的两条路：
- **菜单**：`Agent3DGS > Auto Import Configured PLY`（来自队友的 `Agent3DGSAutoImporter`，会**新建场景**）。
- **纯手动**：把 `model.ply` 拖进 `Assets/`，aras-p 会自动生成 asset，再挂到 `GaussianSplatRenderer` 上。

## 六、与同目录其他文件的关系

| 文件 | 角色 |
|---|---|
| `agent_tool.py` | Python 一键准备 Unity 工程并安装 4 个 C# 脚本 |
| `Agent3DGSStudioUI.cs` | **本文件** — 运行时三联面板（与上面 4 个脚本并存） |
| `STUDIO_UI.md` | 本文档 |
| `README.md` | 一键导入工具的总说明 |
