/* 3DGS-Agent 控制台逻辑。与 FastAPI 后端通信（进度走 SSE）。 */
"use strict";

// API 基址：被后端托管时（任意端口）用同源（""）。
// 仅独立静态服务器（python -m http.server 5173）或 file:// 才显式指向后端。
const API = (location.port === "5173" || location.protocol === "file:")
  ? "http://localhost:8000" : "";

// 阶段 key（与后端一致，勿改）→ 中文显示名
const STAGES = [
  ["preprocess", "预处理图像"],
  ["colmap", "COLMAP · 运动恢复结构 (SfM)"],
  ["train", "训练 3D 高斯"],
  ["convert", "转换 / 校验 .ply"],
  ["package", "打包交付物"],
];

// 任务状态 → 中文
const STATUS_LABEL = {
  queued: "排队中", planning: "规划中", running: "运行中",
  done: "完成", failed: "失败", cancelled: "已取消",
};
const statusText = (s) => STATUS_LABEL[s] || s;

const $ = (id) => document.getElementById(id);
let selectedFiles = [];
let es = null;            // 当前 EventSource
let currentJob = null;

/* ----------------------------- 健康状态 ----------------------------- */
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
  } catch {
    el.innerHTML = "";
    el.append(badge("后端离线", "badge-err"));
  }
}
function badge(text, cls = "badge-muted") {
  const s = document.createElement("span");
  s.className = `badge ${cls}`;
  s.textContent = text;
  return s;
}

/* --------------------------- 选择图片 ----------------------------- */
const dz = $("dropzone");
const fileInput = $("file-input");
dz.addEventListener("click", () => fileInput.click());
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") fileInput.click(); });
fileInput.addEventListener("change", () => addFiles(fileInput.files));
["dragover", "dragenter"].forEach((t) =>
  dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
["dragleave", "drop"].forEach((t) =>
  dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
dz.addEventListener("drop", (e) => addFiles(e.dataTransfer.files));

function addFiles(fileList) {
  for (const f of fileList) if (f.type.startsWith("image/")) selectedFiles.push(f);
  renderThumbs();
}
function renderThumbs() {
  const box = $("thumbs");
  box.innerHTML = "";
  selectedFiles.slice(0, 12).forEach((f) => {
    const img = document.createElement("img");
    img.src = URL.createObjectURL(f);
    img.onload = () => URL.revokeObjectURL(img.src);
    box.append(img);
  });
  if (selectedFiles.length) {
    const c = document.createElement("span");
    c.className = "count";
    c.textContent = `${selectedFiles.length} 张图片`;
    box.append(c);
  }
}

/* ------------------------------ 提交 ----------------------------------- */
$("submit").addEventListener("click", submitJob);
async function submitJob() {
  const err = $("compose-error");
  err.hidden = true;
  if (!selectedFiles.length) {
    err.textContent = "请至少添加一张图片。";
    err.hidden = false;
    return;
  }
  const btn = $("submit");
  btn.disabled = true; btn.textContent = "上传中…";
  try {
    const fd = new FormData();
    selectedFiles.forEach((f) => fd.append("images", f, f.name));
    fd.append("instruction", $("instruction").value.trim());
    if ($("preset").value) fd.append("preset", $("preset").value);
    const res = await fetch(`${API}/api/jobs`, { method: "POST", body: fd });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const { job_id } = await res.json();
    openJob(job_id);
    selectedFiles = []; renderThumbs();
  } catch (e) {
    err.textContent = `无法启动任务：${e.message}`;
    err.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "生成场景";
  }
}

/* ------------------------------ 任务视图 --------------------------------- */
$("new-job").addEventListener("click", () => {
  if (es) es.close();
  $("job").hidden = true;
  $("compose").scrollIntoView();
});
$("cancel").addEventListener("click", async () => {
  if (currentJob) await fetch(`${API}/api/jobs/${currentJob}/cancel`, { method: "POST" });
});

function renderStageList() {
  const ol = $("stages");
  ol.innerHTML = "";
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
  const li = $(`st-${key}`);
  if (!li) return;
  if (status) li.className = `stage ${status === "done" ? "done"
    : status === "running" ? "running" : status === "failed" ? "failed" : ""}`;
  if (pct != null) {
    li.querySelector(".bar > i").style.width = `${Math.round(pct * 100)}%`;
    li.querySelector(".pct").textContent = `${Math.round(pct * 100)}%`;
  }
  if (message != null) li.querySelector(".msg").textContent = message;
}

function setStatus(status) {
  const b = $("job-status");
  b.textContent = statusText(status);
  b.className = "badge " + ({ running: "badge-run", planning: "badge-run",
    done: "badge-ok", failed: "badge-err", cancelled: "badge-err" }[status] || "badge-muted");
  $("cancel").hidden = !(status === "running" || status === "planning");
}

function showPlan(config, planner) {
  if (!config) return;
  $("plan").hidden = false;
  const c = config;
  $("plan-detail").textContent =
    `预设=${c.preset} · 后端=${c.train.backend} · 迭代=${c.train.iterations}`
    + (c.convert.max_splats ? ` · 上限=${c.convert.max_splats}` : "")
    + (planner ? `   (${planner})` : "")
    + (c.notes ? `\n${c.notes}` : "");
}

function logLine(line) {
  const log = $("log");
  log.textContent += line + "\n";
  log.scrollTop = log.scrollHeight;
}

const pkgMetrics = {};

async function openJob(id) {
  currentJob = id;
  if (es) es.close();
  $("job").hidden = false;
  $("job-id").textContent = id;
  $("result").hidden = true;
  $("plan").hidden = true;
  $("log").textContent = "";
  renderStageList();
  setStatus("queued");
  $("job").scrollIntoView({ behavior: "smooth" });

  // 拉取当前状态（兼容重连 / 已完成的任务）
  try {
    const job = await (await fetch(`${API}/api/jobs/${id}`)).json();
    applyJobState(job);
  } catch { /* 忽略 */ }

  es = new EventSource(`${API}/api/jobs/${id}/events`);
  es.onmessage = (e) => handleEvent(JSON.parse(e.data));
  es.onerror = () => { /* 浏览器自动重连；最终事件会关闭它 */ };
}

function applyJobState(job) {
  setStatus(job.status);
  if (job.config) showPlan(job.config, null);
  (job.stages || []).forEach((s) =>
    setStage(s.name, { status: s.status, pct: s.progress, message: s.message }));
  if (job.status === "done") showResult(job);
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
      if (d.status === "done") fetch(`${API}/api/jobs/${ev.job_id}`).then(r => r.json()).then(showResult);
      if (es) es.close();
      loadRecent();
      break;
    case "job_failed":
      setStatus("failed"); logLine(`错误：${d.error}`); if (es) es.close(); loadRecent();
      break;
  }
}

function showResult(job) {
  $("result").hidden = false;
  $("download").href = `${API}/api/jobs/${job.id}/result`;
  const parts = [];
  if (pkgMetrics.splats) parts.push(`${pkgMetrics.splats.toLocaleString()} 个高斯点`);
  if (pkgMetrics.bytes) parts.push(`${(pkgMetrics.bytes / 1024).toFixed(0)} KiB`);
  if (job.config) parts.push(`${job.config.preset}/${job.config.train.backend}`);
  $("result-stats").textContent = parts.join(" · ");
}

/* ------------------------------ 最近任务 ----------------------------- */
async function loadRecent() {
  try {
    const jobs = await (await fetch(`${API}/api/jobs`)).json();
    const ul = $("recent");
    ul.innerHTML = "";
    if (!jobs.length) { ul.innerHTML = '<li class="empty">暂无任务。</li>'; return; }
    jobs.slice(0, 8).forEach((j) => {
      const li = document.createElement("li");
      li.innerHTML =
        `<span class="rid">${j.id}</span>`
        + `<span class="badge ${statusClass(j.status)}">${statusText(j.status)}</span>`
        + `<span class="rins">${escapeHtml(j.instruction || "（无指令）")}</span>`;
      const btn = document.createElement("button");
      btn.textContent = "打开";
      btn.onclick = () => openJob(j.id);
      li.append(btn);
      ul.append(li);
    });
  } catch { /* 离线 */ }
}
const statusClass = (s) => ({ done: "badge-ok", running: "badge-run", planning: "badge-run",
  failed: "badge-err", cancelled: "badge-err" }[s] || "badge-muted");
const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------ 启动 ------------------------------------- */
loadHealth();
loadRecent();
