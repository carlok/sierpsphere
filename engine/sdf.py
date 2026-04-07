"""
SDF (Signed Distance Function) engine for SierpSphere grammar.

Evaluates a JSON grammar into a volumetric SDF, then extracts a mesh
via marching cubes and exports GLTF.  Also serves the SDF parameters
as JSON so the WebGL raymarcher can render in real-time.
"""

import json
import math
import numpy as np


# ── Symmetry vertex sets ──────────────────────────────────────────────

def tetrahedral_vertices():
    """Four vertices of a regular tetrahedron inscribed in the unit sphere."""
    return np.array([
        [ 1,  1,  1],
        [ 1, -1, -1],
        [-1,  1, -1],
        [-1, -1,  1],
    ], dtype=np.float64) / math.sqrt(3)


def octahedral_vertices():
    """Six vertices of a regular octahedron inscribed in the unit sphere."""
    return np.array([
        [ 1,  0,  0], [-1,  0,  0],
        [ 0,  1,  0], [ 0, -1,  0],
        [ 0,  0,  1], [ 0,  0, -1],
    ], dtype=np.float64)


def icosahedral_vertices():
    """Twelve vertices of a regular icosahedron inscribed in the unit sphere."""
    phi = (1 + math.sqrt(5)) / 2
    verts = []
    for s1 in (-1, 1):
        for s2 in (-1, 1):
            verts.append([0, s1, s2 * phi])
            verts.append([s1, s2 * phi, 0])
            verts.append([s2 * phi, 0, s1])
    verts = np.array(verts, dtype=np.float64)
    verts /= np.linalg.norm(verts[0])  # normalize to unit sphere
    return verts


SYMMETRY_GROUPS = {
    "tetrahedral":  tetrahedral_vertices,
    "octahedral":   octahedral_vertices,
    "icosahedral":  icosahedral_vertices,
}


# ── SDF primitives ────────────────────────────────────────────────────

def sdf_sphere(p, center, radius):
    """Signed distance to a sphere."""
    return np.linalg.norm(p - center, axis=-1) - radius


def sdf_cube(p, center, half_extent):
    """Signed distance to an axis-aligned box."""
    q = np.abs(p - center) - half_extent
    return (np.linalg.norm(np.maximum(q, 0), axis=-1)
            + np.minimum(np.max(q, axis=-1), 0))


def sdf_octahedron(p, center, radius):
    """Signed distance to a regular octahedron."""
    q = np.abs(p - center)
    return (q[..., 0] + q[..., 1] + q[..., 2] - radius) * (1.0 / math.sqrt(3))


SDF_PRIMITIVES = {
    "sphere":     sdf_sphere,
    "cube":       sdf_cube,
    "octahedron": sdf_octahedron,
}


# ── Smooth Boolean operators ─────────────────────────────────────────

def smooth_union(d1, d2, k):
    if k <= 0:
        return np.minimum(d1, d2)
    h = np.clip(0.5 + 0.5 * (d2 - d1) / k, 0, 1)
    return d2 * (1 - h) + d1 * h - k * h * (1 - h)


def smooth_subtraction(d1, d2, k):
    """Subtract d1 from d2 (d2 is the 'body')."""
    if k <= 0:
        return np.maximum(-d1, d2)
    h = np.clip(0.5 - 0.5 * (d2 + d1) / k, 0, 1)
    return d2 * (1 - h) + (-d1) * h + k * h * (1 - h)


def smooth_intersection(d1, d2, k):
    if k <= 0:
        return np.maximum(d1, d2)
    h = np.clip(0.5 - 0.5 * (d2 - d1) / k, 0, 1)
    return d2 * (1 - h) + d1 * h + k * h * (1 - h)


BOOLEAN_OPS = {
    "add":       smooth_union,
    "subtract":  smooth_subtraction,
    "intersect": smooth_intersection,
}


# ── Grammar evaluation ────────────────────────────────────────────────

class SierpSphereEvaluator:
    """Evaluates a SierpSphere grammar JSON into a callable SDF."""

    def __init__(self, grammar: dict):
        self.grammar = grammar
        seed = grammar["seed"]
        self.seed_center = np.array(seed.get("center", [0, 0, 0]), dtype=np.float64)
        self.seed_radius = float(seed["radius"])
        self.seed_type = seed.get("type", "sphere")

        sym_name = grammar.get("symmetry_group", "tetrahedral")
        self.base_vertices = SYMMETRY_GROUPS[sym_name]()

        self.iterations = grammar.get("iterations", [])

    def _build_ops(self):
        """
        Build a flat list of (boolean_fn, sdf_fn, center, radius, smooth_k)
        by recursively expanding iterations along symmetry axes.

        Each iteration places child primitives at every symmetry vertex,
        scaled and offset from every "active center" produced by prior iterations.
        """
        ops = []
        # Active centers: list of (center, radius) that the next iteration expands from
        active = [(self.seed_center.copy(), self.seed_radius)]

        for it in self.iterations:
            bool_fn = BOOLEAN_OPS[it["operation"]]
            prim_name = it.get("primitive", "sphere")
            sdf_fn = SDF_PRIMITIVES[prim_name]
            sf = float(it["scale_factor"])
            df = float(it.get("distance_factor", 1.0))
            sk = float(it.get("smooth_radius", 0.0))

            new_active = []
            for parent_center, parent_radius in active:
                child_radius = parent_radius * sf

                for v in self.base_vertices:
                    child_center = parent_center + v * parent_radius * df

                    # For "add": evaluate SDF-so-far at candidate center.
                    # Skip if center is in void (far from any surface).
                    if it["operation"] == "add":
                        seed_sdf_fn = SDF_PRIMITIVES[self.seed_type]
                        d = seed_sdf_fn(child_center.reshape(1, 3),
                                        self.seed_center, self.seed_radius)[0]
                        for b_fn, s_fn, c, r, k in ops:
                            dc = s_fn(child_center.reshape(1, 3), c, r)[0]
                            d = b_fn(dc, d, k)
                        if d > child_radius * 0.5:
                            continue

                    ops.append((bool_fn, sdf_fn, child_center, child_radius, sk))
                    new_active.append((child_center, child_radius))

            # Default: each step expands only from previous step's children,
            # so sf/df are always relative to the previous level.
            apply_to = it.get("apply_to", "new")
            if apply_to == "all":
                active = active + new_active
            else:  # "new" or "surface"
                active = new_active

        return ops

    def evaluate(self, points: np.ndarray) -> np.ndarray:
        """
        Evaluate the full SDF at an array of points.
        points: shape (..., 3)
        Returns: shape (...)  signed distance values.
        """
        seed_sdf = SDF_PRIMITIVES[self.seed_type]
        d = seed_sdf(points, self.seed_center, self.seed_radius)

        for bool_fn, sdf_fn, center, radius, sk in self._build_ops():
            d_child = sdf_fn(points, center, radius)
            d = bool_fn(d_child, d, sk)

        return d

    def to_raymarcher_json(self):
        """
        Export the SDF description as a flat JSON structure the GLSL
        raymarcher can consume at runtime.
        """
        ops = self._build_ops()
        result = {
            "seed": {
                "type": self.seed_type,
                "center": self.seed_center.tolist(),
                "radius": self.seed_radius,
            },
            "operations": [],
        }
        op_name_map = {
            smooth_union: "add",
            smooth_subtraction: "subtract",
            smooth_intersection: "intersect",
        }
        prim_name_map = {
            sdf_sphere: "sphere",
            sdf_cube: "cube",
            sdf_octahedron: "octahedron",
        }
        for bool_fn, sdf_fn, center, radius, sk in ops:
            result["operations"].append({
                "bool_op": op_name_map[bool_fn],
                "primitive": prim_name_map[sdf_fn],
                "center": center.tolist(),
                "radius": float(radius),
                "smooth_k": float(sk),
            })
        return result


# ── Marching cubes mesh extraction ────────────────────────────────────

def extract_mesh(evaluator: SierpSphereEvaluator, resolution=128, bounds=1.8):
    """
    Sample the SDF on a regular grid and extract an isosurface
    via marching cubes.  Returns a trimesh.Trimesh.
    """
    from skimage.measure import marching_cubes
    import trimesh

    lin = np.linspace(-bounds, bounds, resolution)
    X, Y, Z = np.meshgrid(lin, lin, lin, indexing="ij")
    points = np.stack([X, Y, Z], axis=-1)  # (res, res, res, 3)

    volume = evaluator.evaluate(points)

    verts, faces, normals, _ = marching_cubes(volume, level=0.0,
                                               spacing=(2*bounds/resolution,)*3)
    # Center the mesh
    verts -= bounds

    mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)
    return mesh


def grammar_to_gltf(grammar: dict, output_path: str = "sierpsphere.glb"):
    """Full pipeline: grammar → SDF → mesh → GLTF file."""
    ev = SierpSphereEvaluator(grammar)
    res = grammar.get("render", {}).get("resolution", 128)
    bnd = grammar.get("render", {}).get("bounds", 1.8)
    mesh = extract_mesh(ev, resolution=res, bounds=bnd)
    mesh.export(output_path)
    return output_path
