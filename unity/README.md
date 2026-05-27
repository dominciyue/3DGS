# Unity — 交互式 3DGS 查看器

"最后一公里"：加载生成的 `.ply` 文件并使其可交互。这些 C# 脚本在 [aras-p/UnityGaussianSplatting](https://github.com/aras-p/UnityGaussianSplatting) 渲染器之上，实现了项目所需的基础交互功能——**浏览、缩放、平移、选择以及调整显示参数**。

> 本目录仅包含**我们的脚本和配置说明**，并非完整的 Unity 工程。请在本地创建项目（仓库中仅追踪 `Assets/`、`Packages/`、`ProjectSettings/` 目录——缓存和构建输出已被 `.gitignore` 忽略）。完整操作指南：[`../docs/06-unity-integration.md`](../docs/06-unity-integration.md)。

## 配置（约 10 分钟）

1. 在本 `unity/` 目录下创建 **Unity 6 LTS** 项目（推荐使用 URP）。
2. 安装 **aras-p/UnityGaussianSplatting**（通过 Package Manager → *从 git URL 添加包*，或克隆后添加本地包）。请参阅其 README。
3. 将本目录中的 `Assets/Scripts/*.cs` 复制到项目中。
4. **导入模型：** 将 `.ply` 文件（例如公开示例或后端生成的文件）拖入项目——导入器将构建 `GaussianSplatAsset`。
5. 按下方说明连接场景，然后点击 **Play**。

## 场景连接

| GameObject | 组件 | 说明 |
|---|---|---|
| **Main Camera** | `OrbitCameraController` | 左键拖动旋转 · 右键/中键拖动平移 · 滚轮缩放 |
| **Splat 对象** | `GaussianSplatRenderer`（插件）+ `BoxCollider` + `SplatSelectable` | 将 BoxCollider 调整至与模型匹配——它是拾取/聚焦的代理 |
| **SceneManager**（空对象） | `SplatSceneManager` | 指定相机 + （可选）Display UI |
| **UI**（空对象） | `DisplayParamUI` | 屏幕上的滑块；无需 Canvas（使用 IMGUI） |

若有多个 splat 对象？为每个对象分别添加 `BoxCollider` + `SplatSelectable`；管理器会统一追踪并处理选择/聚焦。

## 操作控制

| 输入 | 操作 |
|---|---|
| 左键拖动 | 旋转视角 |
| 右键/中键拖动 | 平移 |
| 鼠标滚轮 | 缩放 |
| 左键单击（不拖动） | 选中光标下的对象（高亮显示其边界） |
| `F` | 聚焦/框选已选中对象 |
| `H` | 隐藏/显示已选中对象 |
| `Esc` | 清除选择 |
| 参数面板 | 拖动滑块实时调整 splat 缩放比例/透明度 |

## 版本兼容性说明

`DisplayParamUI` 通过**反射**驱动渲染器的显示字段，因此我们的脚本无需先安装插件即可编译，且在插件更新后仍可正常使用。若已安装版本中 splat 缩放/透明度字段名称不同，请在 Inspector 的 `DisplayParamUI` 组件上设置对应的成员名称——这是唯一需要验证的连接点。相机、选择和场景管理脚本与插件完全解耦。

## 文件说明

| 脚本 | 职责 |
|---|---|
| `OrbitCameraController.cs` | 浏览 / 缩放 / 平移；`Frame(Bounds)` 用于聚焦 |
| `SplatSceneManager.cs` | 注册表 + 点击选择 + F/H/Esc 路由 |
| `SplatSelectable.cs` | 单对象拾取代理（碰撞体边界）+ 高亮 |
| `DisplayParamUI.cs` | 运行时滑块 → `GaussianSplatRenderer`（通过反射） |

VR / 高级操作（clarte53 查看器，VR-GS 风格抓取/变形）：
[`../docs/07-extensions.md`](../docs/07-extensions.md)。
