"""
G-invariant SDF engine for the g-sdf-evolver grammar.

Numpy/CPU counterpart to evolver/sdf_metal.py. Used by:
  - engine/server.py  (server-side mesh extraction for gallery)
  - engine tests

Mathematical foundation: _next/foundation.tex
  §2.2 primitive SDFs, §2.3 orbit symmetrisation, §1.3 fundamental domain
"""
from __future__ import annotations

import math
from itertools import product as iproduct

import numpy as np


# ── Primitive SDFs (numpy) ─────────────────────────────────────────────────────

def sdf_sphere(pts: np.ndarray, center: np.ndarray, radius: float) -> np.ndarray:
    return np.linalg.norm(pts - center, axis=-1) - radius


def sdf_box(pts: np.ndarray, center: np.ndarray, radius: float) -> np.ndarray:
    """Cube SDF. `radius` = half-extent."""
    q = np.abs(pts - center) - radius
    return (np.linalg.norm(np.maximum(q, 0), axis=-1)
            + np.minimum(np.max(q, axis=-1), 0))


def sdf_tetrahedron(pts: np.ndarray, center: np.ndarray, radius: float) -> np.ndarray:
    """Td-invariant SDF. foundation.tex eq. 3."""
    p = pts - center
    x, y, z = p[..., 0], p[..., 1], p[..., 2]
    md = np.maximum(np.maximum(-x - y - z, x + y - z),
                    np.maximum(-x + y + z,  x - y + z))
    return (md - radius) / math.sqrt(3.0)


def sdf_icosahedron(pts: np.ndarray, center: np.ndarray, radius: float) -> np.ndarray:
    """Ih-invariant SDF via 20 dodecahedral face normals. foundation.tex eq. 5."""
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    s3  = math.sqrt(3.0)
    p   = pts - center
    d   = np.full(p.shape[:-1], -1e9)

    for sx, sy, sz in iproduct((-1, 1), (-1, 1), (-1, 1)):
        n = np.array([sx, sy, sz], dtype=np.float64) / s3
        d = np.maximum(d, p @ n)

    for i0, i1, i2 in ((0, 1, 2), (1, 2, 0), (2, 0, 1)):
        for s1, s2 in iproduct((-1, 1), (-1, 1)):
            raw = [0.0, s1 * phi, s2 / phi]
            n = np.array([raw[i0], raw[i1], raw[i2]], dtype=np.float64) / s3
            d = np.maximum(d, p @ n)

    return d - radius


SDF_PRIMITIVES: dict = {
    "tetrahedron": sdf_tetrahedron,
    "cube":        sdf_box,
    "icosahedron": sdf_icosahedron,
    "sphere":      sdf_sphere,
}

# ── Smooth Boolean ops ─────────────────────────────────────────────────────────

def smooth_union(d1: np.ndarray, d2: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.minimum(d1, d2)
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0, 1)
    return d2 * (1 - h) + d1 * h - k * h * (1 - h)


def smooth_subtraction(d1: np.ndarray, d2: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.maximum(-d1, d2)
    h = np.clip(0.5 - 0.5 * (d2 + d1) / k, 0, 1)
    return d2 * (1 - h) + (-d1) * h + k * h * (1 - h)


def smooth_intersection(d1: np.ndarray, d2: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.maximum(d1, d2)
    h = np.clip(0.5 - 0.5 * (d2 - d1) / k, 0, 1)
    return d2 * (1 - h) + d1 * h + k * h * (1 - h)


BOOLEAN_OPS: dict = {
    "add":       smooth_union,
    "subtract":  smooth_subtraction,
    "intersect": smooth_intersection,
}

# ── Group matrix generation (numpy) ───────────────────────────────────────────

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
    return np.stack(group)


_PHI = (1.0 + math.sqrt(5.0)) / 2.0
_TAU = 2.0 * math.pi

GROUP_MATRICES: dict[str, np.ndarray] = {
    "tetrahedral": _generate_group([
        _rot_mat([1, 1, 1], _TAU / 3),   # C3 — vertex axis (generates T with C2)
        _rot_mat([1, 0, 0], _TAU / 2),   # C2(x): (x,y,z)→(x,-y,-z), generates T
        _reflect_mat([1, -1, 0]),          # σ_d: (x,y,z)→(y,x,z), coset Td\T
    ], expected_order=24),

    "octahedral": _generate_group([
        _rot_mat([0, 0, 1], _TAU / 4),
        _rot_mat([1, 1, 1], _TAU / 3),
        -np.eye(3),
    ], expected_order=48),

    "icosahedral": _generate_group([
        _rot_mat(np.array([0, 1, _PHI]) / math.sqrt(1 + _PHI**2), _TAU / 5),
        _rot_mat([1, 1, 1], _TAU / 3),
        -np.eye(3),
    ], expected_order=120),
}

# ── Fundamental domain ─────────────────────────────────────────────────────────

_FD_CORNERS: dict[str, list[np.ndarray]] = {
    "tetrahedral": [
        np.array([1.0, 1.0, 1.0]) / math.sqrt(3),
        np.array([1.0, 1.0, 0.0]) / math.sqrt(2),
        np.array([1.0, 0.0, 0.0]),
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
    """Barycentric point in FD(G) on S². foundation.tex eq. (1)."""
    u, v = float(u), float(v)
    if u + v > 1.0:
        u, v = 1.0 - u, 1.0 - v
    c0, c1, c2 = _FD_CORNERS[group]
    p = (1.0 - u - v) * c0 + u * c1 + v * c2
    norm = np.linalg.norm(p)
    return p / norm if norm > 1e-9 else c0.copy()


def symmetrize_g(
    pts: np.ndarray,
    prim_fn,
    center: np.ndarray,
    radius: float,
    group: str,
) -> np.ndarray:
    """
    Sym_G(P, φ)(x) = min_{g∈G} P(g·x − φ). foundation.tex eq. (2).
    pts: (..., 3). Returns (...,).
    """
    mats = GROUP_MATRICES[group]   # (|G|, 3, 3)
    flat = pts.reshape(-1, 3)
    # transformed: (|G|, N, 3) = mats @ flat.T transposed per element
    transformed = np.einsum("gij,nj->gni", mats, flat)
    evals = np.stack([
        prim_fn(transformed[g], center, radius)
        for g in range(len(mats))
    ])  # (|G|, N)
    result = evals.min(axis=0)     # (N,)
    return result.reshape(pts.shape[:-1])


# ── Grammar evaluator ──────────────────────────────────────────────────────────

class SierpSphereEvaluator:
    """
    Evaluates a G-grammar into a callable SDF (numpy/CPU).

    Grammar schema:
      seed:       {type: tetrahedron|cube|icosahedron, radius: float}
      iterations: [{operation, primitive, fd_u, fd_v, distance,
                    scale_factor, smooth_radius}]
    """

    def __init__(self, grammar: dict):
        self.grammar  = grammar
        seed          = grammar.get("seed", {})
        self.seed_type   = seed.get("type", "cube")
        self.seed_radius = float(seed.get("radius", 1.0))
        self.group       = SEED_TO_GROUP.get(self.seed_type, "octahedral")
        self.iterations  = grammar.get("iterations", [])

    def evaluate(self, pts: np.ndarray) -> np.ndarray:
        """pts: (..., 3). Returns (...,) signed distances."""
        origin = np.zeros(3)
        d = SDF_PRIMITIVES.get(self.seed_type, sdf_box)(pts, origin, self.seed_radius)

        for it in self.iterations:
            ptype  = it.get("primitive", "sphere")
            op     = it.get("operation", "subtract")
            k      = float(it.get("smooth_radius", 0.0))
            dist   = float(it.get("distance", 0.7))
            scale  = float(it.get("scale_factor", 0.3))
            fd_u   = float(it.get("fd_u", 0.3))
            fd_v   = float(it.get("fd_v", 0.1))

            phi = fd_point(self.group, fd_u, fd_v) * dist
            prim_fn = SDF_PRIMITIVES.get(ptype, sdf_sphere)
            child   = symmetrize_g(pts, prim_fn, phi, scale, self.group)

            bool_fn = BOOLEAN_OPS.get(op, smooth_subtraction)
            d = bool_fn(child, d, k)

        return d

    def to_raymarcher_json(self) -> dict:
        """Export grammar for the GLSL WebGL raymarcher."""
        return {
            "seed": {
                "type":   self.seed_type,
                "center": [0.0, 0.0, 0.0],
                "radius": self.seed_radius,
            },
            "group":      self.group,
            "fd_corners": {g: [c.tolist() for c in cs]
                           for g, cs in _FD_CORNERS.items()},
            "iterations": self.iterations,
        }


# ── Mesh extraction ────────────────────────────────────────────────────────────

def extract_mesh(
    evaluator: SierpSphereEvaluator,
    resolution: int = 128,
    bounds: float = 1.8,
):
    """Sample SDF on grid, extract isosurface via marching cubes."""
    from skimage.measure import marching_cubes
    import trimesh

    lin = np.linspace(-bounds, bounds, resolution)
    X, Y, Z = np.meshgrid(lin, lin, lin, indexing="ij")
    pts = np.stack([X, Y, Z], axis=-1)

    volume = evaluator.evaluate(pts)
    verts, faces, normals, _ = marching_cubes(
        volume, level=0.0, spacing=(2 * bounds / resolution,) * 3
    )
    verts -= bounds
    mesh = trimesh.Trimesh(vertices=verts, faces=faces,
                           vertex_normals=normals)
    return filter_largest_component(mesh)


def filter_largest_component(mesh):
    import trimesh
    parts = mesh.split(only_watertight=False)
    if len(parts) <= 1:
        return mesh
    largest = max(parts, key=lambda p: len(p.faces))
    return trimesh.Trimesh(
        vertices=largest.vertices.copy(),
        faces=largest.faces.copy(),
        process=False,
    )


def grammar_to_gltf(grammar: dict, output_path: str = "out.glb") -> str:
    ev  = SierpSphereEvaluator(grammar)
    res = grammar.get("render", {}).get("resolution", 128)
    bnd = grammar.get("render", {}).get("bounds", 1.8)
    mesh = extract_mesh(ev, resolution=res, bounds=bnd)
    mesh.export(output_path)
    return output_path
