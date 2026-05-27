"""Stage 2 — colmap: Structure-from-Motion (camera poses + sparse point cloud).

Real mode mirrors the Inria ``convert.py`` flow:
    feature_extractor -> matcher -> mapper -> image_undistorter
Mock mode synthesises a ``sparse/0`` model so downstream stages can proceed.
"""
from __future__ import annotations

import time

from .stages import Stage, StageContext, StageError, StageResult, register


class ColmapStage(Stage):
    name = "colmap"

    def run(self, ctx: StageContext) -> StageResult:
        colmap = ctx.settings.colmap_bin
        images = ctx.input_dir                     # preprocess/images
        db = ctx.work_dir / "database.db"
        sparse = ctx.work_dir / "sparse"
        sparse.mkdir(parents=True, exist_ok=True)
        gpu = "1" if ctx.config.colmap.use_gpu else "0"

        ctx.progress(0.05, "feature extraction")
        ctx.run_cmd([colmap, "feature_extractor",
                     "--database_path", db, "--image_path", images,
                     "--ImageReader.single_camera", "1",
                     "--SiftExtraction.use_gpu", gpu])

        ctx.check_cancel()
        ctx.progress(0.4, "feature matching")
        matcher = "exhaustive_matcher" if ctx.config.colmap.matcher == "exhaustive" else "sequential_matcher"
        ctx.run_cmd([colmap, matcher, "--database_path", db, "--SiftMatching.use_gpu", gpu])

        ctx.check_cancel()
        ctx.progress(0.7, "sparse mapping (SfM)")
        ctx.run_cmd([colmap, "mapper",
                     "--database_path", db, "--image_path", images, "--output_path", sparse])

        model0 = sparse / "0"
        if not model0.exists():
            raise StageError("COLMAP produced no reconstruction (sparse/0 missing) — "
                             "try more images with better overlap (see docs/04).")

        ctx.progress(0.9, "undistorting images")
        ctx.run_cmd([colmap, "image_undistorter",
                     "--image_path", images, "--input_path", model0,
                     "--output_path", ctx.work_dir, "--output_type", "COLMAP"])

        return StageResult(
            artifacts={"sparse": str(model0), "images": str(ctx.work_dir / "images")},
            metrics={"matcher": ctx.config.colmap.matcher},
        )

    def run_mock(self, ctx: StageContext) -> StageResult:
        model0 = ctx.work_dir / "sparse" / "0"
        model0.mkdir(parents=True, exist_ok=True)
        for fn in ("cameras.bin", "images.bin", "points3D.bin"):
            (model0 / fn).write_bytes(b"")  # placeholder COLMAP model files
        imgs_out = ctx.work_dir / "images"
        imgs_out.mkdir(parents=True, exist_ok=True)
        n = 0
        for p in sorted(ctx.input_dir.glob("*")):
            (imgs_out / p.name).write_bytes(b"")
            n += 1
        for k in range(1, 6):
            ctx.check_cancel()
            time.sleep(ctx.settings.mock_delay)
            ctx.progress(k / 5, f"mock SfM {k * 20}%")
        return StageResult(
            artifacts={"sparse": str(model0), "images": str(imgs_out)},
            metrics={"registered_images": n, "sparse_points": 1500},
        )


register(ColmapStage())
