"""
Metal-accelerated SDF grid sampler for macOS (Apple Silicon / Intel + Metal).
Drop-in replacement for extract_mesh() in sdf.py.

Uses PyTorch MPS to evaluate the SDF for all N³ voxels in a single batched
GPU pass. Falls back to CPU tensors if MPS is not available.
"""
from __future__ import annotations

import numpy as np
import torch
import trimesh
from skimage.measure import marching_cubes

# ── Device selection ─────────────────────────────────────────────────────────

if torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
elif torch.cuda.is_available():
    DEVICE = torch.device("cuda")
else:
    DEVICE = torch.device("cpu")


# ── Smooth Boolean ops (scalar and batched) ───────────────────────────────────

def _smin(a: torch.Tensor, b: torch.Tensor, k: float) -> torch.Tensor:
    """Smooth minimum (union)."""
    if k <= 0:
        return torch.minimum(a, b)
    h = torch.clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return torch.lerp(b, a, h) - k * h * (1.0 - h)


def _smax(a: torch.Tensor, b: torch.Tensor, k: float) -> torch.Tensor:
    """Smooth maximum (intersect / subtract)."""
    if k <= 0:
        return torch.maximum(a, b)
    h = torch.clamp(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return torch.lerp(b, a, h) + k * h * (1.0 - h)


# ── Primitive SDFs ────────────────────────────────────────────────────────────

def _sd_sphere(pts: torch.Tensor, center: torch.Tensor, radius: float) -> torch.Tensor:
    return torch.norm(pts - center, dim=1) - radius


def _sd_box(pts: torch.Tensor, center: torch.Tensor, half: float) -> torch.Tensor:
    q = torch.abs(pts - center) - half
    return (torch.clamp(q, min=0.0).norm(dim=1)
            + torch.clamp(torch.amax(q, dim=1), max=0.0))


def _sd_octahedron(pts: torch.Tensor, center: torch.Tensor, s: float) -> torch.Tensor:
    p = torch.abs(pts - center)
    return (p[:, 0] + p[:, 1] + p[:, 2] - s) * 0.57735027


def _sd_primitive(pts: torch.Tensor, ptype: str,
                  center: torch.Tensor, radius: float) -> torch.Tensor:
    if ptype == "cube":
        return _sd_box(pts, center, radius)
    if ptype == "octahedron":
        return _sd_octahedron(pts, center, radius)
    return _sd_sphere(pts, center, radius)


# ── Main evaluator ────────────────────────────────────────────────────────────

def evaluate_grammar_metal(grammar: dict, resolution: int, bounds: float) -> np.ndarray:
    """
    Evaluate the SDF described by `grammar` on an N³ grid entirely on the GPU.
    Returns a float32 numpy array of shape (N, N, N).
    """
    coords = torch.linspace(-bounds, bounds, resolution, device=DEVICE, dtype=torch.float32)
    gx, gy, gz = torch.meshgrid(coords, coords, coords, indexing="ij")
    pts = torch.stack([gx.reshape(-1), gy.reshape(-1), gz.reshape(-1)], dim=1)  # (N³, 3)

    seed = grammar.get("seed", {})
    seed_type   = seed.get("type", "sphere")
    seed_radius = float(seed.get("radius", 1.0))
    seed_center = torch.tensor(seed.get("center", [0.0, 0.0, 0.0]),
                               device=DEVICE, dtype=torch.float32)

    # ── Build flat operation list (same logic as sdf.py SierpSphereEvaluator) ──
    from sdf import SierpSphereEvaluator
    ev = SierpSphereEvaluator(grammar)
    ops = ev.to_raymarcher_json()["operations"]

    # Seed SDF
    sdf = _sd_primitive(pts, seed_type, seed_center, seed_radius)

    # Apply operations
    for op in ops:
        c = torch.tensor(op["center"], device=DEVICE, dtype=torch.float32)
        r = float(op["radius"])
        k = float(op.get("smooth_k", 0.0))
        ptype = op.get("primitive", "sphere")
        child = _sd_primitive(pts, ptype, c, r)

        bop = op.get("bool_op", "subtract")
        if bop == "subtract":
            sdf = _smax(sdf, -child, k)
        elif bop == "add":
            sdf = _smin(sdf, child, k)
        elif bop == "intersect":
            sdf = _smax(sdf, child, k)

    return sdf.reshape(resolution, resolution, resolution).cpu().float().numpy()


def extract_mesh_metal(grammar: dict, resolution: int = 64, bounds: float = 1.8):
    """
    Metal-accelerated drop-in for extract_mesh() in sdf.py.
    Returns a trimesh.Trimesh or None.
    """
    grid = evaluate_grammar_metal(grammar, resolution, bounds)

    if grid.max() <= 0 or grid.min() >= 0:
        return None

    spacing = (2 * bounds) / (resolution - 1)
    try:
        verts, faces, _, _ = marching_cubes(grid, level=0.0, spacing=(spacing,) * 3)
    except Exception:
        return None

    verts -= bounds  # shift to [-bounds, bounds]
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    return mesh if len(mesh.faces) > 0 else None


# ── Info ──────────────────────────────────────────────────────────────────────

def device_info() -> str:
    if DEVICE.type == "mps":
        return "Metal (MPS)"
    if DEVICE.type == "cuda":
        return f"CUDA ({torch.cuda.get_device_name(0)})"
    return "CPU (no GPU available)"
