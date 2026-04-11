"""
Tests for grammar_name.py: grammar_name() and grammar_slug().
"""
import re
import pytest
from grammar_name import grammar_name, grammar_slug

POSIX_SAFE = re.compile(r'^[A-Za-z0-9._-]+$')


def _classic():
    return {
        "seed": {"type": "sphere", "radius": 1.0, "center": [0, 0, 0]},
        "symmetry_group": "tetrahedral",
        "iterations": [
            {"operation": "subtract", "primitive": "sphere",
             "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.02},
            {"operation": "add",      "primitive": "sphere",
             "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.01},
            {"operation": "subtract", "primitive": "sphere",
             "scale_factor": 0.5, "distance_factor": 1.0, "smooth_radius": 0.005},
        ],
    }


# ── grammar_name ──────────────────────────────────────────────────────────────

def test_grammar_name_classic():
    name = grammar_name(_classic())
    assert name.startswith("Td.S.")
    assert "-s" in name
    assert "+s" in name


def test_grammar_name_group_mapping():
    g = _classic()
    for sym, code in [("tetrahedral","Td"), ("octahedral","Oh"), ("icosahedral","Ih")]:
        g["symmetry_group"] = sym
        assert grammar_name(g).startswith(code)


def test_grammar_name_seed_mapping():
    g = _classic()
    for stype, code in [("sphere","S"), ("cube","C"), ("octahedron","O")]:
        g["seed"]["type"] = stype
        assert grammar_name(g).split(".")[1] == code


def test_grammar_name_op_chars():
    g = _classic()
    name = grammar_name(g)
    # Display notation uses - + x
    steps_part = name.split(".", 2)[2]
    for ch in steps_part:
        assert ch not in ("N", "P", "X"), "Display name should not contain slug chars"


def test_grammar_name_scale_omitted_at_half():
    g = _classic()  # all scale_factor=0.5
    name = grammar_name(g)
    assert ":" not in name, "scale omitted when 0.5"


def test_grammar_name_scale_shown_when_not_half():
    g = _classic()
    g["iterations"][0]["scale_factor"] = 0.47
    name = grammar_name(g)
    assert ":47" in name


def test_grammar_name_distance_omitted_at_one():
    g = _classic()
    name = grammar_name(g)
    assert "@" not in name


def test_grammar_name_distance_shown_when_not_one():
    g = _classic()
    g["iterations"][0]["distance_factor"] = 1.2
    name = grammar_name(g)
    assert "@" in name


# ── grammar_slug ──────────────────────────────────────────────────────────────

def test_grammar_slug_posix_safe():
    from mutate import diverse_population
    pop = diverse_population(12)
    for g in pop:
        slug = grammar_slug(g)
        assert POSIX_SAFE.match(slug), f"Slug not POSIX safe: {slug!r}"


def test_grammar_slug_classic_known():
    slug = grammar_slug(_classic())
    assert slug == "Td.S.Ns4Ps2Ns1"


def test_grammar_slug_no_display_chars():
    from mutate import diverse_population
    for g in diverse_population(24):
        slug = grammar_slug(g)
        for bad in ("+", "-", ":", "@"):
            assert bad not in slug, f"Bad char {bad!r} in slug {slug!r}"


def test_grammar_slug_scale_encoded_with_k():
    g = _classic()
    g["iterations"][0]["scale_factor"] = 0.47
    slug = grammar_slug(g)
    assert "k47" in slug


def test_grammar_slug_distance_encoded_with_d():
    g = _classic()
    g["iterations"][0]["distance_factor"] = 1.1
    slug = grammar_slug(g)
    assert "d110" in slug


def test_grammar_name_intersect_shows_x():
    g = _classic()
    g["iterations"][0]["operation"] = "intersect"
    name = grammar_name(g)
    assert "x" in name.split(".", 2)[2]


def test_grammar_slug_intersect_shows_X():
    g = _classic()
    g["iterations"][0]["operation"] = "intersect"
    slug = grammar_slug(g)
    assert "X" in slug.split(".", 2)[2]


def test_grammar_name_no_iterations():
    g = _classic()
    g["iterations"] = []
    name = grammar_name(g)
    # Should still have group.seed. prefix, steps empty
    parts = name.split(".")
    assert parts[0] == "Td"
    assert parts[1] == "S"
    assert parts[2] == ""


def test_grammar_slug_no_iterations():
    g = _classic()
    g["iterations"] = []
    slug = grammar_slug(g)
    assert slug == "Td.S."
    assert POSIX_SAFE.match(slug)


def test_grammar_name_steps_space_separated():
    g = _classic()  # 3 steps
    name = grammar_name(g)
    steps_part = name.split(".", 2)[2]
    # display name separates steps with spaces
    assert " " in steps_part


def test_grammar_slug_steps_no_spaces():
    slug = grammar_slug(_classic())
    assert " " not in slug


def test_grammar_name_smooth_zero_gives_rho0():
    g = _classic()
    g["iterations"] = [{"operation": "subtract", "primitive": "sphere",
                         "scale_factor": 0.5, "distance_factor": 1.0,
                         "smooth_radius": 0.0}]
    name = grammar_name(g)
    assert "-s0" in name


def test_grammar_slug_octahedron_seed():
    g = _classic()
    g["seed"]["type"] = "octahedron"
    slug = grammar_slug(g)
    assert slug.startswith("Td.O.")


def test_grammar_slug_cube_primitive():
    g = _classic()
    g["iterations"] = [{"operation": "add", "primitive": "cube",
                         "scale_factor": 0.5, "distance_factor": 1.0,
                         "smooth_radius": 0.01}]
    slug = grammar_slug(g)
    assert "Pc2" in slug


def test_grammar_name_add_shows_plus():
    g = _classic()
    g["iterations"] = [{"operation": "add", "primitive": "sphere",
                         "scale_factor": 0.5, "distance_factor": 1.0,
                         "smooth_radius": 0.01}]
    name = grammar_name(g)
    assert "+s" in name
