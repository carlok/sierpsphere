"""
Metal-accelerated G-invariant SDF evaluator for macOS (Apple Silicon).
Uses PyTorch MPS for GPU evaluation; falls back to CPU if unavailable.

Mathematical foundation: _next/foundation.tex
  - Primitive SDFs:        §2.2 (eqs. 3–5)
  - Orbit symmetrisation:  §2.3 (eq. 2, Proposition 1)
  - Fundamental domain:    §1.3 (eq. 1)
  - Smooth booleans:       §2.4 (eqs. 6–7)
"""
from __future__ import annotations

import math
from itertools import product as iproduct

import numpy as np
import torch
import trimesh
from skimage.measure import marching_cubes

# ── Device ────────────────────────────────────────────────────────────────────

if torch.backends.mps.is_available():
    DEVICE = torch.device("mps")
elif torch.cuda.is_available():
    DEVICE = torch.device("cuda")
else:
    DEVICE = torch.device("cpu")

# ── Smooth Boolean ops ────────────────────────────────────────────────────────

def _smin(a: torch.Tensor, b: torch.Tensor, k: float) -> torch.Tensor:
    """Smooth union (foundation.tex eq. 6)."""
    if k <= 0:
        return torch.minimum(a, b)
    h = torch.clamp(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return torch.lerp(b, a, h) - k * h * (1.0 - h)


def _smax(a: torch.Tensor, b: torch.Tensor, k: float) -> torch.Tensor:
    """Smooth intersection / subtraction (foundation.tex eq. 7)."""
    if k <= 0:
        return torch.maximum(a, b)
    h = torch.clamp(0.5 - 0.5 * (b - a) / k, 0.0, 1.0)
    return torch.lerp(b, a, h) + k * h * (1.0 - h)


# ── Primitive SDFs ─────────────────────────────────────────────────────────────

def _sd_sphere(pts: torch.Tensor, center: torch.Tensor, radius: float) -> torch.Tensor:
    return torch.norm(pts - center, dim=1) - radius


def _sd_box(pts: torch.Tensor, center: torch.Tensor, radius: float) -> torch.Tensor:
    """Cube SDF, Oh-invariant. `radius` = half-extent."""
    q = torch.abs(pts - center) - radius
    return (torch.clamp(q, min=0.0).norm(dim=1)
            + torch.clamp(torch.amax(q, dim=1), max=0.0))


def _sd_tetrahedron(pts: torch.Tensor, center: torch.Tensor, radius: float) -> torch.Tensor:
    """Td-invariant SDF. foundation.tex eq. 3 (Quilez)."""
    p = pts - center
    x, y, z = p[:, 0], p[:, 1], p[:, 2]
    md = torch.maximum(torch.maximum(-x - y - z, x + y - z),
                       torch.maximum(-x + y + z,  x - y + z))
    return (md - radius) / math.sqrt(3.0)


def _sd_icosahedron(pts: torch.Tensor, center: torch.Tensor, radius: float) -> torch.Tensor:
    """
    Ih-invariant SDF via 20 dodecahedral face normals. foundation.tex eq. 5.
    All 20 normals have magnitude √3. `radius` = inradius.
    """
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    s3  = math.sqrt(3.0)
    p   = pts - center
    d   = torch.full((p.shape[0],), -1e9, device=p.device, dtype=p.dtype)

    # 8 normals: (±1, ±1, ±1)/√3
    for sx, sy, sz in iproduct((-1, 1), (-1, 1), (-1, 1)):
        n = torch.tensor([sx, sy, sz], dtype=p.dtype, device=p.device) / s3
        d = torch.maximum(d, p @ n)

    # 12 normals: cyclic permutations of (0, ±φ, ±1/φ)/√3
    for i0, i1, i2 in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        for s1, s2 in iproduct((-1, 1), (-1, 1)):
            raw = [0.0, s1 * phi, s2 / phi]
            n = torch.tensor(
                [raw[i0], raw[i1], raw[i2]], dtype=p.dtype, device=p.device
            ) / s3
            d = torch.maximum(d, p @ n)

    return d - radius


_PRIM_FNS: dict = {
    "tetrahedron": _sd_tetrahedron,
    "cube":        _sd_box,
    "icosahedron": _sd_icosahedron,
    "sphere":      _sd_sphere,
}

# ── Group matrix generation ────────────────────────────────────────────────────

def _rot_mat(axis, angle: float) -> np.ndarray:
    ax = np.asarray(axis, float); ax /= np.linalg.norm(ax)
    c, s = math.cos(angle), math.sin(angle); t = 1.0 - c
    x, y, z = ax
    return np.array([
        [t*x*x + c,   t*x*y - s*z, t*x*z + s*y],
        [t*x*y + s*z, t*y*y + c,   t*y*z - s*x],
        [t*x*z - s*y, t*y*z + s*x, t*z*z + c  ],
    ])


def _reflect_mat(normal) -> np.ndarray:
    n = np.asarray(normal, float); n /= np.linalg.norm(n)
    return np.eye(3) - 2.0 * np.outer(n, n)


def _generate_group(generators: list[np.ndarray], expected_order: int) -> np.ndarray:
    """Close generators under matrix multiplication. Returns (|G|,3,3) float32."""
    def key(m): return tuple(np.round(m, 9).flatten())
    group = [np.eye(3)]
    seen  = {key(np.eye(3))}
    queue = list(generators)
    while queue:
        g = queue.pop(0)
        k = key(g)
        if k in seen:
            continue
        seen.add(k); group.append(g)
        for h in list(group):
            for prod in (g @ h, h @ g):
                pk = key(prod)
                if pk not in seen:
                    queue.append(prod)
    if len(group) != expected_order:
        raise RuntimeError(
            f"Group generation: {len(group)} elements, expected {expected_order}"
        )
    return np.stack(group).astype(np.float32)


_PHI = (1.0 + math.sqrt(5.0)) / 2.0
_TAU = 2.0 * math.pi

# Precomputed at import — one-time cost: Td<1ms, Oh<5ms, Ih~30ms
_GROUP_MATS_NP: dict[str, np.ndarray] = {
    "tetrahedral": _generate_group([
        _rot_mat([1, 1, 1], _TAU / 3),  # C3 — vertex axis
        _rot_mat([1, 0, 0], _TAU / 2),  # C2(x): (x,y,z)→(x,-y,-z), generates T
        _reflect_mat([1, -1, 0]),         # σ_d: (x,y,z)→(y,x,z), coset Td\T
    ], expected_order=24),

    "octahedral": _generate_group([
        _rot_mat([0, 0, 1], _TAU / 4),  # C4 — face axis
        _rot_mat([1, 1, 1], _TAU / 3),  # C3 — vertex axis
        -np.eye(3),                       # inversion
    ], expected_order=48),

    "icosahedral": _generate_group([
        _rot_mat(np.array([0, 1, _PHI]) / math.sqrt(1 + _PHI**2), _TAU / 5),  # C5
        _rot_mat([1, 1, 1], _TAU / 3),                                          # C3
        -np.eye(3),                                                              # inversion
    ], expected_order=120),
}

_GROUP_MATS_TORCH: dict[str, torch.Tensor] = {}  # lazily moved to DEVICE


def _get_group_mats(group: str) -> torch.Tensor:
    if group not in _GROUP_MATS_TORCH:
        _GROUP_MATS_TORCH[group] = torch.tensor(
            _GROUP_MATS_NP[group], dtype=torch.float32, device=DEVICE
        )
    return _GROUP_MATS_TORCH[group]


# ── Fundamental domain ─────────────────────────────────────────────────────────

_FD_CORNERS: dict[str, list[np.ndarray]] = {
    "tetrahedral": [
        np.array([1.0, 1.0, 1.0]) / math.sqrt(3),  # C3 vertex axis
        np.array([1.0, 1.0, 0.0]) / math.sqrt(2),  # C2 edge-midpoint axis
        np.array([1.0, 0.0, 0.0]),                  # face-normal axis
    ],
    "octahedral": [
        np.array([1.0, 1.0, 1.0]) / math.sqrt(3),
        np.array([1.0, 1.0, 0.0]) / math.sqrt(2),
        np.array([1.0, 0.0, 0.0]),
    ],
    "icosahedral": [
        np.array([1.0, 1.0, 1.0]) / math.sqrt(3),
        np.array([_PHI, 1.0, 0.0]) / math.sqrt(_PHI**2 + 1.0),
        np.array([1.0, 0.0, 0.0]),
    ],
}

SEED_TO_GROUP: dict[str, str] = {
    "tetrahedron": "tetrahedral",
    "cube":        "octahedral",
    "icosahedron": "icosahedral",
}


def fd_point(group: str, u: float, v: float) -> np.ndarray:
    """
    Barycentric point in FD(G) on S². (u,v)∈[0,1]², u+v≤1 (folded if not).
    Returns a unit vector. foundation.tex eq. (1).
    """
    u, v = float(u), float(v)
    if u + v > 1.0:
        u, v = 1.0 - u, 1.0 - v
    c0, c1, c2 = _FD_CORNERS[group]
    p = (1.0 - u - v) * c0 + u * c1 + v * c2
    norm = np.linalg.norm(p)
    return p / norm if norm > 1e-9 else c0.copy()


# ── Orbit symmetrisation ───────────────────────────────────────────────────────

def symmetrize_g(
    pts: torch.Tensor,
    prim_fn,
    center: torch.Tensor,
    radius: float,
    group: str,
) -> torch.Tensor:
    """
    Sym_G(P, φ)(x) = min_{g∈G} P(g·x − φ)

    G-invariant by Proposition 1 (foundation.tex §2.3).
    Orbit size = |G| for generic interior φ: 24 / 48 / 120.
    Since G is closed under inversion, min over g·x = min over g⁻¹·x.
    """
    mats = _get_group_mats(group)                          # (|G|, 3, 3)
    transformed = torch.einsum("gij,nj->gni", mats, pts)  # (|G|, N, 3)
    evals = torch.stack([
        prim_fn(transformed[g], center, radius)
        for g in range(mats.shape[0])
    ])                                                     # (|G|, N)
    return evals.min(dim=0).values                         # (N,)


# ── Grammar evaluator ──────────────────────────────────────────────────────────

def evaluate_grammar_metal(
    grammar: dict, resolution: int, bounds: float
) -> np.ndarray:
    """
    Evaluate a G-grammar SDF on an N³ grid on GPU.
    Returns float32 numpy array (N, N, N).

    Grammar schema:
      seed:       {type: tetrahedron|cube|icosahedron, radius: float}
      iterations: [{operation, primitive, fd_u, fd_v, distance,
                    scale_factor, smooth_radius}]
    symmetry_group is derived from seed.type — not stored in the dict.
    """
    coords = torch.linspace(-bounds, bounds, resolution,
                            device=DEVICE, dtype=torch.float32)
    gx, gy, gz = torch.meshgrid(coords, coords, coords, indexing="ij")
    pts = torch.stack([gx.reshape(-1), gy.reshape(-1), gz.reshape(-1)], dim=1)

    seed      = grammar.get("seed", {})
    seed_type = seed.get("type", "cube")
    seed_rad  = float(seed.get("radius", 1.0))
    group     = SEED_TO_GROUP.get(seed_type, "octahedral")
    origin    = torch.zeros(3, device=DEVICE, dtype=torch.float32)

    # Seed — G-invariant by construction (canonical Platonic primitive)
    sdf = _PRIM_FNS.get(seed_type, _sd_box)(pts, origin, seed_rad)

    for it in grammar.get("iterations", []):
        ptype  = it.get("primitive", "sphere")
        op     = it.get("operation", "subtract")
        k      = float(it.get("smooth_radius", 0.0))
        dist   = float(it.get("distance", 0.7))
        scale  = float(it.get("scale_factor", 0.3))
        fd_u   = float(it.get("fd_u", 0.3))
        fd_v   = float(it.get("fd_v", 0.1))

        # φ = direction in FD(G) × distance
        phi_np = fd_point(group, fd_u, fd_v) * dist
        phi_t  = torch.tensor(phi_np, device=DEVICE, dtype=torch.float32)

        prim_fn = _PRIM_FNS.get(ptype, _sd_sphere)
        child   = symmetrize_g(pts, prim_fn, phi_t, scale, group)

        if op == "subtract":
            sdf = _smax(sdf, -child, k)
        elif op == "add":
            sdf = _smin(sdf, child, k)
        elif op == "intersect":
            sdf = _smax(sdf, child, k)

    return sdf.reshape(resolution, resolution, resolution).cpu().float().numpy()


def extract_mesh_metal(
    grammar: dict, resolution: int = 64, bounds: float = 1.8
) -> trimesh.Trimesh | None:
    """Metal-accelerated mesh extraction via marching cubes.
    Always returns at most the dominant component(s): parts with ≥15% of the
    largest component's face count are kept; smaller dangles are dropped.
    This ensures fitness evaluation and GLB export see the same topology.
    """
    grid = evaluate_grammar_metal(grammar, resolution, bounds)
    if grid.max() <= 0 or grid.min() >= 0:
        return None
    spacing = (2 * bounds) / (resolution - 1)
    try:
        verts, faces, _, _ = marching_cubes(grid, level=0.0, spacing=(spacing,) * 3)
    except Exception:
        return None
    verts -= bounds
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    if len(mesh.faces) == 0:
        return None
    parts = mesh.split(only_watertight=False)
    if len(parts) > 1:
        max_faces = max(len(p.faces) for p in parts)
        parts = [p for p in parts if len(p.faces) >= max_faces * 0.15]
        mesh = trimesh.util.concatenate(parts) if len(parts) > 1 else parts[0]
        mesh = trimesh.Trimesh(vertices=mesh.vertices.copy(),
                               faces=mesh.faces.copy(), process=False)
    return mesh if len(mesh.faces) > 0 else None


def device_info() -> str:
    if DEVICE.type == "mps":
        return "Metal (MPS)"
    if DEVICE.type == "cuda":
        return f"CUDA ({torch.cuda.get_device_name(0)})"
    return "CPU (no GPU available)"
