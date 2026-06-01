"""Tests for the pipeline, agent, and API — all run in mock mode, no GPU, no network."""
import time

from app.agent.planner import MockPlanner
from app.config import Settings
from app.models import PipelineConfig, StageStatus, STAGE_ORDER, Job
from app.pipeline._ply import is_gaussian_ply, vertex_count, write_gaussian_ply
from app.pipeline.convert import _decimate
from app.pipeline.runner import PipelineRunner


# --- config / presets -------------------------------------------------------

def test_presets_expand():
    assert PipelineConfig.from_preset("preview").train.iterations == 7000
    assert PipelineConfig.from_preset("balanced").train.iterations == 30000
    assert PipelineConfig.from_preset("high").max_image_edge is None


# --- ply helpers ------------------------------------------------------------

def test_write_and_validate_gaussian_ply(tmp_path):
    p = tmp_path / "m.ply"
    n = write_gaussian_ply(p, num_points=500, sh_degree=3)
    assert n == 500
    assert is_gaussian_ply(p)
    assert vertex_count(p) == 500


def test_non_gaussian_ply_rejected(tmp_path):
    p = tmp_path / "plain.ply"
    p.write_text("ply\nformat ascii 1.0\nelement vertex 1\n"
                 "property float x\nproperty float y\nproperty float z\nend_header\n0 0 0\n")
    assert not is_gaussian_ply(p)


def test_decimate_caps_splats(tmp_path):
    src = tmp_path / "big.ply"
    write_gaussian_ply(src, num_points=2000, sh_degree=1)
    dst = tmp_path / "small.ply"
    kept = _decimate(src, dst, max_splats=300)
    assert kept == 300
    assert vertex_count(dst) == 300
    assert is_gaussian_ply(dst)


# --- mock planner -----------------------------------------------------------

def test_mock_planner_keyword_routing():
    p = MockPlanner()
    assert p.plan("just a quick preview").preset == "preview"
    assert p.plan("I want the highest quality possible").preset == "high"
    assert p.plan("make it anti-aliased, no shimmer").train.backend == "mip"
    assert p.plan("I need clean surfaces / a mesh").train.backend == "2dgs"
    assert p.plan("relight the scene").train.backend == "relight"
    assert p.plan("must run in VR, keep it light").convert.max_splats == 1_000_000
    assert p.plan("").train.backend == "vanilla"  # default


# --- full pipeline (mock) ---------------------------------------------------

def _make_job(tmp_path, n_images=4, preset="preview"):
    job = Job(instruction="reconstruct", image_count=n_images)
    job.config = PipelineConfig.from_preset(preset)
    jd = tmp_path / "job"
    (jd / "input").mkdir(parents=True)
    for i in range(n_images):
        (jd / "input" / f"img{i}.jpg").write_bytes(b"not-a-real-jpeg")
    return job, jd


def test_pipeline_runs_end_to_end(tmp_path):
    job, jd = _make_job(tmp_path)
    events = []
    runner = PipelineRunner(Settings(mock=True, mock_delay=0.0, data_dir=tmp_path / "d"))
    result = runner.run(job, jd, events.append, lambda: False)

    assert result == jd / "result" / "model.ply"
    assert result.exists()
    assert is_gaussian_ply(result)
    assert (jd / "result" / "manifest.json").exists()
    assert [s.name for s in job.stages] == STAGE_ORDER
    assert all(s.status == StageStatus.done for s in job.stages)
    assert any(e.type == "stage_finished" for e in events)


def test_pipeline_cancellation(tmp_path):
    job, jd = _make_job(tmp_path)
    runner = PipelineRunner(Settings(mock=True, mock_delay=0.0, data_dir=tmp_path / "d"))
    from app.pipeline.stages import CancelledError
    try:
        runner.run(job, jd, lambda e: None, lambda: True)  # cancelled from the start
        assert False, "expected CancelledError"
    except CancelledError:
        pass


# --- API (TestClient, drives the async worker) ------------------------------

def test_api_health_and_job_flow():
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["mock_pipeline"] is True

    files = [("images", ("a.jpg", b"x" * 32, "image/jpeg")),
             ("images", ("b.jpg", b"y" * 32, "image/jpeg"))]
    r = client.post("/api/jobs", files=files,
                    data={"instruction": "quick preview, anti-aliased"})
    assert r.status_code == 200
    jid = r.json()["job_id"]

    status = None
    for _ in range(200):
        status = client.get(f"/api/jobs/{jid}").json()
        if status["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert status and status["status"] == "done", status
    # mock planner routed "preview" + "anti-aliased"
    assert status["config"]["preset"] == "preview"
    assert status["config"]["train"]["backend"] == "mip"

    res = client.get(f"/api/jobs/{jid}/result")
    assert res.status_code == 200
    assert res.content[:3] == b"ply"


# --- new endpoints: /api/jobs/from-path and /api/chat ----------------------

def test_api_jobs_from_path(tmp_path):
    """Unity-side workflow: hand the backend a server-side folder of images."""
    from fastapi.testclient import TestClient
    from app.main import app

    folder = tmp_path / "images"
    folder.mkdir()
    for i in range(3):
        (folder / f"img{i}.jpg").write_bytes(b"x" * 64)
    # also drop a non-image to ensure it's ignored
    (folder / "notes.txt").write_text("ignore me")

    client = TestClient(app)
    r = client.post("/api/jobs/from-path",
                    json={"path": str(folder),
                          "instruction": "anti-aliased preview",
                          "preset": "preview"})
    assert r.status_code == 200, r.text
    jid = r.json()["job_id"]

    status = None
    for _ in range(200):
        status = client.get(f"/api/jobs/{jid}").json()
        if status["status"] in ("done", "failed", "cancelled"):
            break
        time.sleep(0.05)
    assert status and status["status"] == "done", status
    assert status["image_count"] == 3
    assert status["config"]["train"]["backend"] == "mip"   # routed by mock planner


def test_api_jobs_from_path_validation():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    r = client.post("/api/jobs/from-path", json={"path": "/nope/does/not/exist"})
    assert r.status_code == 400
    assert "not a directory" in r.text


def test_api_chat_mock_replies():
    """Chat with no API key uses the rule-based mock; keywords route to canned replies."""
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)

    r = client.post("/api/chat",
                    json={"messages": [{"role": "user", "content": "我想要抗锯齿"}]})
    assert r.status_code == 200
    body = r.json()
    assert body["backend"] == "mock"
    assert "mip" in body["reply"].lower()

    r2 = client.post("/api/chat",
                     json={"messages": [{"role": "user", "content": "你好"}]})
    assert r2.status_code == 200 and r2.json()["reply"]


def test_api_chat_rejects_empty_or_assistant_last():
    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    assert client.post("/api/chat", json={"messages": []}).status_code == 400
    bad = client.post("/api/chat",
                      json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert bad.status_code == 400
