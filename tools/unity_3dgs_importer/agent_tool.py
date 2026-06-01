from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


GAUSSIAN_SPLATTING_PACKAGE = "org.nesnausk.gaussian-splatting"
GAUSSIAN_SPLATTING_GIT_URL = (
    "https://github.com/aras-p/UnityGaussianSplatting.git?path=/package#v1.1.1"
)


@dataclass
class ImportResult:
    unity_project: str
    source_ply: str
    copied_ply: str
    unity_config: str
    scene_name: str
    package_added: bool
    files_written: list[str]
    next_steps: list[str]
    unity_exe: str | None = None
    unity_exit_code: int | None = None
    unity_log: str | None = None


def one_click_import_3dgs_to_unity(
    gs_output_dir: str | Path,
    unity_project_dir: str | Path,
    scene_name: str = "Generated3DGSScene",
    unity_exe: str | Path | None = None,
    graphics_api: str = "d3d12",
    run_unity_import: bool = True,
) -> ImportResult:
    """One-call Agent tool: prepare Unity, convert PLY, and generate a scene.

    The Python side installs/copies/configures files. The Unity side then runs
    Agent3DGS.Editor.Agent3DGSAutoImporter.ImportFromCommandLine, which calls
    the UnityGaussianSplatting importer and creates the scene.
    """

    result = import_3dgs_to_unity(
        gs_output_dir=gs_output_dir,
        unity_project_dir=unity_project_dir,
        scene_name=scene_name,
    )
    if not run_unity_import:
        return result

    unity_path = _resolve_unity_exe(unity_exe, Path(unity_project_dir))
    log_path = Path(unity_project_dir).resolve() / "Logs" / "agent3dgs_import.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    args = [
        str(unity_path),
        "-batchmode",
        "-quit",
        "-projectPath",
        str(Path(unity_project_dir).resolve()),
        "-executeMethod",
        "Agent3DGS.Editor.Agent3DGSAutoImporter.ImportFromCommandLine",
        "-agent3dgsConfig",
        result.unity_config,
        "-logFile",
        str(log_path),
    ]
    if graphics_api.lower() in {"d3d12", "direct3d12", "dx12"}:
        args.append("-force-d3d12")
    elif graphics_api.lower() == "vulkan":
        args.append("-force-vulkan")

    completed = subprocess.run(args, check=False)
    result.unity_exe = str(unity_path)
    result.unity_exit_code = completed.returncode
    result.unity_log = str(log_path)
    if completed.returncode != 0:
        raise RuntimeError(
            f"Unity import failed with exit code {completed.returncode}. "
            f"See log: {log_path}"
        )
    return result


def _resolve_unity_exe(unity_exe: str | Path | None, unity_project_dir: Path) -> Path:
    if unity_exe:
        path = Path(unity_exe).expanduser().resolve()
        if not path.is_file():
            raise FileNotFoundError(f"Unity.exe not found: {path}")
        return path

    version_file = unity_project_dir / "ProjectSettings" / "ProjectVersion.txt"
    version = None
    if version_file.is_file():
        match = re.search(r"m_EditorVersion:\s*(\S+)", version_file.read_text(encoding="utf-8"))
        if match:
            version = match.group(1)

    candidates: list[Path] = []
    if version:
        candidates.extend(
            [
                Path(f"C:/Program Files/Unity/Hub/Editor/{version}/Editor/Unity.exe"),
                Path(f"D:/useful tool/Unity/Editor/{version}/Editor/Unity.exe"),
            ]
        )
    candidates.extend(
        [
            Path("C:/Program Files/Unity/Hub/Editor"),
            Path("D:/useful tool/Unity/Editor"),
        ]
    )

    for candidate in candidates:
        if candidate.is_file():
            return candidate
        if candidate.is_dir():
            found = sorted(candidate.glob("*/Editor/Unity.exe"), reverse=True)
            if found:
                return found[0]

    raise FileNotFoundError("Unity.exe not found. Pass unity_exe explicitly.")


def import_3dgs_to_unity(
    gs_output_dir: str | Path,
    unity_project_dir: str | Path,
    scene_name: str = "Generated3DGSScene",
    asset_folder: str = "Assets/Generated3DGS",
    install_package: bool = True,
    overwrite: bool = True,
    dry_run: bool = False,
) -> ImportResult:
    """Prepare a Unity project to import a 3D Gaussian Splatting PLY.

    This is intentionally a thin Agent tool around Aras Pranckevicius'
    UnityGaussianSplatting package. It does not reimplement 3DGS rendering.

    Args:
        gs_output_dir: Folder produced by the 3DGS training pipeline.
        unity_project_dir: Unity project root containing Assets/ and Packages/.
        scene_name: Name used for the generated Unity asset folder and scene.
        asset_folder: Unity-relative destination folder.
        install_package: Add the Gaussian Splatting git package to manifest.json.
        overwrite: Replace an existing copied PLY/scripts.
        dry_run: Return planned actions without writing files.
    """

    gs_dir = Path(gs_output_dir).expanduser().resolve()
    unity_dir = Path(unity_project_dir).expanduser().resolve()
    _validate_unity_project(unity_dir)

    source_ply = _find_best_ply(gs_dir)
    safe_scene_name = _safe_unity_name(scene_name)
    dest_dir = unity_dir / asset_folder / safe_scene_name
    dest_ply = dest_dir / "point_cloud.ply"
    files_written: list[str] = []

    package_added = False
    if install_package:
        package_added = _ensure_package(unity_dir, dry_run)
        if package_added:
            files_written.append(str(unity_dir / "Packages" / "manifest.json"))

    if not dry_run:
        dest_dir.mkdir(parents=True, exist_ok=True)
        if dest_ply.exists() and not overwrite:
            raise FileExistsError(f"Destination PLY already exists: {dest_ply}")
        if not (dest_ply.exists() and dest_ply.stat().st_size == source_ply.stat().st_size):
            shutil.copy2(source_ply, dest_ply)
    files_written.append(str(dest_ply))

    for sidecar_name in ("cameras.json", "exposure.json", "cfg_args"):
        sidecar = gs_dir / sidecar_name
        if sidecar.is_file():
            sidecar_dest = dest_dir / sidecar_name
            if not dry_run:
                if sidecar_dest.exists() and not overwrite:
                    raise FileExistsError(f"Destination file already exists: {sidecar_dest}")
                if not (sidecar_dest.exists() and sidecar_dest.stat().st_size == sidecar.stat().st_size):
                    shutil.copy2(sidecar, sidecar_dest)
            files_written.append(str(sidecar_dest))

    helper_files = {
        unity_dir / "Assets" / "Agent3DGS" / "Runtime" / "Agent3DGSOrbitCamera.cs": ORBIT_CAMERA_CS,
        unity_dir / "Assets" / "Agent3DGS" / "Runtime" / "Agent3DGSRuntimePanel.cs": RUNTIME_PANEL_CS,
        unity_dir / "Assets" / "Agent3DGS" / "Editor" / "Agent3DGSSceneBuilder.cs": SCENE_BUILDER_CS,
        unity_dir / "Assets" / "Agent3DGS" / "Editor" / "Agent3DGSAutoImporter.cs": AUTO_IMPORTER_CS,
        dest_dir / "README_ImportSteps.md": _readme_text(source_ply, dest_ply, safe_scene_name),
    }
    for path, content in helper_files.items():
        if not dry_run:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists() and not overwrite:
                raise FileExistsError(f"Destination file already exists: {path}")
            path.write_text(content, encoding="utf-8")
        files_written.append(str(path))

    config_path = dest_dir / "agent3dgs_import_config.json"
    config = {
        "inputPlyAbsolutePath": str(dest_ply),
        "outputFolder": _to_unity_path(dest_dir, unity_dir),
        "sceneAssetPath": f"Assets/Generated3DGS/{safe_scene_name}/{safe_scene_name}.unity",
        "sceneName": safe_scene_name,
        "quality": "Medium",
        "importCameras": True,
    }
    if not dry_run:
        config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    files_written.append(str(config_path))

    return ImportResult(
        unity_project=str(unity_dir),
        source_ply=str(source_ply),
        copied_ply=str(dest_ply),
        unity_config=str(config_path),
        scene_name=safe_scene_name,
        package_added=package_added,
        files_written=files_written,
        next_steps=[
            "Open the Unity project and let Package Manager resolve the Gaussian Splatting package.",
            "Use Agent3DGS > Auto Import Configured PLY to convert the PLY and generate the scene.",
            "For command-line automation, run Unity with -executeMethod Agent3DGS.Editor.Agent3DGSAutoImporter.ImportFromCommandLine -agent3dgsConfig <config-json>.",
            "Enter Play Mode to browse with mouse look + WASD flight movement, Space/Ctrl for extra vertical movement, and F1 for optional controls.",
        ],
    )


def _validate_unity_project(unity_dir: Path) -> None:
    if not (unity_dir / "Assets").is_dir():
        raise FileNotFoundError(f"Unity Assets folder not found: {unity_dir / 'Assets'}")
    if not (unity_dir / "Packages" / "manifest.json").is_file():
        raise FileNotFoundError(
            f"Unity package manifest not found: {unity_dir / 'Packages' / 'manifest.json'}"
        )


def _find_best_ply(gs_dir: Path) -> Path:
    if not gs_dir.is_dir():
        raise FileNotFoundError(f"3DGS output folder not found: {gs_dir}")

    candidates = list(gs_dir.glob("point_cloud/iteration_*/point_cloud.ply"))
    if candidates:
        return max(candidates, key=_iteration_number)

    fallback = gs_dir / "point_cloud.ply"
    if fallback.is_file():
        return fallback

    ply_files = list(gs_dir.rglob("*.ply"))
    if not ply_files:
        raise FileNotFoundError(f"No .ply files found under {gs_dir}")
    return max(ply_files, key=lambda p: p.stat().st_mtime)


def _iteration_number(path: Path) -> int:
    match = re.search(r"iteration_(\d+)", str(path))
    return int(match.group(1)) if match else -1


def _ensure_package(unity_dir: Path, dry_run: bool) -> bool:
    manifest_path = unity_dir / "Packages" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    deps: dict[str, Any] = manifest.setdefault("dependencies", {})

    if deps.get(GAUSSIAN_SPLATTING_PACKAGE) == GAUSSIAN_SPLATTING_GIT_URL:
        return False

    deps[GAUSSIAN_SPLATTING_PACKAGE] = GAUSSIAN_SPLATTING_GIT_URL
    if not dry_run:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return True


def _safe_unity_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_\-]+", "_", name.strip())
    return cleaned or "Generated3DGSScene"


def _to_unity_path(path: Path, unity_dir: Path) -> str:
    rel = path.resolve().relative_to(unity_dir.resolve())
    return rel.as_posix()


def _readme_text(source_ply: Path, dest_ply: Path, scene_name: str) -> str:
    return f"""# Agent3DGS Import

Source PLY:

`{source_ply}`

Unity copy:

`{dest_ply}`

Scene name:

`{scene_name}`

## Unity steps

1. Wait for Package Manager to finish resolving `org.nesnausk.gaussian-splatting`.
2. Run `Agent3DGS > Auto Import Configured PLY`.
3. Open the generated scene and enter Play Mode.

Fallback manual path:

1. Open `Tools > Gaussian Splats > Create GaussianSplatAsset`.
2. Set `Input PLY/SPZ File` to the copied `point_cloud.ply`.
3. Save the generated asset in this folder.
4. Select the generated `GaussianSplat` asset.
5. Run `Agent3DGS > Build Scene From Selected GaussianSplat Asset`.
"""


ORBIT_CAMERA_CS = r'''using UnityEngine;

namespace Agent3DGS
{
    public sealed class Agent3DGSOrbitCamera : MonoBehaviour
    {
        [SerializeField] private float moveSpeed = 3.5f;
        [SerializeField] private float fastMultiplier = 4f;
        [SerializeField] private float lookSensitivity = 2.5f;
        [SerializeField] private float rollSpeed = 90f;
        [SerializeField] private bool invertY = false;
        [SerializeField] private bool lockCursorOnStart = true;
        [SerializeField] private KeyCode toggleCursorKey = KeyCode.Tab;
        [SerializeField] private KeyCode resetViewKey = KeyCode.R;

        private float yaw;
        private float pitch;
        private bool cursorLocked;

        private void Awake()
        {
            ResetAnglesFromCurrentForward();
            cursorLocked = lockCursorOnStart;
            ApplyCursorState();
        }

        private void Update()
        {
            if (Input.GetMouseButtonDown(0) || Input.GetMouseButtonDown(1))
            {
                cursorLocked = true;
                ApplyCursorState();
            }

            if (Input.GetKeyDown(toggleCursorKey))
            {
                cursorLocked = !cursorLocked;
                ApplyCursorState();
            }

            if (Input.GetKeyDown(resetViewKey))
            {
                RemoveRoll();
            }

            if (cursorLocked)
            {
                float mouseX = Input.GetAxisRaw("Mouse X");
                float mouseY = Input.GetAxisRaw("Mouse Y");

                float pitchSign = invertY ? 1f : -1f;
                transform.Rotate(Vector3.up, mouseX * lookSensitivity, Space.Self);
                transform.Rotate(Vector3.right, mouseY * lookSensitivity * pitchSign, Space.Self);
            }

            float speed = moveSpeed * (Input.GetKey(KeyCode.LeftShift) ? fastMultiplier : 1f);
            Vector3 move =
                transform.right * Input.GetAxisRaw("Horizontal") +
                transform.forward * Input.GetAxisRaw("Vertical");

            if (Input.GetKey(KeyCode.Space)) move += Vector3.up;
            if (Input.GetKey(KeyCode.LeftControl)) move -= Vector3.up;
            transform.position += move.normalized * speed * Time.deltaTime;

            float roll = 0f;
            if (Input.GetKey(KeyCode.Q)) roll += 1f;
            if (Input.GetKey(KeyCode.E)) roll -= 1f;
            if (Mathf.Abs(roll) > 0.001f)
                transform.Rotate(Vector3.forward, roll * rollSpeed * Time.deltaTime, Space.Self);
        }

        private void ApplyCursorState()
        {
            Cursor.lockState = cursorLocked ? CursorLockMode.Locked : CursorLockMode.None;
            Cursor.visible = !cursorLocked;
        }

        private void ResetAnglesFromCurrentForward()
        {
            Vector3 forward = transform.forward.normalized;
            yaw = Mathf.Atan2(forward.x, forward.z) * Mathf.Rad2Deg;
            float flatLength = new Vector2(forward.x, forward.z).magnitude;
            pitch = Mathf.Atan2(forward.y, flatLength) * Mathf.Rad2Deg;
        }

        private void RemoveRoll()
        {
            Vector3 forward = transform.forward;
            if (forward.sqrMagnitude < 0.0001f) return;

            Vector3 up = Vector3.ProjectOnPlane(Vector3.up, forward);
            if (up.sqrMagnitude < 0.0001f)
                up = Vector3.ProjectOnPlane(transform.up, forward);

            transform.rotation = Quaternion.LookRotation(forward, up.normalized);
        }
    }
}
'''


RUNTIME_PANEL_CS = r'''using UnityEngine;

namespace Agent3DGS
{
    public sealed class Agent3DGSRuntimePanel : MonoBehaviour
    {
        [SerializeField] private Transform splatRoot;
        [SerializeField] private float scaleStep = 0.1f;
        [SerializeField] private bool showPanel = false;

        private bool visible;

        private void Awake()
        {
            visible = showPanel;
        }

        public void SetSplatRoot(Transform root)
        {
            splatRoot = root;
        }

        private void Update()
        {
            if (Input.GetKeyDown(KeyCode.F1))
                visible = !visible;
        }

        private void OnGUI()
        {
            if (!visible || splatRoot == null) return;

            GUI.matrix = Matrix4x4.TRS(Vector3.zero, Quaternion.identity, Vector3.one * 1.8f);
            const int width = 300;
            GUI.Box(new Rect(12, 12, width, 170), "3DGS Controls");

            GUILayout.BeginArea(new Rect(24, 40, width - 24, 130));
            if (!visible || splatRoot == null) return;
            GUILayout.Label("Move: WASD");
            GUILayout.Label("Up/Down: Space, Ctrl");
            GUILayout.Label("Roll: Q / E");
            GUILayout.Label("Look: move mouse");
            GUILayout.Label("Cursor: Tab | Reset: R | Panel: F1");

            GUILayout.Space(8);
            Vector3 scale = splatRoot.localScale;
            float next = GUILayout.HorizontalSlider(scale.x, 0.05f, 5f);
            splatRoot.localScale = Vector3.one * Mathf.Max(scaleStep, next);

            GUILayout.BeginHorizontal();
            if (GUILayout.Button("Rotate -15")) splatRoot.Rotate(Vector3.up, -15f, Space.World);
            if (GUILayout.Button("Rotate +15")) splatRoot.Rotate(Vector3.up, 15f, Space.World);
            GUILayout.EndHorizontal();

            if (GUILayout.Button(splatRoot.gameObject.activeSelf ? "Hide Splats" : "Show Splats"))
            {
                splatRoot.gameObject.SetActive(!splatRoot.gameObject.activeSelf);
            }

            GUILayout.EndArea();
        }
    }
}
'''


SCENE_BUILDER_CS = r'''using System;
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Agent3DGS.Editor
{
    public static class Agent3DGSSceneBuilder
    {
        [MenuItem("Agent3DGS/Build Scene From Selected GaussianSplat Asset")]
        public static void BuildScene()
        {
            UnityEngine.Object asset = Selection.activeObject;
            if (asset == null)
            {
                EditorUtility.DisplayDialog("Agent3DGS", "Select a generated GaussianSplat asset first.", "OK");
                return;
            }

            Type rendererType = FindType("GaussianSplatting.Runtime.GaussianSplatRenderer");
            if (rendererType == null)
            {
                EditorUtility.DisplayDialog("Agent3DGS", "GaussianSplatRenderer type was not found. Let Package Manager finish importing UnityGaussianSplatting first.", "OK");
                return;
            }

            BuildSceneFromAsset(asset, null);
        }

        public static void BuildSceneFromAsset(UnityEngine.Object asset, string sceneAssetPath)
        {
            if (asset == null)
            {
                throw new ArgumentNullException(nameof(asset));
            }

            Type rendererType = FindType("GaussianSplatting.Runtime.GaussianSplatRenderer");
            if (rendererType == null)
            {
                throw new InvalidOperationException("GaussianSplatRenderer type was not found.");
            }

            Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            scene.name = string.IsNullOrWhiteSpace(sceneAssetPath) ? "Generated3DGSScene" : System.IO.Path.GetFileNameWithoutExtension(sceneAssetPath);

            GameObject splat = new GameObject("GaussianSplatScene");
            Component renderer = splat.AddComponent(rendererType);
            AssignAsset(renderer, asset);
            splat.transform.rotation = Quaternion.Euler(-160f, 0f, 180f);

            GameObject cameraObject = new GameObject("Main Camera");
            Camera camera = cameraObject.AddComponent<Camera>();
            camera.tag = "MainCamera";
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(0.04f, 0.04f, 0.045f);
            cameraObject.transform.position = new Vector3(0f, 0.5f, -3f);
            cameraObject.transform.LookAt(Vector3.zero);
            cameraObject.AddComponent<Agent3DGS.Agent3DGSOrbitCamera>();

            GameObject lightObject = new GameObject("Directional Light");
            Light light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            lightObject.transform.rotation = Quaternion.Euler(50f, -30f, 0f);

            GameObject panelObject = new GameObject("Agent3DGS Runtime Panel");
            Agent3DGS.Agent3DGSRuntimePanel panel = panelObject.AddComponent<Agent3DGS.Agent3DGSRuntimePanel>();
            panel.SetSplatRoot(splat.transform);

            EditorSceneManager.MarkSceneDirty(scene);
            if (!string.IsNullOrWhiteSpace(sceneAssetPath))
            {
                System.IO.Directory.CreateDirectory(System.IO.Path.GetDirectoryName(sceneAssetPath));
                EditorSceneManager.SaveScene(scene, sceneAssetPath);
                AssetDatabase.Refresh();
            }
            else
            {
                EditorUtility.DisplayDialog("Agent3DGS", "Scene generated. Save it with File > Save As when ready.", "OK");
            }
        }

        private static Type FindType(string fullName)
        {
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type type = assembly.GetType(fullName);
                if (type != null) return type;
            }
            return null;
        }

        private static void AssignAsset(Component renderer, UnityEngine.Object asset)
        {
            SerializedObject serialized = new SerializedObject(renderer);
            SerializedProperty iterator = serialized.GetIterator();
            bool enterChildren = true;
            while (iterator.NextVisible(enterChildren))
            {
                enterChildren = false;
                if (iterator.propertyType == SerializedPropertyType.ObjectReference &&
                    iterator.displayName.ToLowerInvariant().Contains("asset"))
                {
                    iterator.objectReferenceValue = asset;
                    serialized.ApplyModifiedProperties();
                    return;
                }
            }

            Debug.LogWarning("Agent3DGS could not auto-assign the selected asset. Drag it into the GaussianSplatRenderer Asset field manually.");
        }
    }
}
'''


AUTO_IMPORTER_CS = r'''using System;
using System.IO;
using System.Reflection;
using UnityEditor;
using UnityEngine;

namespace Agent3DGS.Editor
{
    public static class Agent3DGSAutoImporter
    {
        [Serializable]
        private sealed class ImportConfig
        {
            public string inputPlyAbsolutePath;
            public string outputFolder;
            public string sceneAssetPath;
            public string sceneName;
            public string quality = "Medium";
            public bool importCameras = true;
        }

        [MenuItem("Agent3DGS/Auto Import Configured PLY")]
        public static void ImportConfiguredPly()
        {
            ImportFromConfigPath(FindDefaultConfigPath(), false);
        }

        public static void ImportFromCommandLine()
        {
            string configPath = GetArgument("-agent3dgsConfig") ?? "Assets/Generated3DGS/Demo3DGSScene/agent3dgs_import_config.json";
            try
            {
                ImportFromConfigPath(configPath, true);
                UnityEditor.EditorApplication.Exit(0);
            }
            catch (Exception ex)
            {
                Debug.LogException(ex);
                UnityEditor.EditorApplication.Exit(1);
            }
        }

        public static void ImportFromConfigPath(string configPath, bool batchMode)
        {
            string fullConfigPath = Path.IsPathRooted(configPath)
                ? configPath
                : Path.Combine(Directory.GetCurrentDirectory(), configPath);
            if (!File.Exists(fullConfigPath))
                throw new FileNotFoundException("Agent3DGS import config not found.", fullConfigPath);

            ImportConfig config = JsonUtility.FromJson<ImportConfig>(File.ReadAllText(fullConfigPath));
            if (config == null || string.IsNullOrWhiteSpace(config.inputPlyAbsolutePath))
                throw new InvalidDataException("Agent3DGS import config is missing inputPlyAbsolutePath.");
            if (!File.Exists(config.inputPlyAbsolutePath))
                throw new FileNotFoundException("Input PLY not found.", config.inputPlyAbsolutePath);
            if (string.IsNullOrWhiteSpace(config.outputFolder))
                config.outputFolder = "Assets/Generated3DGS/Demo3DGSScene";
            if (string.IsNullOrWhiteSpace(config.sceneAssetPath))
                config.sceneAssetPath = $"{config.outputFolder}/Generated3DGSScene.unity";

            AssetDatabase.Refresh();
            UnityEngine.Object asset = CreateGaussianSplatAsset(config);
            Agent3DGSSceneBuilder.BuildSceneFromAsset(asset, config.sceneAssetPath);
            Selection.activeObject = asset;
            Debug.Log($"Agent3DGS imported {config.inputPlyAbsolutePath} and generated {config.sceneAssetPath}");

            if (!batchMode)
                EditorUtility.DisplayDialog("Agent3DGS", $"Import complete.\nScene: {config.sceneAssetPath}", "OK");
        }

        private static UnityEngine.Object CreateGaussianSplatAsset(ImportConfig config)
        {
            Type creatorType = FindType("GaussianSplatting.Editor.GaussianSplatAssetCreator");
            if (creatorType == null)
                throw new InvalidOperationException("GaussianSplatAssetCreator was not found. Let Package Manager finish importing UnityGaussianSplatting first.");

            UnityEngine.Object creator = ScriptableObject.CreateInstance(creatorType);
            SetField(creatorType, creator, "m_InputFile", config.inputPlyAbsolutePath);
            SetField(creatorType, creator, "m_OutputFolder", config.outputFolder);
            SetField(creatorType, creator, "m_ImportCameras", config.importCameras);

            Type qualityType = creatorType.GetNestedType("DataQuality", BindingFlags.NonPublic);
            if (qualityType != null)
            {
                object quality = Enum.Parse(qualityType, string.IsNullOrWhiteSpace(config.quality) ? "Medium" : config.quality);
                SetField(creatorType, creator, "m_Quality", quality);
            }

            InvokeIfExists(creatorType, creator, "ApplyQualityLevel");
            MethodInfo createAsset = creatorType.GetMethod("CreateAsset", BindingFlags.Instance | BindingFlags.NonPublic);
            if (createAsset == null)
                throw new MissingMethodException(creatorType.FullName, "CreateAsset");
            createAsset.Invoke(creator, null);

            UnityEngine.Object asset = Selection.activeObject;
            if (asset == null || asset.GetType().FullName != "GaussianSplatting.Runtime.GaussianSplatAsset")
                asset = FindGaussianSplatAsset(config.outputFolder);
            if (asset == null)
                throw new FileNotFoundException("GaussianSplat asset was not created.", config.outputFolder);
            return asset;
        }

        private static UnityEngine.Object FindGaussianSplatAsset(string outputFolder)
        {
            string[] guids = AssetDatabase.FindAssets("t:GaussianSplatAsset", new[] { outputFolder });
            foreach (string guid in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                UnityEngine.Object asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(path);
                if (asset != null)
                    return asset;
            }

            string[] assetGuids = AssetDatabase.FindAssets("t:ScriptableObject", new[] { outputFolder });
            foreach (string guid in assetGuids)
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                UnityEngine.Object asset = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(path);
                if (asset != null && asset.GetType().FullName == "GaussianSplatting.Runtime.GaussianSplatAsset")
                    return asset;
            }
            return null;
        }

        private static void SetField(Type type, object target, string name, object value)
        {
            FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null)
                throw new MissingFieldException(type.FullName, name);
            field.SetValue(target, value);
        }

        private static void InvokeIfExists(Type type, object target, string name)
        {
            MethodInfo method = type.GetMethod(name, BindingFlags.Instance | BindingFlags.NonPublic);
            method?.Invoke(target, null);
        }

        private static Type FindType(string fullName)
        {
            foreach (Assembly assembly in AppDomain.CurrentDomain.GetAssemblies())
            {
                Type type = assembly.GetType(fullName);
                if (type != null) return type;
            }
            return null;
        }

        private static string GetArgument(string name)
        {
            string[] args = Environment.GetCommandLineArgs();
            for (int i = 0; i < args.Length - 1; i++)
            {
                if (args[i] == name)
                    return args[i + 1];
            }
            return null;
        }

        private static string FindDefaultConfigPath()
        {
            string[] configs = Directory.GetFiles(
                Path.Combine(Directory.GetCurrentDirectory(), "Assets/Generated3DGS"),
                "agent3dgs_import_config.json",
                SearchOption.AllDirectories);
            if (configs.Length == 0)
                throw new FileNotFoundException("No agent3dgs_import_config.json found under Assets/Generated3DGS.");
            Array.Sort(configs, (a, b) => File.GetLastWriteTimeUtc(b).CompareTo(File.GetLastWriteTimeUtc(a)));
            return configs[0];
        }
    }
}
'''


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a Unity project for 3DGS PLY import.")
    parser.add_argument("--gs-output-dir", required=True)
    parser.add_argument("--unity-project-dir", required=True)
    parser.add_argument("--scene-name", default="Generated3DGSScene")
    parser.add_argument("--asset-folder", default="Assets/Generated3DGS")
    parser.add_argument("--run-unity-import", action="store_true")
    parser.add_argument("--unity-exe")
    parser.add_argument("--graphics-api", default="d3d12", choices=["d3d12", "vulkan", "none"])
    parser.add_argument("--no-package", action="store_true")
    parser.add_argument("--no-overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.run_unity_import:
        if args.no_package or args.no_overwrite or args.dry_run or args.asset_folder != "Assets/Generated3DGS":
            raise SystemExit("--run-unity-import uses the default one-click path; do not combine it with dry-run/no-package/no-overwrite/custom asset-folder.")
        result = one_click_import_3dgs_to_unity(
            gs_output_dir=args.gs_output_dir,
            unity_project_dir=args.unity_project_dir,
            scene_name=args.scene_name,
            unity_exe=args.unity_exe,
            graphics_api=args.graphics_api,
            run_unity_import=True,
        )
    else:
        result = import_3dgs_to_unity(
            gs_output_dir=args.gs_output_dir,
            unity_project_dir=args.unity_project_dir,
            scene_name=args.scene_name,
            asset_folder=args.asset_folder,
            install_package=not args.no_package,
            overwrite=not args.no_overwrite,
            dry_run=args.dry_run,
        )
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
