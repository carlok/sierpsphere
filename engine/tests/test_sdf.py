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

