# 06 · Unity Integration & Interaction

This is the "last mile": turn a `.ply` Gaussian model into an interactive Unity scene
with **browse / zoom / pan / select / display-parameter** controls — the required
baseline interactions.

## Why aras-p/UnityGaussianSplatting

- Imports the **original 3DGS `.ply`** directly (and SPZ); recent versions: just drag
  the `.ply` into the project and an importer builds a `GaussianSplatAsset`.
- GPU-accelerated sorting; runs on **Unity 6 LTS**, PC/Mac/mobile; **no runtime CUDA**.
- Has a runtime `GaussianSplatRenderer` component with tunable display params.

(The clarte53 VR viewer is the alternative for the VR stretch goal — see `docs/07`.)

## Setup

1. **Unity 6 LTS** project (URP recommended). Keep it under `unity/` so the tracked
   folders (`Assets/`, `Packages/`, `ProjectSettings/`) version cleanly.
2. Install the package — follow https://github.com/aras-p/UnityGaussianSplatting :
   - Package Manager → **Add package from git URL**, *or* clone it and add the local
     `package.json` under its `package/` folder.
3. **Import a model:** drag `result/model.ply` into the project (or use
   `Tools → Gaussian Splats → Create GaussianSplatAsset` on older versions). Pick a
   compression preset if offered.
4. Create an empty GameObject, add **`GaussianSplatRenderer`**, assign the asset.
5. Copy our scripts from [`../unity/Assets/Scripts/`](../unity/Assets/Scripts/) into the
   project and wire them up (below).
6. Press **Play**.

## Our interaction scripts (`unity/Assets/Scripts/`)

| Script | Interaction (assignment requirement) | Attach to |
|---|---|---|
| `OrbitCameraController.cs` | **browse / zoom / pan** — orbit (LMB drag), zoom (wheel), pan (RMB/MMB drag), focus (F) | Main Camera |
| `SplatSceneManager.cs` | **scene organization** — register splat objects, frame/focus a target, toggle visibility | an empty `SceneManager` object |
| `SplatSelectable.cs` | **select** — raycast pick + highlight; reports selection to the manager | each selectable splat object (with a collider/bounds) |
| `DisplayParamUI.cs` | **display-parameter adjustment** — sliders for splat scale / opacity / SH (point size), reset | a UI Canvas |

> **Integration points (verify against your installed plugin version):** the display
> params in `DisplayParamUI.cs` set fields on `GaussianSplatRenderer` (e.g. a splat
> scale and an opacity/SH-order knob). Field/property names have changed across plugin
> versions, so the script centralizes them in one clearly-marked region — update those
> few lines to match your version. Everything else (camera, raycasting, UI wiring) is
> plugin-agnostic and works regardless.

## Selection of Gaussian objects — how

Gaussians have no mesh colliders, so selection uses **bounds proxies**: each splat
object gets a `BoxCollider` (or a computed AABB from the asset bounds). `SplatSelectable`
raycasts from the camera on click, and on hit asks `SplatSceneManager` to mark it
selected and visually distinguish it (e.g. nudge splat scale / tint / outline the
bounds). For finer, per-Gaussian selection, see VR-GS-style cage grouping in `docs/07`
— out of baseline scope.

## Scene organization

`SplatSceneManager` keeps a list of registered splat objects so the demo can hold
**multiple reconstructed objects** in one scene, frame any of them (used by the
camera's focus), toggle visibility, and route selection. This satisfies the
"自动组织场景 / scene organization" requirement and gives the demo structure.

## Performance notes (feeds `docs/07` optimization)

- Use the importer's **compression**/quality presets; cap splat count in the backend
  `convert` stage for weaker GPUs.
- 3DGS is **fill-rate / sort** bound — fewer, larger splats far away help; this is the
  practical motivation for the **Mip-Splatting** track.
- Profile with the Unity Profiler; watch GPU sort cost and overdraw.
- For VR, target the per-eye framerate budget early — splat counts that are fine on
  desktop may not hold at VR framerates.

## Connecting to the backend (optional convenience)

For a smoother demo you can have Unity pull the latest result via the API
(`GET /api/jobs/{id}/result`) with `UnityWebRequest`, save to a temp `.ply`, and load
it at runtime through the plugin's runtime-load path. The baseline demo can also just
use the Editor import flow above — simpler and reliable for grading.
