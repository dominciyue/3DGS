/* 3DGS-Agent dashboard logic. Talks to the FastAPI backend (SSE for live progress). */
"use strict";

// API base: same-origin when the backend serves us; else the dev backend.
const API = (location.port === "8000" || location.port === "")
  ? "" : "http://localhost:8000";

const STAGES = [
  ["preprocess", "Preprocess images"],
  ["colmap", "COLMAP · Structure-from-Motion"],
  ["train", "Train 3D Gaussians"],
  ["convert", "Convert / validate .ply"],
  ["package", "Package deliverable"],
];

const $ = (id) => document.getElementById(id);
let selectedFiles = [];
let es = null;            // active EventSource
let currentJob = null;

/* ----------------------------- health ----------------------------------- */
async function loadHealth() {
  const el = $("health");
  try {
    const h = await (await fetch(`${API}/api/health`)).json();
    el.innerHTML = "";
    el.append(badge(h.mock_pipeline ? "mock pipeline" : "real pipeline",
                    h.mock_pipeline ? "badge-muted" : "badge-ok"));
    el.append(badge(h.llm_enabled ? "Claude agent" : "mock agent",
                    h.llm_enabled ? "badge-ok" : "badge-muted"));
    el.append(badge(`v${h.version}`, "badge-muted"));
  } catch {
    el.innerHTML = "";
    el.append(badge("backend offline", "badge-err"));
  }
}
function badge(text, cls = "badge-muted") {
  const s = document.createElement("span");
  s.className = `badge ${cls}`;
  s.textContent = text;
  return s;
}

/* --------------------------- file selection ----------------------------- */
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
    c.textContent = `${selectedFiles.length} image${selectedFiles.length > 1 ? "s" : ""}`;
    box.append(c);
  }
}

/* ------------------------------ submit ----------------------------------- */
$("submit").addEventListener("click", submitJob);
async function submitJob() {
  const err = $("compose-error");
  err.hidden = true;
  if (!selectedFiles.length) {
    err.textContent = "Add at least one image.";
    err.hidden = false;
    return;
  }
  const btn = $("submit");
  btn.disabled = true; btn.textContent = "Uploading…";
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
    err.textContent = `Could not start job: ${e.message}`;
    err.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Generate scene";
  }
}

/* ------------------------------ job view --------------------------------- */
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
  b.textContent = status;
  b.className = "badge " + ({ running: "badge-run", planning: "badge-run",
    done: "badge-ok", failed: "badge-err", cancelled: "badge-err" }[status] || "badge-muted");
  $("cancel").hidden = !(status === "running" || status === "planning");
}

function showPlan(config, planner) {
  if (!config) return;
  $("plan").hidden = false;
  const c = config;
  $("plan-detail").textContent =
    `preset=${c.preset} · backend=${c.train.backend} · iters=${c.train.iterations}`
    + (c.convert.max_splats ? ` · cap=${c.convert.max_splats}` : "")
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

  // Hydrate from current state (covers reconnect / already-finished jobs).
  try {
    const job = await (await fetch(`${API}/api/jobs/${id}`)).json();
    applyJobState(job);
  } catch { /* ignore */ }

  es = new EventSource(`${API}/api/jobs/${id}/events`);
  es.onmessage = (e) => handleEvent(JSON.parse(e.data));
  es.onerror = () => { /* browser auto-reconnects; final event closes it */ };
}

function applyJobState(job) {
  setStatus(job.status);
  if (job.config) showPlan(job.config, null);
  (job.stages || []).forEach((s) =>
    setStage(s.name, { status: s.status, pct: s.progress, message: s.message }));
  if (job.status === "done") showResult(job);
  if (job.status === "failed") logLine(`ERROR: ${job.error || "failed"}`);
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
    case "stage_failed": setStage(ev.stage, { status: "failed" }); logLine(`[${ev.stage}] ERROR: ${d.error}`); break;
    case "job_finished":
      setStatus(d.status);
      if (d.status === "done") fetch(`${API}/api/jobs/${ev.job_id}`).then(r => r.json()).then(showResult);
      if (es) es.close();
      loadRecent();
      break;
    case "job_failed":
      setStatus("failed"); logLine(`ERROR: ${d.error}`); if (es) es.close(); loadRecent();
      break;
  }
}

function showResult(job) {
  $("result").hidden = false;
  $("download").href = `${API}/api/jobs/${job.id}/result`;
  const parts = [];
  if (pkgMetrics.splats) parts.push(`${pkgMetrics.splats.toLocaleString()} splats`);
  if (pkgMetrics.bytes) parts.push(`${(pkgMetrics.bytes / 1024).toFixed(0)} KiB`);
  if (job.config) parts.push(`${job.config.preset}/${job.config.train.backend}`);
  $("result-stats").textContent = parts.join(" · ");
}

/* ------------------------------ recent ----------------------------------- */
async function loadRecent() {
  try {
    const jobs = await (await fetch(`${API}/api/jobs`)).json();
    const ul = $("recent");
    ul.innerHTML = "";
    if (!jobs.length) { ul.innerHTML = '<li class="empty">No jobs yet.</li>'; return; }
    jobs.slice(0, 8).forEach((j) => {
      const li = document.createElement("li");
      li.innerHTML =
        `<span class="rid">${j.id}</span>`
        + `<span class="badge ${statusClass(j.status)}">${j.status}</span>`
        + `<span class="rins">${escapeHtml(j.instruction || "(no instruction)")}</span>`;
      const btn = document.createElement("button");
      btn.textContent = "open";
      btn.onclick = () => openJob(j.id);
      li.append(btn);
      ul.append(li);
    });
  } catch { /* offline */ }
}
const statusClass = (s) => ({ done: "badge-ok", running: "badge-run", planning: "badge-run",
  failed: "badge-err", cancelled: "badge-err" }[s] || "badge-muted");
const escapeHtml = (s) => s.replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/* ------------------------------ boot ------------------------------------- */
loadHealth();
loadRecent();
