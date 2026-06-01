// Agent3DGS Studio UI — runtime 三联面板:文件夹输入 / 任务进度 / Agent 聊天。
// 把本文件放进 Unity 工程的 Assets/Agent3DGS/Runtime/。运行时 F2 切换显隐。
// 后端接口:POST /api/jobs/from-path、POST /api/chat、GET /api/jobs/{id}。

using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
#if UNITY_EDITOR
using System.Reflection;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
#endif

namespace Agent3DGS
{
    [AddComponentMenu("Agent3DGS/Studio UI (folder + status + chat)")]
    public sealed class Agent3DGSStudioUI : MonoBehaviour
    {
        [Header("后端")]
        [Tooltip("后端基址（与服务端 uvicorn 监听的端口一致）。")]
        public string backendBaseUrl = "http://localhost:8001";

        [Header("重建参数（初始值，运行时可改）")]
        public string sourceFolder = "";
        public string instruction = "high quality, anti-aliased";
        public string preset = ""; // "" / preview / balanced / high

        [Header("布局")]
        public int leftWidth = 340;
        public int rightWidth = 380;
        public KeyCode toggleKey = KeyCode.F2;

        // -- UI 状态 ----------------------------------------------------------
        private string _statusText = "（空闲）";
        private string _currentJobId = "";
        private readonly List<string> _logLines = new List<string>();
        private Vector2 _logScroll, _chatScroll;
        private bool _busy;
        private bool _visible = true;
        private string _chatInput = "";
        private string _chatBackend = "";
        private readonly List<ChatMsg> _chat = new List<ChatMsg>();

        // ② 训练完拉进当前场景按钮用
        private bool _loading;
        private string _resultPath = "";

        // -- 与后端 JSON 对应的可序列化类型（供 JsonUtility 使用） ----------------
        [System.Serializable] private class FromPathReq { public string path; public string instruction; public string preset; }
        [System.Serializable] private class JobIdResp { public string job_id; }
        [System.Serializable] private class StageInfo { public string name; public string status; public float progress; public string message; }
        [System.Serializable] private class TrainCfg { public string backend; public int iterations; }
        [System.Serializable] private class CfgInfo { public string preset; public TrainCfg train; }
        [System.Serializable] private class JobStatus { public string id; public string status; public string error; public int image_count; public string result_path; public StageInfo[] stages; public CfgInfo config; }
        [System.Serializable] private class ChatMsg { public string role; public string content; }
        [System.Serializable] private class ChatReq { public ChatMsg[] messages; }
        [System.Serializable] private class ChatResp { public string reply; public string backend; }

        private void Update()
        {
            if (Input.GetKeyDown(toggleKey)) _visible = !_visible;
        }

        private void OnGUI()
        {
            if (!_visible)
            {
                if (GUI.Button(new Rect(12, 12, 160, 26), "Studio (" + toggleKey + ")")) _visible = true;
                return;
            }
            DrawLeftPanel();
            DrawRightPanel();
        }

        // -------------------------------------------------- 左面板：任务提交 + 状态
        private void DrawLeftPanel()
        {
            int h = Screen.height - 24;
            GUILayout.BeginArea(new Rect(12, 12, leftWidth, h), GUI.skin.box);
            GUILayout.Label("3DGS · Agent  （" + toggleKey + " 切换）");
            GUILayout.Space(4);

            GUILayout.Label("图片文件夹（后端可读到的绝对路径）:");
            sourceFolder = GUILayout.TextField(sourceFolder ?? "");

            GUILayout.Label("给 Agent 的指令:");
            instruction = GUILayout.TextArea(instruction ?? "", GUILayout.Height(54));

            GUILayout.Label("质量预设:");
            string[] presets = { "自动", "preview", "balanced", "high" };
            int sel = string.IsNullOrEmpty(preset) ? 0 : System.Array.IndexOf(presets, preset);
            if (sel < 0) sel = 0;
            sel = GUILayout.SelectionGrid(sel, presets, 4);
            preset = sel == 0 ? "" : presets[sel];

            GUI.enabled = !_busy && !string.IsNullOrWhiteSpace(sourceFolder);
            if (GUILayout.Button(_busy ? "运行中…" : "生成场景"))
                StartCoroutine(SubmitFromPath());
            GUI.enabled = true;

            GUILayout.Space(6);
            GUILayout.Label("状态: " + _statusText);
            if (!string.IsNullOrEmpty(_currentJobId))
                GUILayout.Label("Job: " + _currentJobId);

#if UNITY_EDITOR
            GUI.enabled = !_loading && !string.IsNullOrEmpty(_resultPath);
            if (GUILayout.Button(_loading ? "导入中…" : "↩ 把 .ply 加入当前场景"))
                StartCoroutine(LoadResultIntoScene());
            GUI.enabled = true;
#else
            if (!string.IsNullOrEmpty(_resultPath))
                GUILayout.Label("结果(仅 Editor 可一键导入):\n" + _resultPath);
#endif

            GUILayout.Label("日志:");
            _logScroll = GUILayout.BeginScrollView(_logScroll, GUI.skin.box, GUILayout.ExpandHeight(true));
            for (int i = 0; i < _logLines.Count; i++) GUILayout.Label(_logLines[i]);
            GUILayout.EndScrollView();

            GUILayout.EndArea();
        }

        // -------------------------------------------------- 右面板：Agent 聊天
        private void DrawRightPanel()
        {
            int h = Screen.height - 24;
            int x = Screen.width - rightWidth - 12;
            GUILayout.BeginArea(new Rect(x, 12, rightWidth, h), GUI.skin.box);
            GUILayout.BeginHorizontal();
            GUILayout.Label("与 Agent 对话");
            GUILayout.FlexibleSpace();
            if (!string.IsNullOrEmpty(_chatBackend))
                GUILayout.Label("(" + _chatBackend + ")");
            GUILayout.EndHorizontal();

            _chatScroll = GUILayout.BeginScrollView(_chatScroll, GUI.skin.box, GUILayout.ExpandHeight(true));
            for (int i = 0; i < _chat.Count; i++)
            {
                var m = _chat[i];
                GUILayout.Label((m.role == "user" ? "▸ 你: " : "◂ Agent: ") + m.content);
                GUILayout.Space(2);
            }
            GUILayout.EndScrollView();

            GUILayout.BeginHorizontal();
            _chatInput = GUILayout.TextField(_chatInput ?? "");
            GUI.enabled = !string.IsNullOrWhiteSpace(_chatInput);
            if (GUILayout.Button("发送", GUILayout.Width(64)))
                StartCoroutine(SendChat());
            GUI.enabled = true;
            GUILayout.EndHorizontal();

            GUILayout.EndArea();
        }

        // -------------------------------------------------- 协程：从路径提交并轮询
        private IEnumerator SubmitFromPath()
        {
            _busy = true;
            _statusText = "提交中…";
            _currentJobId = "";
            _logLines.Clear();

            string body = JsonUtility.ToJson(new FromPathReq
            {
                path = sourceFolder,
                instruction = instruction ?? "",
                preset = preset ?? "",
            });

            using (UnityWebRequest req = new UnityWebRequest(backendBaseUrl + "/api/jobs/from-path", "POST"))
            {
                req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    _statusText = "失败";
                    _logLines.Add("HTTP 错误: " + req.error);
                    if (!string.IsNullOrEmpty(req.downloadHandler.text))
                        _logLines.Add(req.downloadHandler.text);
                    _busy = false;
                    yield break;
                }

                JobIdResp idResp = JsonUtility.FromJson<JobIdResp>(req.downloadHandler.text);
                _currentJobId = idResp != null ? idResp.job_id : "";
                _logLines.Add("已提交 Job: " + _currentJobId);
            }

            string lastStageMsg = "";
            while (!string.IsNullOrEmpty(_currentJobId))
            {
                yield return new WaitForSeconds(0.4f);
                using (UnityWebRequest r = UnityWebRequest.Get(backendBaseUrl + "/api/jobs/" + _currentJobId))
                {
                    yield return r.SendWebRequest();
                    if (r.result != UnityWebRequest.Result.Success)
                    {
                        _logLines.Add("查询失败: " + r.error);
                        continue;
                    }
                    JobStatus st = JsonUtility.FromJson<JobStatus>(r.downloadHandler.text);
                    if (st == null) continue;

                    _statusText = st.status;
                    if (st.config != null && st.config.train != null)
                        _statusText += "  · " + st.config.preset + "/" + st.config.train.backend;

                    if (st.stages != null)
                    {
                        for (int i = 0; i < st.stages.Length; i++)
                        {
                            StageInfo s = st.stages[i];
                            if (s.status == "running")
                            {
                                string line = "[" + s.name + "] " + Mathf.RoundToInt(s.progress * 100f) + "% " + (s.message ?? "");
                                if (line != lastStageMsg)
                                {
                                    _logLines.Add(line);
                                    lastStageMsg = line;
                                }
                                break;
                            }
                        }
                    }

                    if (st.status == "done")
                    {
                        _resultPath = st.result_path ?? "";
                        _logLines.Add("✓ 完成。result: " + _resultPath);
                        break;
                    }
                    if (st.status == "failed" || st.status == "cancelled")
                    {
                        _logLines.Add("× " + st.status + (string.IsNullOrEmpty(st.error) ? "" : ": " + st.error));
                        break;
                    }
                }
            }
            _busy = false;
        }

        // -------------------------------------------------- 协程：Agent 聊天
        private IEnumerator SendChat()
        {
            string text = (_chatInput ?? "").Trim();
            if (string.IsNullOrEmpty(text)) yield break;

            _chat.Add(new ChatMsg { role = "user", content = text });
            _chatInput = "";

            ChatReq reqObj = new ChatReq { messages = _chat.ToArray() };
            string body = JsonUtility.ToJson(reqObj);

            using (UnityWebRequest req = new UnityWebRequest(backendBaseUrl + "/api/chat", "POST"))
            {
                req.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                req.downloadHandler = new DownloadHandlerBuffer();
                req.SetRequestHeader("Content-Type", "application/json");
                yield return req.SendWebRequest();

                if (req.result != UnityWebRequest.Result.Success)
                {
                    _chat.Add(new ChatMsg { role = "assistant", content = "(请求失败: " + req.error + ")" });
                    yield break;
                }
                ChatResp resp = JsonUtility.FromJson<ChatResp>(req.downloadHandler.text);
                if (resp == null || string.IsNullOrEmpty(resp.reply))
                    _chat.Add(new ChatMsg { role = "assistant", content = "(空回复)" });
                else
                {
                    _chat.Add(new ChatMsg { role = "assistant", content = resp.reply });
                    _chatBackend = resp.backend;
                }
            }
        }

#if UNITY_EDITOR
        // ===================================================================
        // ② "训练完直接拉 .ply 进当前场景" —— 仅 Editor 生效。
        // 不修改队友的 agent_tool.py / Agent3DGSAutoImporter:这里只在我自己
        // 的脚本里用反射调用 aras-p 公开的
        //   GaussianSplatting.Editor.GaussianSplatAssetCreator
        // 把 .ply 转成 GaussianSplatAsset,再加一个 GameObject + GaussianSplatRenderer
        // 进**当前活动场景**(不新建场景、不替换场景、不动队友的 SceneBuilder)。
        // 标准 player 构建里这整块被剥离;面板里改为只显示结果路径。
        // ===================================================================

        private IEnumerator LoadResultIntoScene()
        {
            if (string.IsNullOrEmpty(_resultPath) && string.IsNullOrEmpty(_currentJobId))
            {
                _logLines.Add("× 没有可用结果。");
                yield break;
            }
            _loading = true;

            // 1) 确保 .ply 在 Unity 工程的 Assets/ 下(asset creator 要求 input/output
            //    都在工程内)。后端本机的就直接 copy;否则走 /api/jobs/{id}/result 下载。
            string jobLabel = string.IsNullOrEmpty(_currentJobId) ? "result" : _currentJobId;
            string assetsRel = "Assets/Generated3DGS/jobs/" + jobLabel;
            string assetsAbs = Path.GetFullPath(Path.Combine(Application.dataPath, "..", assetsRel))
                                   .Replace("\\", "/");
            Directory.CreateDirectory(assetsAbs);
            string destPly = (assetsAbs + "/point_cloud.ply");

            bool gotLocal = !string.IsNullOrEmpty(_resultPath) && File.Exists(_resultPath);
            if (gotLocal)
            {
                try
                {
                    if (Path.GetFullPath(_resultPath) != Path.GetFullPath(destPly))
                        File.Copy(_resultPath, destPly, true);
                    _logLines.Add("已复制 .ply 到工程: " + assetsRel + "/point_cloud.ply");
                }
                catch (System.Exception exc)
                {
                    _logLines.Add("× 复制失败: " + exc.Message);
                    _loading = false; yield break;
                }
            }
            else
            {
                _logLines.Add("本机找不到结果,正在从后端下载…");
                using (UnityWebRequest r = UnityWebRequest.Get(backendBaseUrl + "/api/jobs/" + _currentJobId + "/result"))
                {
                    yield return r.SendWebRequest();
                    if (r.result != UnityWebRequest.Result.Success)
                    {
                        _logLines.Add("× 下载失败: " + r.error);
                        _loading = false; yield break;
                    }
                    try { File.WriteAllBytes(destPly, r.downloadHandler.data); }
                    catch (System.Exception exc)
                    {
                        _logLines.Add("× 写入失败: " + exc.Message);
                        _loading = false; yield break;
                    }
                    _logLines.Add("已下载 " + (r.downloadHandler.data.Length / 1024) + " KiB → " + assetsRel);
                }
            }

            // 2) 让 Unity 看到新文件,然后用反射跑 aras-p 的 GaussianSplatAssetCreator
            //    (就是菜单 Tools > Gaussian Splats > Create GaussianSplatAsset 干的事)。
            AssetDatabase.Refresh();
            UnityEngine.Object asset = null;
            try { asset = CreateGaussianSplatAssetEditor(destPly, assetsRel); }
            catch (System.Exception exc) { _logLines.Add("× 转换失败: " + exc.Message); }
            if (asset == null)
            {
                _logLines.Add("× 未生成 GaussianSplatAsset(请等 Package Manager 装完 aras-p 再试)。");
                _loading = false; yield break;
            }

            // 3) 把 GameObject + GaussianSplatRenderer 加到**当前活动场景**(不新建场景)。
            System.Type rendererType = FindTypeAcrossAssemblies("GaussianSplatting.Runtime.GaussianSplatRenderer");
            if (rendererType == null)
            {
                _logLines.Add("× 未找到 GaussianSplatRenderer 类型。");
                _loading = false; yield break;
            }
            GameObject splat = new GameObject("Splat_" + jobLabel);
            Component renderer = splat.AddComponent(rendererType);
            AssignAssetField(renderer, asset);
            // 朝向与队友 SceneBuilder 一致,导入即可显示
            splat.transform.rotation = Quaternion.Euler(-160f, 0f, 180f);
            EditorSceneManager.MarkSceneDirty(SceneManager.GetActiveScene());
            Selection.activeGameObject = splat;
            _logLines.Add("✓ 已加入当前场景: " + splat.name);
            _loading = false;
        }

        // 反射 helpers (Editor only)

        private static UnityEngine.Object CreateGaussianSplatAssetEditor(string plyAbsolutePath, string outputAssetFolder)
        {
            System.Type creatorType = FindTypeAcrossAssemblies("GaussianSplatting.Editor.GaussianSplatAssetCreator");
            if (creatorType == null) return null;
            UnityEngine.Object creator = ScriptableObject.CreateInstance(creatorType);

            SetPrivateField(creatorType, creator, "m_InputFile", plyAbsolutePath);
            SetPrivateField(creatorType, creator, "m_OutputFolder", outputAssetFolder);
            SetPrivateField(creatorType, creator, "m_ImportCameras", false);

            System.Type qualityType = creatorType.GetNestedType("DataQuality", BindingFlags.NonPublic);
            if (qualityType != null)
            {
                object q = System.Enum.Parse(qualityType, "Medium");
                SetPrivateField(creatorType, creator, "m_Quality", q);
            }
            MethodInfo apply = creatorType.GetMethod("ApplyQualityLevel", BindingFlags.Instance | BindingFlags.NonPublic);
            if (apply != null) apply.Invoke(creator, null);

            MethodInfo createAsset = creatorType.GetMethod("CreateAsset", BindingFlags.Instance | BindingFlags.NonPublic);
            if (createAsset == null) return null;
            createAsset.Invoke(creator, null);

            string[] guids = AssetDatabase.FindAssets("t:ScriptableObject", new[] { outputAssetFolder });
            foreach (string g in guids)
            {
                string p = AssetDatabase.GUIDToAssetPath(g);
                UnityEngine.Object o = AssetDatabase.LoadAssetAtPath<UnityEngine.Object>(p);
                if (o != null && o.GetType().FullName == "GaussianSplatting.Runtime.GaussianSplatAsset")
                    return o;
            }
            return null;
        }

        private static System.Type FindTypeAcrossAssemblies(string fullName)
        {
            foreach (var asm in System.AppDomain.CurrentDomain.GetAssemblies())
            {
                System.Type t = asm.GetType(fullName);
                if (t != null) return t;
            }
            return null;
        }

        private static void SetPrivateField(System.Type type, object target, string name, object value)
        {
            FieldInfo f = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic);
            if (f == null) throw new System.MissingFieldException(type.FullName, name);
            f.SetValue(target, value);
        }

        private static void AssignAssetField(Component renderer, UnityEngine.Object asset)
        {
            SerializedObject so = new SerializedObject(renderer);
            SerializedProperty it = so.GetIterator();
            bool enterChildren = true;
            while (it.NextVisible(enterChildren))
            {
                enterChildren = false;
                if (it.propertyType == SerializedPropertyType.ObjectReference &&
                    it.displayName.ToLowerInvariant().Contains("asset"))
                {
                    it.objectReferenceValue = asset;
                    so.ApplyModifiedProperties();
                    return;
                }
            }
            Debug.LogWarning("Agent3DGSStudioUI: 未能找到 asset 字段,请手动把生成的 GaussianSplatAsset 拖到 Renderer 上。");
        }
#endif
    }
}
