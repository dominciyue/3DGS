"""Stage 4 — convert: validate the trained .ply is a Gaussian splat file and prepare
it for the engine (optional splat-count cap for weaker GPUs).

This is the compatibility gate before Unity: the aras-p importer rejects non-Gaussian
.ply files, so we verify the per-Gaussian properties are present here.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from ._ply import is_gaussian_ply, read_ply_header, vertex_count
from .stages import Stage, StageContext, StageError, StageResult, register


def _find_trained_ply(train_dir: Path) -> Path | None:
    """Highest-iteration point_cloud.ply, else any .ply under the train dir."""
    cands = sorted(train_dir.glob("point_cloud/iteration_*/point_cloud.ply"),
                   key=lambda p: int(p.parent.name.split("_")[-1]))
    if cands:
        return cands[-1]
    others = sorted(train_dir.rglob("*.ply"))
    return others[-1] if others else None


def _decimate(src: Path, dst: Path, max_splats: int) -> int:
    """Keep the first ``max_splats`` vertices of a binary-LE Gaussian .ply.

    Defensive: on any unexpected format, fall back to a plain copy.
    """
    count, props, fmt = read_ply_header(src)
    if fmt != "binary_little_endian" or count <= max_splats:
        shutil.copy2(src, dst)
        return count
    record = len(props) * 4  # all 3DGS properties are float32
    raw = src.read_bytes()
    marker = b"end_header\n"
    idx = raw.find(marker)
    if idx == -1:
        shutil.copy2(src, dst)
        return count
    header_end = idx + len(marker)
    header_txt = raw[:header_end].decode("ascii", errors="replace")
    new_header = header_txt.replace(f"element vertex {count}", f"element vertex {max_splats}")
    body = raw[header_end:header_end + record * max_splats]
    dst.write_bytes(new_header.encode("ascii") + body)
    return max_splats


class ConvertStage(Stage):
    name = "convert"

    def _convert(self, ctx: StageContext) -> StageResult:
        src = _find_trained_ply(ctx.input_dir)
        if src is None:
            raise StageError(f"no .ply found under {ctx.input_dir}")
        if not is_gaussian_ply(src):
            raise StageError(
                f"{src.name} is not a Gaussian-Splatting .ply (missing per-Gaussian "
                f"properties). Unity import would fail — check the trainer output."
            )
        ctx.progress(0.4, "validating Gaussian .ply")
        dst = ctx.work_dir / "model.ply"
        max_splats = ctx.config.convert.max_splats
        if max_splats:
            kept = _decimate(src, dst, max_splats)
            ctx.log(f"decimated to {kept} splats (cap {max_splats}) for engine performance")
        else:
            shutil.copy2(src, dst)
        if ctx.config.convert.emit_spz:
            ctx.log("NOTE: SPZ emission requested — wire up an SPZ encoder here "
                    "(aras-p importer also reads SPZ). Keeping .ply for now.")
        ctx.progress(1.0, "converted")
        return StageResult(artifacts={"model": str(dst)},
                           metrics={"splats": vertex_count(dst)})

    def run(self, ctx: StageContext) -> StageResult:
        return self._convert(ctx)

    def run_mock(self, ctx: StageContext) -> StageResult:
        # Identical logic — convert needs no external tools, only the upstream .ply.
        return self._convert(ctx)


register(ConvertStage())
