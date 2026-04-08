import numpy as np

from sdf import SierpSphereEvaluator, sdf_cube, sdf_sphere


def test_sdf_cube_sign_center_and_outside() -> None:
    center = np.array([0.0, 0.0, 0.0])
    inside = sdf_cube(np.array([[0.0, 0.0, 0.0]]), center, 1.0)[0]
    outside = sdf_cube(np.array([[2.0, 0.0, 0.0]]), center, 1.0)[0]
    assert inside < 0
    assert outside > 0


def test_cube_seed_evaluator_differs_from_sphere_at_corner() -> None:
    cube_grammar = {
        "seed": {"type": "cube", "radius": 1.0, "center": [0, 0, 0]},
        "iterations": [],
    }
    sphere_grammar = {
        "seed": {"type": "sphere", "radius": 1.0, "center": [0, 0, 0]},
        "iterations": [],
    }
    point = np.array([[0.9, 0.9, 0.9]])
    cube_d = SierpSphereEvaluator(cube_grammar).evaluate(point)[0]
    sphere_d = SierpSphereEvaluator(sphere_grammar).evaluate(point)[0]
    assert cube_d < sphere_d


def test_sdf_sphere_center_negative() -> None:
    d = sdf_sphere(np.array([[0.0, 0.0, 0.0]]), np.array([0.0, 0.0, 0.0]), 1.0)[0]
    assert d < 0


def test_apply_to_default_matches_all_behavior() -> None:
    base = {
        "seed": {"type": "sphere", "radius": 1.0, "center": [0, 0, 0]},
        "symmetry_group": "tetrahedral",
        "iterations": [
            {"operation": "subtract", "primitive": "sphere", "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.0},
            {"operation": "subtract", "primitive": "sphere", "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.0},
        ],
    }
    explicit_all = {
        **base,
        "iterations": [dict(base["iterations"][0], apply_to="all"), dict(base["iterations"][1], apply_to="all")],
    }
    default_count = len(SierpSphereEvaluator(base)._build_ops())
    all_count = len(SierpSphereEvaluator(explicit_all)._build_ops())
    assert default_count == all_count


def test_apply_to_surface_differs_from_new() -> None:
    common = {
        "seed": {"type": "sphere", "radius": 1.0, "center": [0, 0, 0]},
        "symmetry_group": "tetrahedral",
        "iterations": [
            {"operation": "subtract", "primitive": "sphere", "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.02, "apply_to": "all"},
            {"operation": "add", "primitive": "sphere", "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.01},
        ],
    }
    g_surface = {**common, "iterations": [common["iterations"][0], dict(common["iterations"][1], apply_to="surface")]}
    g_new = {**common, "iterations": [common["iterations"][0], dict(common["iterations"][1], apply_to="new")]}
    surface_count = len(SierpSphereEvaluator(g_surface)._build_ops())
    new_count = len(SierpSphereEvaluator(g_new)._build_ops())
    assert surface_count != new_count

