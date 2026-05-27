# 06 · Unity 集成与交互

这是"最后一公里"：将一个 `.ply` 高斯模型转变为可交互的 Unity 场景，
实现**浏览 / 缩放 / 平移 / 选择 / 显示参数**控制——这是要求的
基础交互。

## 为什么选择 aras-p/UnityGaussianSplatting

- 直接导入**原始 3DGS `.ply`**（及 SPZ）；新版本只需将
  `.ply` 拖入项目，导入器即可构建一个 `GaussianSplatAsset`。
- GPU 加速排序；在 **Unity 6 LTS** 上运行，支持 PC/Mac/移动端；**无需运行时 CUDA**。
- 提供带可调显示参数的运行时 `GaussianSplatRenderer` 组件。

（clarte53 VR 查看器是 VR 进阶目标的备选方案——参见 `docs/07`。）

## 配置步骤

1. **Unity 6 LTS** 项目（推荐使用 URP）。将其置于 `unity/` 目录下，使被追踪的
   文件夹（`Assets/`、`Packages/`、`ProjectSettings/`）能够干净地进行版本管理。
2. 安装插件——参照 https://github.com/aras-p/UnityGaussianSplatting ：
   - 通过 Package Manager → **Add package from git URL** 添加，*或者*克隆后将其
     `package/` 文件夹下的本地 `package.json` 添加到项目中。
3. **导入模型：**将 `result/model.ply` 拖入项目（或在旧版本中使用
   `Tools → Gaussian Splats → Create GaussianSplatAsset`）。如有提示，选择
   一个压缩预设。
4. 创建一个空的 GameObject，添加 **`GaussianSplatRenderer`** 组件，并指定资产。
5. 将我们的脚本从 [`../unity/Assets/Scripts/`](../unity/Assets/Scripts/) 复制到
   项目中并完成连接（见下文）。
6. 按下 **Play**。

## 我们的交互脚本（`unity/Assets/Scripts/`）

| 脚本 | 交互（任务要求） | 挂载目标 |
|---|---|---|
| `OrbitCameraController.cs` | **浏览 / 缩放 / 平移** —— 轨道旋转（左键拖拽）、缩放（滚轮）、平移（右键/中键拖拽）、聚焦（F） | 主相机 |
| `SplatSceneManager.cs` | **场景组织** —— 注册高斯点（splat）对象、对目标取景/聚焦、切换可见性 | 一个空的 `SceneManager` 对象 |
| `SplatSelectable.cs` | **选择** —— 射线检测拾取 + 高亮；向管理器上报选中状态 | 每个可选择的高斯点（splat）对象（需带碰撞体/包围盒） |
| `DisplayParamUI.cs` | **显示参数调节** —— 高斯点（splat）缩放 / 不透明度 / SH（点大小）的滑块及重置 | 一个 UI Canvas |

> **集成注意事项（请与已安装的插件版本核对）：** `DisplayParamUI.cs` 中的显示
> 参数会设置 `GaussianSplatRenderer` 上的字段（例如高斯点（splat）缩放和
> 不透明度/SH 阶数旋钮）。字段/属性名称在不同插件版本间有所变化，
> 因此脚本将它们集中在一个清晰标注的区域内——请将这几行更新以匹配你的版本。
> 其余部分（相机、射线检测、UI 连接）与插件无关，均可正常使用。

## 高斯对象的选择方式

高斯对象没有网格碰撞体，因此选择使用**包围盒代理**：每个高斯点（splat）
对象配备一个 `BoxCollider`（或从资产包围盒计算得到的 AABB）。`SplatSelectable`
在点击时从相机发出射线检测，命中后请求 `SplatSceneManager` 将其标记为
已选中并进行视觉区分（例如微调高斯点（splat）缩放 / 着色 / 描边包围盒）。
如需更精细的逐高斯选择，参见 `docs/07` 中的 VR-GS 风格笼体分组——
超出基础范围。

## 场景组织

`SplatSceneManager` 维护已注册高斯点（splat）对象的列表，使演示可以在
一个场景中容纳**多个重建对象**，对其中任意一个取景（供相机聚焦使用），
切换可见性，并路由选中状态。这满足了"自动组织场景 / scene organization"
的要求，并为演示提供了结构支撑。

## 性能说明（供 `docs/07` 优化参考）

- 使用导入器的**压缩**/质量预设；在后端的
  `convert` 阶段针对较弱的 GPU 限制高斯点（splat）数量。
- 3DGS 受**填充率 / 排序**瓶颈制约——远处更少、更大的高斯点（splat）有助于
  性能；这也是 **Mip-Splatting** 方向的实际动机。
- 使用 Unity Profiler 进行性能分析；关注 GPU 排序开销和过度绘制。
- 对于 VR，应尽早确定单眼帧率预算——在桌面端表现良好的高斯点（splat）
  数量在 VR 帧率下可能无法维持。

## 连接到训练后端（可选便利功能）

为获得更流畅的演示效果，可以让 Unity 通过 API
（`GET /api/jobs/{id}/result`）使用 `UnityWebRequest` 拉取最新结果，
保存为临时 `.ply` 文件，并在运行时通过插件的运行时加载路径加载。
基础演示也可以直接使用上述 Editor 导入流程——更简单，且评分时更可靠。
