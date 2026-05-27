# Unity — Interactive 3DGS Viewer

The "last mile": load a produced `.ply` and make it interactive. These C# scripts give
the baseline interactions the project requires — **browse, zoom, pan, select, and
adjust display parameters** — on top of the
[aras-p/UnityGaussianSplatting](https://github.com/aras-p/UnityGaussianSplatting) renderer.

> This folder holds **our scripts + setup notes**, not a full Unity project. Create the
> project locally (only `Assets/`, `Packages/`, `ProjectSettings/` are tracked — caches
> and build output are ignored by the repo `.gitignore`). Full walkthrough:
> [`../docs/06-unity-integration.md`](../docs/06-unity-integration.md).

## Setup (≈10 minutes)

1. **Unity 6 LTS** project (URP recommended), created under this `unity/` folder.
2. Install **aras-p/UnityGaussianSplatting** (Package Manager → *Add package from git
   URL*, or clone and add the local package). Follow its README.
3. Copy `Assets/Scripts/*.cs` (this folder) into the project.
4. **Import a model:** drag a `.ply` (e.g. a public sample, or one from the backend)
   into the project — the importer builds a `GaussianSplatAsset`.
5. Wire up the scene (below) and press **Play**.

## Scene wiring

| GameObject | Components | Notes |
|---|---|---|
| **Main Camera** | `OrbitCameraController` | left-drag orbit · right/middle-drag pan · wheel zoom |
| **Splat object** | `GaussianSplatRenderer` (plugin) + `BoxCollider` + `SplatSelectable` | size the BoxCollider to the model — it's the pick/focus proxy |
| **SceneManager** (empty) | `SplatSceneManager` | assign the camera + (optional) the Display UI |
| **UI** (empty) | `DisplayParamUI` | on-screen sliders; no Canvas needed (IMGUI) |

Multiple splat objects? Give each its own `BoxCollider` + `SplatSelectable`; the manager
tracks them all and routes selection/focus.

## Controls

| Input | Action |
|---|---|
| Left-drag | orbit | 
| Right/Middle-drag | pan |
| Mouse wheel | zoom |
| Left-click (no drag) | select object under cursor (highlights its bounds) |
| `F` | focus/frame the selected object |
| `H` | hide/show the selected object |
| `Esc` | clear selection |
| Params panel | drag sliders to change splat scale / opacity live |

## The one version-specific bit

`DisplayParamUI` drives the renderer's display fields **by reflection**, so our scripts
compile before the plugin is installed and survive plugin updates. If your installed
version names the splat-scale/opacity fields differently, set the member names on the
`DisplayParamUI` component in the Inspector — that's the only wiring to verify. Camera,
selection, and scene-management scripts are fully plugin-agnostic.

## Files

| Script | Role |
|---|---|
| `OrbitCameraController.cs` | browse / zoom / pan; `Frame(Bounds)` for focus |
| `SplatSceneManager.cs` | registry + click-to-select + F/H/Esc routing |
| `SplatSelectable.cs` | per-object pick proxy (collider bounds) + highlight |
| `DisplayParamUI.cs` | runtime sliders → `GaussianSplatRenderer` (via reflection) |

VR / advanced manipulation (clarte53 viewer, VR-GS-style grab/deform):
[`../docs/07-extensions.md`](../docs/07-extensions.md).
