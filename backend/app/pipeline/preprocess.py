"""Stage 1 — preprocess: validate, normalise, and (real mode) downscale images."""
from __future__ import annotations

import shutil
from pathlib import Path

from .stages import Stage, StageContext, StageError, StageResult, register

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}


def _resize_copy(src: Path, dst: Path, max_edge: int) -> bool:
    """Downscale so the longest edge <= max_edge. Returns False if Pillow is absent."""
    try:
        from PIL import Image  # optional dependency
    except Exception:
        return False
    with Image.open(src) as im:
        im = im.convert("RGB")
        w, h = im.size
        if max(w, h) > max_edge:
            scale = max_edge / max(w, h)
            im = im.resize((round(w * scale), round(h * scale)), Image.LANCZOS)
        im.save(dst, quality=95)
    return True


class PreprocessStage(Stage):
    name = "preprocess"

    def _images(self, ctx: StageContext) -> list[Path]:
        return sorted(p for p in ctx.input_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS)

    def _prepare(self, ctx: StageContext, resize: bool) -> StageResult:
        imgs = self._images(ctx)
        out = ctx.work_dir / "images"
        out.mkdir(parents=True, exist_ok=True)
        n = len(imgs)
        if n == 0:
            raise StageError(f"no input images found in {ctx.input_dir}")
        if n == 1:
            ctx.log("WARNING: only 1 image — multi-view 3DGS needs many overlapping "
                    "views; single-image needs a generative model (see docs/03 §3.7).")
        elif n < 20:
            ctx.log(f"WARNING: only {n} images; COLMAP usually wants >= 20 with ~70% overlap.")

        for i, src in enumerate(imgs):
            ctx.check_cancel()
            dst = out / f"{i:04d}{src.suffix.lower()}"
            did = resize and ctx.config.max_image_edge and _resize_copy(src, dst, ctx.config.max_image_edge)
            if not did:
                shutil.copy2(src, dst)
            ctx.progress((i + 1) / n, f"prepared {i + 1}/{n}")
        return StageResult(artifacts={"images_dir": str(out)}, metrics={"image_count": n})

    def run(self, ctx: StageContext) -> StageResult:
        return self._prepare(ctx, resize=True)

    def run_mock(self, ctx: StageContext) -> StageResult:
        # Preprocess needs no GPU, so mock just skips the (optional) resize.
        return self._prepare(ctx, resize=False)


register(PreprocessStage())
