import numpy as np
import trimesh

from sdf import filter_largest_component


def test_filter_largest_component_removes_islands() -> None:
    big = trimesh.creation.icosphere(subdivisions=1, radius=1.0)
    small = trimesh.creation.icosphere(subdivisions=1, radius=0.2)
    small.apply_translation([5.0, 0.0, 0.0])
    merged = trimesh.util.concatenate([big, small])

    filtered = filter_largest_component(merged)
    parts = filtered.split(only_watertight=False)

    assert len(parts) == 1
    assert len(filtered.faces) == len(big.faces)
    assert np.all(np.abs(filtered.centroid) < 0.5)

