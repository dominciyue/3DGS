"""Stage 5 — package: finalise the deliverable + write a manifest for reproducibility."""
from __future__ import annotations

import hashlib
import json
import shutil
import time

from ._ply import vertex_count
from .stages import Stage, StageContext, StageError, StageResult, register


def _sha256(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


class PackageStage(Stage):
    name = "package"

    def _package(self, ctx: StageContext) -> StageResult:
        src = ctx.input_dir / "model.ply"      # convert/model.ply
        if not src.exists():
            raise StageError(f"expected converted model at {src}")
        dst = ctx.work_dir / "model.ply"
        shutil.copy2(src, dst)
        ctx.progress(0.6, "writing manifest")

        splats = vertex_count(dst)
        size = dst.stat().st_size
        manifest = {
            "job_id": ctx.job_id,
            "created_at": time.time(),
            "mock": ctx.mock,
            "config": ctx.config.model_dump(),
            "model": {
                "file": "model.ply",
                "splats": splats,
                "bytes": size,
                "sha256": _sha256(dst),
            },
            "unity": {
                "importer": "aras-p/UnityGaussianSplatting",
                "note": "Drag model.ply into a Unity 6 project with the plugin installed; "
                        "see docs/06-unity-integration.md",
            },
        }
        (ctx.work_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))
        ctx.progress(1.0, f"packaged {splats} splats ({size // 1024} KiB)")
        return StageResult(
            artifacts={"model": str(dst), "manifest": str(ctx.work_dir / "manifest.json")},
            metrics={"splats": splats, "bytes": size},
        )

    def run(self, ctx: StageContext) -> StageResult:
        return self._package(ctx)

    def run_mock(self, ctx: StageContext) -> StageResult:
        return self._package(ctx)


register(PackageStage())
