// Agent3DGS Studio UI — runtime 三联面板:文件夹输入 / 任务进度 / Agent 聊天。
// 把本文件放进 Unity 工程的 Assets/Agent3DGS/Runtime/。运行时 F2 切换显隐。
// 后端接口:POST /api/jobs/from-path、POST /api/chat、GET /api/jobs/{id}。

using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

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
                        _logLines.Add("✓ 完成。result: " + (st.result_path ?? ""));
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
    }
}
