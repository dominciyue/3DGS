"""Stage 3 — train: optimise the 3D Gaussians (the heavy, GPU step).

Real mode shells out to the configured trainer repo (vanilla Inria, or an extension
backend: mip / 2dgs / relight). Mock mode writes a small, format-correct Gaussian
.ply so the rest of the pipeline — and a Unity import — works end to end.
"""
from __future__ import annotations

import time
from pathlib import Path

from ._ply import write_gaussian_ply
from .stages import Stage, StageContext, StageError, StageResult, register

# Approximate splat counts per preset, for mock metrics. The mock .ply itself is
# capped small (below) to keep the file lightweight.
PRESET_SPLATS = {"preview": 20_000, "balanced": 120_000, "high": 300_000}
MOCK_PLY_CAP = 5_000


class TrainStage(Stage):
    name = "train"

    def _ply_path(self, ctx: StageContext) -> Path:
        it = ctx.config.train.iterations
        return ctx.work_dir / "point_cloud" / f"iteration_{it}" / "point_cloud.ply"

    def run(self, ctx: StageContext) -> StageResult:
        backend = ctx.config.train.backend
        repo = ctx.settings.trainer_repo_for(backend)
        if not repo:
            raise StageError(
                f"trainer backend '{backend}' is not configured. Clone it into "
                f"third_party/ and set its repo dir in backend/.env (see third_party/README.md)."
            )
        if backend != "vanilla":
            ctx.log(f"NOTE: backend '{backend}' uses the vanilla train.py arg form here; "
                    f"adjust args in train.py if this fork differs (see docs/07).")

        source = ctx.input_dir            # job_dir/colmap  (images/ + sparse/)
        out = ctx.work_dir                # job_dir/train
        cmd = [ctx.settings.gs_python, "train.py",
               "-s", source, "-m", out,
               "--iterations", str(ctx.config.train.iterations),
               "-r", str(ctx.config.train.resolution),
               "--sh_degree", str(ctx.config.train.sh_degree)]
        ctx.progress(0.05, f"training ({backend}, {ctx.config.train.iterations} iters)")
        ctx.run_cmd(cmd, cwd=Path(repo))

        ply = self._ply_path(ctx)
        if not ply.exists():
            # Fall back to whatever highest-iteration ply exists.
            cands = sorted((out / "point_cloud").glob("iteration_*/point_cloud.ply"))
            if not cands:
                raise StageError(f"training finished but no point_cloud.ply found under {out}")
            ply = cands[-1]
        return StageResult(artifacts={"ply": str(ply)},
                           metrics={"backend": backend, "iterations": ctx.config.train.iterations})

    def run_mock(self, ctx: StageContext) -> StageResult:
        it = ctx.config.train.iterations
        ply = self._ply_path(ctx)
        target = PRESET_SPLATS.get(ctx.config.preset, 120_000)
        for k in range(1, 11):
            ctx.check_cancel()
            time.sleep(ctx.settings.mock_delay)
            ctx.progress(k / 10, f"mock training {k * 10}%  (~{it} iters, {ctx.config.train.backend})")
        n = write_gaussian_ply(ply, num_points=min(target, MOCK_PLY_CAP),
                               sh_degree=ctx.config.train.sh_degree)
        return StageResult(
            artifacts={"ply": str(ply)},
            metrics={"backend": ctx.config.train.backend, "iterations": it,
                     "splats_written": n, "splats_nominal": target},
        )


register(TrainStage())
