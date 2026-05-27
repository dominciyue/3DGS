"""Minimal helpers for the 3D Gaussian Splatting .ply format.

Used to (a) validate that a trained .ply really is a Gaussian splat file before it
reaches Unity, and (b) synthesise a small but *format-correct* .ply in mock mode so
the whole pipeline is end-to-end testable (and the mock result even imports into the
aras-p Unity plugin).

3DGS .ply per-vertex properties (all float32):
    x y z  nx ny nz  f_dc_0..2  f_rest_0..(M-1)  opacity  scale_0..2  rot_0..3
where M = 3 * ((sh_degree+1)^2 - 1).
"""
from __future__ import annotations

import random
import struct
from pathlib import Path

# Properties that must be present for us to treat a .ply as a Gaussian splat.
REQUIRED_PROPS = {"x", "y", "z", "f_dc_0", "opacity", "scale_0", "rot_0", "rot_3"}


def f_rest_count(sh_degree: int) -> int:
    return 3 * ((sh_degree + 1) ** 2 - 1)


def gaussian_property_names(sh_degree: int = 3) -> list[str]:
    props = ["x", "y", "z", "nx", "ny", "nz", "f_dc_0", "f_dc_1", "f_dc_2"]
    props += [f"f_rest_{i}" for i in range(f_rest_count(sh_degree))]
    props += ["opacity", "scale_0", "scale_1", "scale_2", "rot_0", "rot_1", "rot_2", "rot_3"]
    return props


def write_gaussian_ply(path: Path, num_points: int = 2000, sh_degree: int = 3, seed: int = 0,
                       extent: float = 1.0) -> int:
    """Write a small, format-correct binary-little-endian Gaussian .ply. Returns count."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    props = gaussian_property_names(sh_degree)
    header = ["ply", "format binary_little_endian 1.0", f"element vertex {num_points}"]
    header += [f"property float {p}" for p in props]
    header += ["end_header", ""]
    n_floats = len(props)

    with path.open("wb") as fh:
        fh.write("\n".join(header).encode("ascii"))
        for _ in range(num_points):
            x, y, z = (rng.uniform(-extent, extent) for _ in range(3))
            vals = [x, y, z, 0.0, 0.0, 0.0]                 # pos + normals
            vals += [rng.uniform(-1.0, 1.0) for _ in range(3)]  # f_dc (base color)
            vals += [0.0] * f_rest_count(sh_degree)          # higher-order SH
            vals.append(rng.uniform(2.0, 6.0))               # opacity (logit space)
            vals += [rng.uniform(-5.0, -3.0) for _ in range(3)]  # log-scale (small)
            vals += [1.0, 0.0, 0.0, 0.0]                     # rotation quaternion
            assert len(vals) == n_floats
            fh.write(struct.pack("<" + "f" * n_floats, *vals))
    return num_points


def read_ply_header(path: Path) -> tuple[int, list[str], str]:
    """Return (vertex_count, property_names, format) by parsing the ascii header."""
    count, props, fmt = 0, [], "unknown"
    with Path(path).open("rb") as fh:
        for raw in fh:
            line = raw.decode("ascii", errors="replace").strip()
            if line.startswith("format "):
                fmt = line.split()[1]
            elif line.startswith("element vertex"):
                count = int(line.split()[-1])
            elif line.startswith("property"):
                props.append(line.split()[-1])
            elif line == "end_header":
                break
    return count, props, fmt


def is_gaussian_ply(path: Path) -> bool:
    """True if the .ply header carries the per-Gaussian properties Unity needs."""
    try:
        _, props, _ = read_ply_header(path)
    except Exception:
        return False
    return REQUIRED_PROPS.issubset(set(props))


def vertex_count(path: Path) -> int:
    return read_ply_header(path)[0]
