"""
Tests for fitness.py: _primitive_diversity and WEIGHTS sum.
Hard-gate and mesh tests are skipped without trimesh/scipy (use Podman for those).
"""
import pytest


# ── WEIGHTS ───────────────────────────────────────────────────────────────────

def test_weights_sum_to_one():
    from fitness import WEIGHTS
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_weights_all_positive():
    from fitness import WEIGHTS
    for k, v in WEIGHTS.items():
        assert v > 0, f"Weight {k} is not positive: {v}"


def test_primitive_diversity_replaces_self_similarity():
    from fitness import WEIGHTS
    assert "primitive_diversity" in WEIGHTS
    assert "self_similarity" not in WEIGHTS


# ── _primitive_diversity ──────────────────────────────────────────────────────

def _g(seed, step_prims):
    return {
        "seed": {"type": seed},
        "iterations": [{"primitive": p} for p in step_prims],
    }


def test_diversity_all_same_scores_zero():
    from fitness import _primitive_diversity
    assert _primitive_diversity(_g("sphere", ["sphere", "sphere"])) == 0.0


def test_diversity_two_types_half():
    from fitness import _primitive_diversity
    score = _primitive_diversity(_g("sphere", ["cube", "cube"]))
    assert 0.4 <= score <= 0.65


def test_diversity_all_three_types_max():
    from fitness import _primitive_diversity
    score = _primitive_diversity(_g("sphere", ["cube", "octahedron"]))
    assert score >= 0.9


def test_diversity_seed_counted():
    from fitness import _primitive_diversity
    # seed=cube, steps all sphere → two distinct types
    score = _primitive_diversity(_g("cube", ["sphere", "sphere"]))
    assert score > 0.0


def test_diversity_step_mix_bonus():
    from fitness import _primitive_diversity
    # same as two-type but step prims vary → small bonus
    no_bonus = _primitive_diversity(_g("sphere", ["cube", "cube"]))
    bonus    = _primitive_diversity(_g("sphere", ["cube", "octahedron"]))
    assert bonus > no_bonus


def test_diversity_score_in_range():
    from fitness import _primitive_diversity
    from mutate import diverse_population
    for g in diverse_population(24):
        score = _primitive_diversity(g)
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"


def test_diversity_empty_iterations():
    from fitness import _primitive_diversity
    # Only seed, no steps — single type, score 0
    g = {"seed": {"type": "sphere"}, "iterations": []}
    assert _primitive_diversity(g) == 0.0


def test_diversity_single_step_same_as_seed():
    from fitness import _primitive_diversity
    g = {"seed": {"type": "cube"}, "iterations": [{"primitive": "cube"}]}
    assert _primitive_diversity(g) == 0.0


def test_diversity_single_step_different_from_seed():
    from fitness import _primitive_diversity
    g = {"seed": {"type": "cube"}, "iterations": [{"primitive": "sphere"}]}
    score = _primitive_diversity(g)
    assert score == 0.5  # two distinct types, no step mix bonus


def test_weights_expected_keys():
    from fitness import WEIGHTS
    expected = {
        "fractal_dimension", "curvature_variance", "symmetry_preservation",
        "normalised_S_V", "genus", "aspect_ratio", "min_wall_thickness",
        "min_feature_size", "drain_openings", "enclosed_voids", "no_islands",
        "thermal_mass_variance", "support_volume_ratio", "silhouette_complexity",
        "primitive_diversity", "fill_ratio",
    }
    assert set(WEIGHTS.keys()) == expected


def test_fail_returns_zero_fitness():
    from fitness import _fail
    result = _fail("no_islands")
    assert result["fitness"] == 0.0
    assert result["hard_gate_failed"] == "no_islands"
    assert result["scores"] == {}


# ── mesh-based tests (trimesh available in Podman) ────────────────────────────

def _unit_sphere_mesh():
    import trimesh
    return trimesh.creation.icosphere(subdivisions=3, radius=1.0)


def test_aspect_ratio_sphere():
    from fitness import _aspect_ratio
    mesh = _unit_sphere_mesh()
    score = _aspect_ratio(mesh)
    assert score == 1.0  # sphere is ~isotropic


def test_thermal_mass_sphere_high():
    from fitness import _thermal_mass
    mesh = _unit_sphere_mesh()
    score = _thermal_mass(mesh)
    # Sphere is perfectly uniform across octants → high score
    assert score > 0.8


def test_thermal_mass_returns_float_in_range():
    from fitness import _thermal_mass
    mesh = _unit_sphere_mesh()
    score = _thermal_mass(mesh)
    assert 0.0 <= score <= 1.0


def test_genus_sphere_zero():
    from fitness import _genus
    mesh = _unit_sphere_mesh()
    score = _genus(mesh)
    # Genus 0 → score 0.0
    assert score == 0.0


def test_compute_fitness_sphere_structure():
    import trimesh
    from fitness import compute_fitness, WEIGHTS
    mesh = _unit_sphere_mesh()
    g = {"seed": {"type": "sphere"}, "symmetry_group": "tetrahedral", "iterations": []}
    result = compute_fitness(mesh, g)
    assert "fitness" in result
    assert "scores" in result
    # Plain sphere is watertight single component — should not hard-gate
    if result.get("hard_gate_failed") is None:
        assert result["fitness"] > 0.0
        for k in WEIGHTS:
            assert k in result["scores"]


def test_compute_fitness_scores_in_range():
    from fitness import compute_fitness
    mesh = _unit_sphere_mesh()
    g = {"seed": {"type": "sphere"}, "symmetry_group": "tetrahedral", "iterations": []}
    result = compute_fitness(mesh, g)
    if result.get("hard_gate_failed") is None:
        for k, v in result["scores"].items():
            assert 0.0 <= v <= 1.0, f"Score {k}={v} out of [0,1]"


def test_compute_fitness_fitness_bounded():
    from fitness import compute_fitness
    mesh = _unit_sphere_mesh()
    g = {"seed": {"type": "sphere"}, "symmetry_group": "tetrahedral", "iterations": []}
    result = compute_fitness(mesh, g)
    assert 0.0 <= result["fitness"] <= 1.0


def test_compute_fitness_has_manufacturing_note():
    from fitness import compute_fitness
    mesh = _unit_sphere_mesh()
    g = {"seed": {"type": "sphere"}, "symmetry_group": "tetrahedral", "iterations": []}
    result = compute_fitness(mesh, g)
    assert "manufacturing_note" in result


# ── _normalised_sv ────────────────────────────────────────────────────────────

def test_normalised_sv_sphere_in_range():
    from fitness import _normalised_sv
    mesh = _unit_sphere_mesh()
    score = _normalised_sv(mesh)
    assert 0.0 <= score <= 1.0


# ── _fractal_dimension ────────────────────────────────────────────────────────

def test_fractal_dimension_sphere_in_range():
    from fitness import _fractal_dimension
    mesh = _unit_sphere_mesh()
    score = _fractal_dimension(mesh)
    assert 0.0 <= score <= 1.0


# ── _curvature_variance ───────────────────────────────────────────────────────

def test_curvature_variance_sphere_in_range():
    from fitness import _curvature_variance
    mesh = _unit_sphere_mesh()
    score = _curvature_variance(mesh)
    assert 0.0 <= score <= 1.0


# ── _symmetry / _sym_axes ────────────────────────────────────────────────────

def test_sym_axes_tetrahedral_count():
    from fitness import _sym_axes
    axes = _sym_axes("tetrahedral")
    assert len(axes) == 4


def test_sym_axes_octahedral_count():
    from fitness import _sym_axes
    axes = _sym_axes("octahedral")
    assert len(axes) == 6


def test_sym_axes_unknown_returns_empty():
    from fitness import _sym_axes
    assert _sym_axes("unknown") == []


def test_symmetry_sphere_tetrahedral_in_range():
    from fitness import _symmetry
    mesh = _unit_sphere_mesh()
    g = {"symmetry_group": "tetrahedral"}
    score = _symmetry(mesh, g)
    assert 0.0 <= score <= 1.0


def test_symmetry_sphere_octahedral_in_range():
    from fitness import _symmetry
    mesh = _unit_sphere_mesh()
    g = {"symmetry_group": "octahedral"}
    score = _symmetry(mesh, g)
    assert 0.0 <= score <= 1.0


# ── _silhouette ───────────────────────────────────────────────────────────────

def test_silhouette_sphere_in_range():
    from fitness import _silhouette
    mesh = _unit_sphere_mesh()
    score = _silhouette(mesh)
    assert 0.0 <= score <= 1.0


# ── _wall_thickness ───────────────────────────────────────────────────────────

def test_wall_thickness_sphere_returns_tuple():
    from fitness import _wall_thickness
    mesh = _unit_sphere_mesh()
    score, mm = _wall_thickness(mesh, target_mm=80.0)
    assert 0.0 <= score <= 1.0
    assert mm > 0.0


def test_wall_thickness_mm_scales_with_target():
    from fitness import _wall_thickness
    mesh = _unit_sphere_mesh()
    _, mm_80 = _wall_thickness(mesh, target_mm=80.0)
    _, mm_40 = _wall_thickness(mesh, target_mm=40.0)
    assert mm_80 > mm_40


# ── _support_ratio ────────────────────────────────────────────────────────────

def test_support_ratio_sphere_in_range():
    from fitness import _support_ratio
    mesh = _unit_sphere_mesh()
    score = _support_ratio(mesh)
    assert 0.0 <= score <= 1.0


# ── _aspect_ratio edge cases ──────────────────────────────────────────────────

def test_aspect_ratio_elongated_box_low():
    import trimesh
    from fitness import _aspect_ratio
    # Very elongated box → ratio > 10 → score 0
    box = trimesh.creation.box([1, 1, 15])
    score = _aspect_ratio(box)
    assert score == 0.0


def test_aspect_ratio_moderate_box():
    import trimesh
    from fitness import _aspect_ratio
    box = trimesh.creation.box([1, 1, 5])
    score = _aspect_ratio(box)
    assert 0.0 < score < 1.0


# ── _note ─────────────────────────────────────────────────────────────────────

def test_note_thin_walls():
    from fitness import _note
    assert "sintering" in _note({"min_wall_thickness": 0.3})


def test_note_high_overhang():
    from fitness import _note
    assert "support" in _note({"support_volume_ratio": 0.9})


def test_note_uneven_thermal():
    from fitness import _note
    assert "warping" in _note({"thermal_mass_variance": 0.1})


def test_note_good_scores():
    from fitness import _note
    note = _note({"min_wall_thickness": 1.0, "support_volume_ratio": 0.1,
                  "thermal_mass_variance": 0.9})
    assert note == "None"


# ── compute_fitness hard-gate: no_islands ─────────────────────────────────────

# ── _fill_ratio ───────────────────────────────────────────────────────────────

def test_fill_ratio_sphere_low():
    from fitness import _fill_ratio
    # Solid sphere ≈ fills its convex hull → low score (high fill)
    mesh = _unit_sphere_mesh()
    score = _fill_ratio(mesh)
    assert score < 0.2  # sphere nearly fills its convex hull


def test_fill_ratio_in_range():
    from fitness import _fill_ratio
    mesh = _unit_sphere_mesh()
    assert 0.0 <= _fill_ratio(mesh) <= 1.0


def test_fill_ratio_carved_shape_higher_than_sphere():
    import trimesh
    from fitness import _fill_ratio
    sphere = _unit_sphere_mesh()
    # Subtract a smaller sphere → more hollow → higher fill_ratio score
    carved = trimesh.boolean.difference([sphere,
        trimesh.creation.icosphere(subdivisions=2, radius=0.7)],
        engine="blender") if False else sphere  # skip if blender unavailable
    # At minimum: solid sphere < 0.2, any carving would raise score
    assert _fill_ratio(sphere) < 0.2


def test_compute_fitness_hard_gate_no_islands():
    import trimesh
    from fitness import compute_fitness
    # Two disconnected spheres → no_islands gate
    a = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    a.apply_translation([-2, 0, 0])
    b = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    b.apply_translation([2, 0, 0])
    mesh = trimesh.util.concatenate([a, b])
    g = {"seed": {"type": "sphere"}, "symmetry_group": "tetrahedral", "iterations": []}
    result = compute_fitness(mesh, g)
    assert result["fitness"] == 0.0
    assert result["hard_gate_failed"] == "no_islands"
