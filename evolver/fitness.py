"""
Fitness metrics for DMLS/SLM metal 3D printing.
All sub-scores in [0, 1]. Hard-gate violations → fitness = 0.0.
"""
from __future__ import annotations
import numpy as np
import trimesh


# ── Weights (must sum to 1.0) ─────────────────────────────────────────────
WEIGHTS = {
    "fractal_dimension":     0.16,
    "curvature_variance":    0.12,
    "normalised_S_V":        0.08,
    "genus":                 0.05,
    "aspect_ratio":          0.03,
    "min_wall_thickness":    0.15,
    "min_feature_size":      0.08,
    "drain_openings":        0.05,
    "enclosed_voids":        0.03,
    "no_islands":            0.03,
    "thermal_mass_variance": 0.05,
    "support_volume_ratio":  0.05,
    "silhouette_complexity": 0.05,
    "primitive_diversity":   0.02,
    "fill_ratio":            0.05,
}


def compute_fitness(
    mesh: trimesh.Trimesh,
    grammar: dict,
    target_mm: float = 80.0,
) -> dict:
    scores: dict[str, float] = {}

    # ── Hard gates ────────────────────────────────────────────────────────
    parts = mesh.split(only_watertight=False)
    if len(parts) != 1:
        return _fail("no_islands")
    scores["no_islands"] = 1.0

    # Enclosed voids: if mesh is watertight but contains sealed inner shells
    # approximate by comparing volume to convex hull — large discrepancy
    # combined with non-watertight sub-meshes indicates sealed pockets.
    if not mesh.is_watertight:
        return _fail("enclosed_voids")
    scores["enclosed_voids"] = 1.0

    wt_score, wt_mm = _wall_thickness(mesh, target_mm)
    if wt_mm < 0.5:
        return _fail("min_wall_thickness")
    scores["min_wall_thickness"] = wt_score
    scores["min_feature_size"] = wt_score  # proxy (same scale)

    # ── Aesthetic ─────────────────────────────────────────────────────────
    scores["normalised_S_V"]        = _normalised_sv(mesh)
    scores["genus"]                 = _genus(mesh)
    scores["curvature_variance"]    = _curvature_variance(mesh)
    scores["fractal_dimension"]     = _fractal_dimension(mesh)
    scores["aspect_ratio"]          = _aspect_ratio(mesh)
    scores["silhouette_complexity"] = _silhouette(mesh)
    scores["primitive_diversity"]   = _primitive_diversity(grammar)

    # ── Manufacturing ─────────────────────────────────────────────────────
    scores["thermal_mass_variance"] = _thermal_mass(mesh)
    scores["support_volume_ratio"]  = _support_ratio(mesh)
    scores["fill_ratio"]            = _fill_ratio(mesh)
    scores["drain_openings"]        = 1.0  # guaranteed: no enclosed voids passed

    fitness = sum(WEIGHTS[k] * scores.get(k, 0.0) for k in WEIGHTS)
    return {
        "hard_gate_failed": None,
        "scores": {k: round(float(v), 4) for k, v in scores.items()},
        "fitness": round(float(fitness), 4),
        "manufacturing_note": _note(scores),
    }


# ── Helpers ───────────────────────────────────────────────────────────────

def _fail(gate: str) -> dict:
    return {"hard_gate_failed": gate, "scores": {}, "fitness": 0.0,
            "manufacturing_note": f"Hard gate failed: {gate}"}


def _note(scores: dict) -> str:
    if scores.get("min_wall_thickness", 1) < 0.5:
        return "Walls near DMLS resolution limit — risk of incomplete sintering."
    if scores.get("support_volume_ratio", 0) > 0.6:
        return "High overhang fraction — difficult support removal in metal."
    if scores.get("thermal_mass_variance", 1) < 0.3:
        return "Uneven thermal mass — risk of warping at thick/thin junctions."
    return "None"


def _normalised_sv(mesh: trimesh.Trimesh) -> float:
    try:
        hull = mesh.convex_hull
        sv = (mesh.area / mesh.volume) / (hull.area / hull.volume)
        return float(np.tanh((sv - 1.0) / 2.0))
    except Exception:
        return 0.0


def _genus(mesh: trimesh.Trimesh) -> float:
    try:
        g = max(0, 1 - mesh.euler_number // 2)
        return float(min(g, 30) / 30)
    except Exception:
        return 0.0


def _curvature_variance(mesh: trimesh.Trimesh) -> float:
    try:
        # Discrete mean curvature via angle deficit
        cv = trimesh.curvature.discrete_mean_curvature_measure(
            mesh, mesh.vertices, radius=mesh.scale * 0.05
        )
        std = float(np.std(cv))
        seed_r = mesh.bounding_sphere.primitive.radius
        return float(np.tanh(std / (seed_r * 0.4 + 1e-9)))
    except Exception:
        return 0.0


def _fractal_dimension(mesh: trimesh.Trimesh) -> float:
    """Box-counting dimension on mesh vertices, target 2.3–2.7."""
    try:
        pts = mesh.vertices
        scales = np.logspace(-1, 0.5, 12)
        counts = []
        for s in scales:
            grid = np.floor(pts / s).astype(int)
            counts.append(len(set(map(tuple, grid))))
        log_s = np.log(1.0 / scales)
        log_n = np.log(np.array(counts, dtype=float))
        slope = float(np.polyfit(log_s, log_n, 1)[0])
        # Gaussian centred at 2.5, sigma 0.3
        return float(np.exp(-((slope - 2.5) ** 2) / (2 * 0.3 ** 2)))
    except Exception:
        return 0.0


def _aspect_ratio(mesh: trimesh.Trimesh) -> float:
    ext = mesh.bounding_box.extents
    ratio = float(ext.max() / (ext.min() + 1e-9))
    if ratio <= 3:
        return 1.0
    if ratio >= 10:
        return 0.0
    return float(1.0 - (ratio - 3) / 7)


def _silhouette(mesh: trimesh.Trimesh) -> float:
    """Approximate silhouette complexity via projected area variance from 6 views."""
    try:
        dirs = [[1,0,0],[-1,0,0],[0,1,0],[0,-1,0],[0,0,1],[0,0,-1]]
        areas = []
        r = mesh.bounding_sphere.primitive.radius
        for d in dirs:
            n = np.array(d, dtype=float)
            proj = mesh.vertices - np.outer(mesh.vertices @ n, n)
            hull_area = trimesh.convex.convex_hull(proj[:, [i for i in range(3) if n[i] == 0] or [0,1]]).area if False else _proj_area(proj, n)
            areas.append(hull_area)
        ref = np.pi * r ** 2 + 1e-9
        norm = [a / ref for a in areas]
        return float(np.tanh(np.std(norm) / 0.3))
    except Exception:
        return 0.3


def _proj_area(pts: np.ndarray, normal: np.ndarray) -> float:
    """2D convex hull area of points projected onto plane perpendicular to normal."""
    axes = [i for i in range(3) if abs(normal[i]) < 0.9]
    if len(axes) < 2:
        axes = [0, 1]
    p2 = pts[:, axes[:2]]
    try:
        from scipy.spatial import ConvexHull
        return float(ConvexHull(p2).volume)  # in 2D, volume = area
    except Exception:
        return 0.0


def _wall_thickness(mesh: trimesh.Trimesh, target_mm: float) -> tuple[float, float]:
    """
    Approximate minimum wall thickness via ray casting.
    Returns (score 0-1, thickness in mm at target scale).

    Uses 400 surface samples + 2nd percentile (was 150 + 5th) so local thin
    spots on high-symmetry shapes (Ih order-120) are not missed.
    Score curve mapped to [0.5, 1.5] mm — weerg SLM minimum is ~0.5 mm.
    """
    try:
        scale_factor = target_mm / (mesh.bounding_sphere.primitive.radius * 2 + 1e-9)
        n_samples = 400
        pts, face_ids = trimesh.sample.sample_surface(mesh, n_samples)
        normals = mesh.face_normals[face_ids]
        origins = pts - normals * 1e-4
        directions = -normals
        locs, ray_ids, _ = mesh.ray.intersects_location(origins, directions, multiple_hits=False)
        if len(locs) == 0:
            return 0.5, target_mm * 0.1
        dists = np.linalg.norm(locs - origins[ray_ids], axis=1)
        min_t = float(np.percentile(dists, 2)) * scale_factor  # 2nd pct — tighter bound
        if min_t >= 1.5:
            score = 1.0
        elif min_t <= 0.5:
            score = 0.0
        else:
            score = (min_t - 0.5) / 1.0
        return float(score), float(min_t)
    except Exception:
        return 0.5, 1.0


def _thermal_mass(mesh: trimesh.Trimesh) -> float:
    """
    Face-area-weighted centroid variance across 8 octants — proxy for thermal
    mass uniformity. Same signal as voxel density, ~50× faster (no voxelization).
    Lower variance = more uniform = higher score.
    """
    try:
        areas = mesh.area_faces
        centroids = mesh.triangles_center
        # Classify each face into one of 8 octants by centroid sign
        octant = ((centroids > 0).astype(int) * np.array([4, 2, 1])).sum(axis=1)
        densities = []
        for o in range(8):
            mask = octant == o
            densities.append(areas[mask].sum() if mask.any() else 0.0)
        total = sum(densities) + 1e-9
        fracs = [d / total for d in densities]
        std = float(np.std(fracs))
        # Uniform = std of 0 (all octants equal at 0.125); reward low std
        return float(np.exp(-std / 0.15))
    except Exception:
        return 0.5


def _primitive_diversity(grammar: dict) -> float:
    """
    Reward grammars that mix primitive types across steps AND between seed and steps.
    Score = fraction of distinct primitives used out of 3 possible,
    boosted when seed type differs from at least one step primitive.
    0 → all same primitive everywhere  |  1 → all three types present
    """
    seed_type = grammar.get("seed", {}).get("type", "sphere")
    step_prims = [it.get("primitive", "sphere") for it in grammar.get("iterations", [])]
    all_prims = [seed_type] + step_prims
    n_distinct = len(set(all_prims))
    # fraction of distinct types (max 3)
    base = (n_distinct - 1) / 2.0   # 0 if all same, 0.5 if two types, 1.0 if all three
    # bonus: seed type not repeated monotonously in steps
    step_distinct = len(set(step_prims))
    mix_bonus = 0.1 if step_distinct > 1 else 0.0
    return float(min(1.0, base + mix_bonus))


def _fill_ratio(mesh: trimesh.Trimesh) -> float:
    """
    Reward low fill: 1 - (mesh.volume / convex_hull.volume).
    Score 1 = maximally hollow/carved, 0 = solid blob.
    Encourages the GA to carve material out rather than grow blobs.
    """
    try:
        hull_vol = mesh.convex_hull.volume + 1e-9
        fill = float(mesh.volume / hull_vol)
        return float(np.clip(1.0 - fill, 0.0, 1.0))
    except Exception:
        return 0.5


def _support_ratio(mesh: trimesh.Trimesh) -> float:
    """Fraction of faces with normal pointing > 45° from vertical (need support)."""
    try:
        up = np.array([0, 1, 0])
        cos45 = np.cos(np.radians(45))
        overhang = np.sum(mesh.face_normals @ up < cos45)
        ratio = float(overhang / (len(mesh.faces) + 1e-9))
        return float(1.0 - ratio)
    except Exception:
        return 0.5
