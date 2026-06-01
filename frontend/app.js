/* 3DGS-Agent 浏览器一体化控制台
 *   左列：任务控制（路径 / 指令 / 预设 / 进度）
 *   中列：mkkellogg/gaussian-splats-3d 实时渲染 .ply
 *   右列：Agent 多轮聊天
 */
import * as GaussianSplats3D from "@mkkellogg/gaussian-splats-3d";
import * as THREE from "three";

const API = (location.port === "5173" || location.protocol === "file:")
  ? "http://localhost:8000" : "";

const STAGES = [
  ["preprocess", "预处理图像"],
  ["colmap", "COLMAP · 运动恢复结构 (SfM)"],
  ["train", "训练 3D 高斯"],
  ["convert", "转换 / 校验 .ply"],
  ["package", "打包交付物"],
];
const STATUS_LABEL = {
  queued: "排队中", planning: "规划中", running: "运行中",
  done: "完成", failed: "失败", cancelled: "已取消",
};
const statusText = (s) => STATUS_LABEL[s] || s;
const $ = (id) => document.getElementById(id);

/* ------------------------- gsplat 视口 ------------------------- */
// URL 不带扩展名时（我们的 /api/sample、/api/jobs/{id}/result 都没有），
// 必须显式告诉库这是 PLY，否则会报 "File format not supported"。
const PLY_FORMAT = GaussianSplats3D.SceneFormat?.Ply ?? 0;

let viewer = null;
let viewerStarted = false;
function ensureViewer() {
  if (viewer) return viewer;
  viewer = new GaussianSplats3D.Viewer({
    rootElement: $("viewer-container"),
    // Inria 训练出的场景:Y 轴朝下 + 略带 Z 倾斜,这是 mkkellogg 示例用过的值
    cameraUp: [0, -1, -0.17],
    initialCameraPosition: [0, -1, -5],
    initialCameraLookAt: [0, 0, 0],
    sphericalHarmonicsDegree: 2,
    gpuAcceleratedSort: true,
    sharedMemoryForWorkers: false,   // 避开 COOP/COEP 要求
    selfDrivenMode: true,
    useBuiltInControls: true,
    dynamicScene: false,
  });
  return viewer;
}

/** 装好场景后:计算包围盒,把相机摆到能看见它的距离。Inria 场景的中心和尺度
 *  事先未知,不 frame 一下相机就常常在云里面 / 离得太远 → 全黑。 */
function frameSceneToCamera() {
  try {
    const mesh = viewer.splatMesh;
    if (!mesh) return;
    const geom = mesh.geometry;
    if (!geom) return;
    geom.computeBoundingBox?.();
    const box = geom.boundingBox;
    if (!box || !isFinite(box.min.x) || !isFinite(box.max.x)) return;
    const center = new THREE.Vector3();
    box.getCenter(center);
    const size = new THREE.Vector3();
    box.getSize(size);
    const radius = Math.max(size.length() * 0.5, 1);
    const dist = radius * 2.5;
    // 视线从场景中心后退 dist 看回来 (考虑 cameraUp 是 -Y 系)
    const cam = viewer.camera;
    cam.position.set(center.x, center.y - dist * 0.3, center.z - dist);
    cam.lookAt(center);
    cam.near = Math.max(radius * 0.005, 0.01);
    cam.far = Math.max(radius * 50, 1000);
    cam.updateProjectionMatrix();
    if (viewer.controls?.target) {
      viewer.controls.target.copy(center);
      viewer.controls.update?.();
    }
    console.log("[viewer] framed:", { center: center.toArray(), size: size.toArray(), dist });
  } catch (e) {
    console.warn("frameSceneToCamera failed:", e);
  }
}

function setViewerStatus(text) {
  const el = $("viewer-status");
  if (!text) { el.hidden = true; return; }
  el.hidden = false; el.textContent = text;
}

async function loadScene(url, label) {
  $("viewer-hint").hidden = true;
  setViewerStatus("加载中…");
  const v = ensureViewer();

  // 移除已有 scene（库的 API 名字在不同版本略有差异，尽量兜底）
  try {
    if (typeof v.getSceneCount === "function") {
      for (let i = v.getSceneCount() - 1; i >= 0; i--) v.removeSplatScene?.(i);
    } else if (v.splatMesh?.getScene) {
      while (v.splatMesh.getSceneCount?.() > 0) v.removeSplatScene?.(0);
    }
  } catch { /* 老版本 fallback：dispose 后重建 */
    try { v.dispose?.(); } catch {}
    viewer = null; viewerStarted = false;
    ensureViewer();
  }

  try {
    await viewer.addSplatScene(url, {
      format: PLY_FORMAT,         // ← 关键: 显式告诉库这是 .ply
      showLoadingUI: true,
      splatAlphaRemovalThreshold: 5,
      // progressiveLoad 在某些场景下相机会摆不对,先关掉
      progressiveLoad: false,
    });
    if (!viewerStarted) { viewer.start(); viewerStarted = true; }
    // 装好后把相机框到点云中心;否则相机常在云里面 / 离得太远 → 全黑
    setTimeout(frameSceneToCamera, 50);
    setViewerStatus(label || "");
    setTimeout(() => setViewerStatus(""), 2500);
  } catch (e) {
    console.error(e);
    setViewerStatus("加载失败：" + e.message);
    $("viewer-hint").hidden = false;
  }
}

/* ------------------------- 健康 ------------------------- */
async function loadHealth() {
  const el = $("health");
  try {
    const h = await (await fetch(`${API}/api/health`)).json();
    el.innerHTML = "";
    el.append(badge(h.mock_pipeline ? "mock 流水线" : "真实流水线",
                    h.mock_pipeline ? "badge-muted" : "badge-ok"));
    el.append(badge(h.llm_enabled ? "Claude 智能体" : "mock 智能体",
                    h.llm_enabled ? "badge-ok" : "badge-muted"));
    el.append(badge(`v${h.version}`, "badge-muted"));
    $("chat-backend").textContent = h.llm_enabled ? "claude" : "mock";
    $("chat-backend").className = "badge " + (h.llm_enabled ? "badge-ok" : "badge-muted");
  } catch {
    el.innerHTML = "";
    el.append(badge("后端离线", "badge-err"));
  }
}
function badge(text, cls = "badge-muted") {
  const s = document.createElement("span");
  s.className = `badge ${cls}`; s.textContent = text; return s;
}

/* ------------------------- 提交任务 ------------------------- */
let currentJob = null;
let es = null;
const pkgMetrics = {};

function renderStages() {
  const ol = $("stages"); ol.innerHTML = "";
  STAGES.forEach(([key, label], i) => {
    const li = document.createElement("li");
    li.className = "stage"; li.id = `st-${key}`;
    li.innerHTML = `
      <span class="ix">${i + 1}</span>
      <span class="body">
        <span class="name">${label}</span>
        <span class="bar"><i></i></span>
        <span class="msg"></span>
      </span>
      <span class="pct"></span>`;
    ol.append(li);
  });
}
function setStage(key, { status, pct, message }) {
  const li = $(`st-${key}`); if (!li) return;
  if (status) li.className = `stage ${status === "done" ? "done"
    : status === "running" ? "running" : status === "failed" ? "failed" : ""}`;
  if (pct != null) {
    li.querySelector(".bar > i").style.width = `${Math.round(pct * 100)}%`;
    li.querySelector(".pct").textContent = `${Math.round(pct * 100)}%`;
  }
  if (message != null) li.querySelector(".msg").textContent = message;
}
function setStatus(s) {
  const b = $("job-status");
  b.textContent = statusText(s);
  b.className = "badge " + ({ running: "badge-run", planning: "badge-run",
    done: "badge-ok", failed: "badge-err", cancelled: "badge-err" }[s] || "badge-muted");
  $("cancel").hidden = !(s === "running" || s === "planning");
}
function showPlan(config, planner) {
  if (!config) return;
  $("plan").hidden = false;
  const c = config;
  $("plan-detail").textContent =
    `预设=${c.preset} · 后端=${c.train.backend} · 迭代=${c.train.iterations}`
    + (c.convert.max_splats ? ` · 上限=${c.convert.max_splats}` : "")
    + (planner ? `  (${planner})` : "");
}
function logLine(line) {
  const log = $("log");
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
}

$("submit").addEventListener("click", submitJob);
$("cancel").addEventListener("click", async () => {
  if (currentJob) await fetch(`${API}/api/jobs/${currentJob}/cancel`, { method: "POST" });
});

async function submitJob() {
  const err = $("compose-error"); err.hidden = true;
  const path = $("source-folder").value.trim();
  if (!path) { err.textContent = "请填一个后端可读到的图片文件夹路径。"; err.hidden = false; return; }
  const btn = $("submit"); btn.disabled = true; btn.textContent = "提交中…";
  try {
    const body = {
      path,
      instruction: $("instruction").value.trim(),
      preset: $("preset").value || null,
    };
    const res = await fetch(`${API}/api/jobs/from-path`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const detail = (await res.json().catch(() => ({}))).detail || res.statusText;
      throw new Error(detail);
    }
    const { job_id } = await res.json();
    openJob(job_id);
  } catch (e) {
    err.textContent = `无法启动任务：${e.message}`;
    err.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "生成场景";
  }
}

async function openJob(id) {
  currentJob = id;
  if (es) es.close();
  $("job-head").hidden = false;
  $("job-id").textContent = id;
  $("plan").hidden = true;
  $("log").textContent = "";
  renderStages();
  setStatus("queued");

  try {
    const job = await (await fetch(`${API}/api/jobs/${id}`)).json();
    applyJobState(job);
  } catch { /* ignore */ }

  es = new EventSource(`${API}/api/jobs/${id}/events`);
  es.onmessage = (e) => handleEvent(JSON.parse(e.data));
  es.onerror = () => {};
}

function applyJobState(job) {
  setStatus(job.status);
  if (job.config) showPlan(job.config, null);
  (job.stages || []).forEach((s) =>
    setStage(s.name, { status: s.status, pct: s.progress, message: s.message }));
  if (job.status === "done") onJobDone(job);
  if (job.status === "failed") logLine(`错误：${job.error || "失败"}`);
}

function handleEvent(ev) {
  const d = ev.data || {};
  switch (ev.type) {
    case "job_update": setStatus(d.status); break;
    case "planned": showPlan(d.config, d.planner); break;
    case "stage_started": setStage(ev.stage, { status: "running", pct: 0 }); break;
    case "stage_progress": setStage(ev.stage, { pct: d.pct, message: d.message }); break;
    case "stage_log": if (d.line) logLine(`[${ev.stage}] ${d.line}`); break;
    case "stage_finished":
      setStage(ev.stage, { status: "done", pct: 1 });
      if (ev.stage === "package" && d.metrics) Object.assign(pkgMetrics, d.metrics);
      break;
    case "stage_failed": setStage(ev.stage, { status: "failed" }); logLine(`[${ev.stage}] 错误：${d.error}`); break;
    case "job_finished":
      setStatus(d.status);
      if (d.status === "done")
        fetch(`${API}/api/jobs/${ev.job_id}`).then(r => r.json()).then(onJobDone);
      if (es) es.close();
      break;
    case "job_failed":
      setStatus("failed"); logLine(`错误：${d.error}`); if (es) es.close();
      break;
  }
}

async function onJobDone(job) {
  const splats = pkgMetrics.splats ? ` · ${pkgMetrics.splats.toLocaleString()} splats` : "";
  setViewerStatus("下载结果中…");
  try {
    const url = `${API}/api/jobs/${job.id}/result`;
    await loadScene(url, `Job ${job.id}${splats}`);
  } catch (e) {
    logLine("装载结果失败: " + e.message);
  }
}

/* ------------------------- 加载样本 ------------------------- */
$("load-sample").addEventListener("click", async () => {
  // 不再用 HEAD 预探测 (FastAPI/FileResponse 对 HEAD 处理有坑) —— 直接试 GET,
  // 失败由 loadScene 的 catch 在 viewer-status 上报错。
  await loadScene(`${API}/api/sample`, "样本场景");
});

/* ------------------------- 聊天 ------------------------- */
const chatHistory = [];

function appendChat(role, content) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role === "user" ? "user" : "agent"}`;
  wrap.innerHTML = `<span class="who">${role === "user" ? "你" : "Agent"}</span>
                    <div class="body"></div>`;
  wrap.querySelector(".body").textContent = content;
  $("chat-history").append(wrap);
  $("chat-history").scrollTop = $("chat-history").scrollHeight;
}

$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const txt = $("chat-input").value.trim();
  if (!txt) return;
  $("chat-input").value = "";
  appendChat("user", txt);
  chatHistory.push({ role: "user", content: txt });
  const sendBtn = $("chat-send");
  sendBtn.disabled = true;
  try {
    const r = await fetch(`${API}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages: chatHistory }),
    });
    const body = await r.json();
    const reply = body.reply || "(空回复)";
    appendChat("agent", reply);
    chatHistory.push({ role: "assistant", content: reply });
    if (body.backend) {
      $("chat-backend").textContent = body.backend;
      $("chat-backend").className = "badge " + (body.backend === "claude" ? "badge-ok" : "badge-muted");
    }
  } catch (err) {
    appendChat("agent", "(请求失败: " + err.message + ")");
  } finally {
    sendBtn.disabled = false;
  }
});

/* ------------------------- 启动 ------------------------- */
loadHealth();
renderStages();
ensureViewer();  // 初始化空视口（出现"左键拖…"提示）
