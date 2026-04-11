"""
Tests for fitness.py: _primitive_diversity, WEIGHTS, and mesh-based metrics.
Hard-gate and mesh tests require trimesh/scipy (available natively on host).
"""


# ── WEIGHTS ───────────────────────────────────────────────────────────────────

def test_weights_sum_to_one():
    from fitness import WEIGHTS
    total = sum(WEIGHTS.values())
    assert abs(total - 1.0) < 1e-9, f"Weights sum to {total}, expected 1.0"


def test_weights_all_positive():
    from fitness import WEIGHTS
    for k, v in WEIGHTS.items():
        assert v > 0, f"Weight {k} is not positive: {v}"


def test_weights_no_symmetry_preservation():
    from fitness import WEIGHTS
    assert "symmetry_preservation" not in WEIGHTS


def test_weights_expected_keys():
    from fitness import WEIGHTS
    expected = {
        "fractal_dimension", "curvature_variance",
        "normalised_S_V", "genus", "aspect_ratio", "min_wall_thickness",
        "min_feature_size", "drain_openings", "enclosed_voids", "no_islands",
        "thermal_mass_variance", "support_volume_ratio", "silhouette_complexity",
        "primitive_diversity", "fill_ratio",
    }
    assert set(WEIGHTS.keys()) == expected


def test_weights_fractal_dimension_raised():
    from fitness import WEIGHTS
    assert WEIGHTS["fractal_dimension"] >= 0.16


def test_weights_curvature_variance_raised():
    from fitness import WEIGHTS
    assert WEIGHTS["curvature_variance"] >= 0.12


def test_weights_fill_ratio_raised():
    from fitness import WEIGHTS
    assert WEIGHTS["fill_ratio"] >= 0.05


def test_primitive_diversity_key_present():
    from fitness import WEIGHTS
    assert "primitive_diversity" in WEIGHTS


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
    score = _primitive_diversity(_g("sphere", ["cube", "icosahedron"]))
    assert score >= 0.9


def test_diversity_seed_counted():
    from fitness import _primitive_diversity
    score = _primitive_diversity(_g("cube", ["sphere", "sphere"]))
    assert score > 0.0


def test_diversity_step_mix_bonus():
    from fitness import _primitive_diversity
    no_bonus = _primitive_diversity(_g("sphere", ["cube", "cube"]))
    bonus    = _primitive_diversity(_g("sphere", ["cube", "icosahedron"]))
    assert bonus > no_bonus


def test_diversity_score_in_range():
    from fitness import _primitive_diversity
    from mutate import diverse_population
    for g in diverse_population(24):
        score = _primitive_diversity(g)
        assert 0.0 <= score <= 1.0, f"Score out of range: {score}"


def test_diversity_empty_iterations():
    from fitness import _primitive_diversity
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


# ── _fail ─────────────────────────────────────────────────────────────────────

def test_fail_returns_zero_fitness():
    from fitness import _fail
    result = _fail("no_islands")
    assert result["fitness"] == 0.0
    assert result["hard_gate_failed"] == "no_islands"
    assert result["scores"] == {}


# ── mesh-based tests ──────────────────────────────────────────────────────────

def _unit_sphere_mesh():
    import trimesh
    return trimesh.creation.icosphere(subdivisions=3, radius=1.0)


def _base_grammar():
    return {"seed": {"type": "cube"}, "iterations": []}


def test_aspect_ratio_sphere():
    from fitness import _aspect_ratio
    assert _aspect_ratio(_unit_sphere_mesh()) == 1.0


def test_thermal_mass_sphere_high():
    from fitness import _thermal_mass
    assert _thermal_mass(_unit_sphere_mesh()) > 0.8


def test_thermal_mass_returns_float_in_range():
    from fitness import _thermal_mass
    score = _thermal_mass(_unit_sphere_mesh())
    assert 0.0 <= score <= 1.0


def test_genus_sphere_zero():
    from fitness import _genus
    assert _genus(_unit_sphere_mesh()) == 0.0


def test_compute_fitness_sphere_structure():
    from fitness import compute_fitness, WEIGHTS
    mesh = _unit_sphere_mesh()
    result = compute_fitness(mesh, _base_grammar())
    assert "fitness" in result
    assert "scores" in result
    if result.get("hard_gate_failed") is None:
        assert result["fitness"] > 0.0
        for k in WEIGHTS:
            assert k in result["scores"]


def test_compute_fitness_scores_in_range():
    from fitness import compute_fitness
    result = compute_fitness(_unit_sphere_mesh(), _base_grammar())
    if result.get("hard_gate_failed") is None:
        for k, v in result["scores"].items():
            assert 0.0 <= v <= 1.0, f"Score {k}={v} out of [0,1]"


def test_compute_fitness_fitness_bounded():
    from fitness import compute_fitness
    result = compute_fitness(_unit_sphere_mesh(), _base_grammar())
    assert 0.0 <= result["fitness"] <= 1.0


def test_compute_fitness_has_manufacturing_note():
    from fitness import compute_fitness
    result = compute_fitness(_unit_sphere_mesh(), _base_grammar())
    assert "manufacturing_note" in result


def test_compute_fitness_no_symmetry_preservation_score():
    from fitness import compute_fitness
    result = compute_fitness(_unit_sphere_mesh(), _base_grammar())
    assert "symmetry_preservation" not in result.get("scores", {})


# ── _normalised_sv ────────────────────────────────────────────────────────────

def test_normalised_sv_sphere_in_range():
    from fitness import _normalised_sv
    assert 0.0 <= _normalised_sv(_unit_sphere_mesh()) <= 1.0


# ── _fractal_dimension ────────────────────────────────────────────────────────

def test_fractal_dimension_sphere_in_range():
    from fitness import _fractal_dimension
    assert 0.0 <= _fractal_dimension(_unit_sphere_mesh()) <= 1.0


# ── _curvature_variance ───────────────────────────────────────────────────────

def test_curvature_variance_sphere_in_range():
    from fitness import _curvature_variance
    assert 0.0 <= _curvature_variance(_unit_sphere_mesh()) <= 1.0


# ── _silhouette ───────────────────────────────────────────────────────────────

def test_silhouette_sphere_in_range():
    from fitness import _silhouette
    assert 0.0 <= _silhouette(_unit_sphere_mesh()) <= 1.0


# ── _wall_thickness ───────────────────────────────────────────────────────────

def test_wall_thickness_sphere_returns_tuple():
    from fitness import _wall_thickness
    score, mm = _wall_thickness(_unit_sphere_mesh(), target_mm=80.0)
    assert 0.0 <= score <= 1.0
    assert mm > 0.0


def test_wall_thickness_mm_scales_with_target():
    from fitness import _wall_thickness
    _, mm_80 = _wall_thickness(_unit_sphere_mesh(), target_mm=80.0)
    _, mm_40 = _wall_thickness(_unit_sphere_mesh(), target_mm=40.0)
    assert mm_80 >= mm_40


# ── _support_ratio ────────────────────────────────────────────────────────────

def test_support_ratio_sphere_in_range():
    from fitness import _support_ratio
    assert 0.0 <= _support_ratio(_unit_sphere_mesh()) <= 1.0


# ── _aspect_ratio edge cases ──────────────────────────────────────────────────

def test_aspect_ratio_elongated_box_low():
    import trimesh
    from fitness import _aspect_ratio
    box = trimesh.creation.box([1, 1, 15])
    assert _aspect_ratio(box) == 0.0


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


# ── _fill_ratio ───────────────────────────────────────────────────────────────

def test_fill_ratio_sphere_low():
    from fitness import _fill_ratio
    assert _fill_ratio(_unit_sphere_mesh()) < 0.2


def test_fill_ratio_in_range():
    from fitness import _fill_ratio
    assert 0.0 <= _fill_ratio(_unit_sphere_mesh()) <= 1.0


# ── hard gates ────────────────────────────────────────────────────────────────

def test_compute_fitness_hard_gate_no_islands():
    import trimesh
    from fitness import compute_fitness
    a = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    a.apply_translation([-2, 0, 0])
    b = trimesh.creation.icosphere(subdivisions=2, radius=0.5)
    b.apply_translation([2, 0, 0])
    mesh = trimesh.util.concatenate([a, b])
    result = compute_fitness(mesh, _base_grammar())
    assert result["fitness"] == 0.0
    assert result["hard_gate_failed"] == "no_islands"
