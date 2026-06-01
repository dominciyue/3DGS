# Unity 3DGS 一键导入工具

这个工具用于把标准 3D Gaussian Splatting 输出目录一键导入 Unity。它不自己实现 3DGS 渲染，而是封装 Aras 的 UnityGaussianSplatting 插件，并提供 Agent 可调用的 Python 函数。

## 提交内容

提交整个目录即可：

```text
tools/unity_3dgs_importer/
  agent_tool.py
  README.md
```

核心函数在 `agent_tool.py` 中：

```python
one_click_import_3dgs_to_unity(...)
```

## 一键调用

```python
from tools.unity_3dgs_importer.agent_tool import one_click_import_3dgs_to_unity

result = one_click_import_3dgs_to_unity(
    gs_output_dir="D:/program/ARVR/project/3DGS",
    unity_project_dir="D:/useful tool/Unity/project/3DGS",
    scene_name="Demo3DGSScene",
    unity_exe="D:/useful tool/Unity/Editor/2022.3.17f1c1/Editor/Unity.exe",
    graphics_api="d3d12",
)
```

这个函数会自动完成：

1. 查找最高迭代目录下的 `point_cloud.ply`。
2. 给 Unity 工程添加 `UnityGaussianSplatting` 插件依赖。
3. 复制 `point_cloud.ply`、`cameras.json`、`exposure.json`、`cfg_args` 到 Unity 工程。
4. 写入 Unity 侧自动导入脚本和交互脚本。
5. 启动 Unity 命令行模式。
6. 调用插件把 `.ply` 转成 GaussianSplat asset。
7. 自动生成并保存 Unity 场景。

## 命令行调用

```powershell
python tools\unity_3dgs_importer\agent_tool.py `
  --gs-output-dir "D:\program\ARVR\project\3DGS" `
  --unity-project-dir "D:\useful tool\Unity\project\3DGS" `
  --scene-name "Demo3DGSScene" `
  --run-unity-import `
  --unity-exe "D:\useful tool\Unity\Editor\2022.3.17f1c1\Editor\Unity.exe" `
  --graphics-api d3d12
```

如果目标机器 D3D12 不可用，可以改成：

```powershell
--graphics-api vulkan
```

## 运行前注意

运行一键导入前建议关闭正在打开的 Unity Editor，否则 Unity 项目锁可能导致命令行导入失败。

第一次运行时 Unity Package Manager 需要下载插件，因此目标机器需要能访问 GitHub。

Windows 下建议使用 D3D12 或 Vulkan。DX11 通常无法满足 UnityGaussianSplatting 的 compute shader 要求。

## 生成后的操作方式

生成的 Unity 场景会带一个基础 3D 飞行浏览控制器：

- 鼠标左移：相对于当前画面向左看
- 鼠标右移：相对于当前画面向右看
- 鼠标上移：相对于当前画面向上看
- 鼠标下移：相对于当前画面向下看
- `W/A/S/D`：根据当前视角方向移动，适合 3D 空间自由穿梭
- `Space`：上升
- `Left Ctrl`：下降
- `Q/E`：绕当前镜头前向轴旋转画面
- `Shift`：加速移动
- `Tab`：锁定/释放鼠标
- `R`：清除异常滚转
- 鼠标左键或右键点击 Game 视图：重新锁定鼠标

这个控制方式更接近 Unity Scene 视图的飞行模式：看向哪里，`W/S` 就沿当前视线前后移动。

## 手动兜底

如果命令行自动导入失败，可以打开 Unity 后手动执行：

```text
Agent3DGS > Auto Import Configured PLY
```

如果插件还没有编译完成，等 Unity 右下角编译完成后再执行一次。
