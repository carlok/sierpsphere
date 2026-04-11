"""
Tests for grammar_name.py: grammar_name() and grammar_slug().
New encoding: T/C/I seed chars, fd_u/fd_v format (u30v10), no group prefix.
"""
import re
from grammar_name import grammar_name, grammar_slug

POSIX_SAFE = re.compile(r'^[A-Za-z0-9._-]+$')


def _classic():
    return {
        "seed": {"type": "tetrahedron", "radius": 1.0},
        "iterations": [
            {"operation": "subtract", "primitive": "tetrahedron",
             "fd_u": 0.30, "fd_v": 0.10, "smooth_radius": 0.02,
             "scale_factor": 0.30, "distance": 0.70},
            {"operation": "add", "primitive": "cube",
             "fd_u": 0.50, "fd_v": 0.20, "smooth_radius": 0.0,
             "scale_factor": 0.30, "distance": 0.70},
        ],
    }


# ── grammar_name ──────────────────────────────────────────────────────────────

def test_grammar_name_starts_with_seed_char():
    assert grammar_name(_classic()).startswith("T.")


def test_grammar_name_known_output():
    # smooth_radius=0.02 → rho=4; fd_u=0.30→u30, fd_v=0.10→v10; defaults omitted
    assert grammar_name(_classic()) == "T.-t4u30v10 +c0u50v20"


def test_grammar_name_seed_mapping():
    for stype, char in [("tetrahedron", "T"), ("cube", "C"), ("icosahedron", "I")]:
        g = _classic()
        g["seed"]["type"] = stype
        assert grammar_name(g).startswith(char + ".")


def test_grammar_name_op_display_chars():
    name = grammar_name(_classic())
    steps_part = name.split(".", 1)[1]
    for bad in ("N", "P", "X"):
        assert bad not in steps_part, f"Slug char {bad!r} found in display name {name!r}"


def test_grammar_name_subtract_shows_minus():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "subtract", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "-s" in grammar_name(g)


def test_grammar_name_add_shows_plus():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "add", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "+s" in grammar_name(g)


def test_grammar_name_intersect_shows_x():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "intersect", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "xs" in grammar_name(g)


def test_grammar_name_scale_omitted_at_default():
    # scale_factor=0.30 is default — k token must not appear
    assert "k" not in grammar_name(_classic())


def test_grammar_name_scale_shown_when_nondefault():
    g = _classic()
    g["iterations"][0]["scale_factor"] = 0.45
    assert "k45" in grammar_name(g)


def test_grammar_name_distance_omitted_at_default():
    # distance=0.70 is default — d token must not appear
    assert "d" not in grammar_name(_classic())


def test_grammar_name_distance_shown_when_nondefault():
    g = _classic()
    g["iterations"][0]["distance"] = 0.85
    assert "d85" in grammar_name(g)


def test_grammar_name_steps_space_separated():
    steps_part = grammar_name(_classic()).split(".", 1)[1]
    assert " " in steps_part


def test_grammar_name_smooth_zero_gives_rho0():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "subtract", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "-s0u" in grammar_name(g)


def test_grammar_name_smooth_encoded_correctly():
    # smooth_radius=0.02 → rho=4 (0.02/0.005=4)
    assert "-t4u" in grammar_name(_classic())


def test_grammar_name_no_iterations():
    g = _classic()
    g["iterations"] = []
    assert grammar_name(g) == "T."


# ── grammar_slug ──────────────────────────────────────────────────────────────

def test_grammar_slug_posix_safe():
    from mutate import diverse_population
    for g in diverse_population(12):
        slug = grammar_slug(g)
        assert POSIX_SAFE.match(slug), f"Slug not POSIX safe: {slug!r}"


def test_grammar_slug_known_output():
    # T.Nt4u30v10Pc0u50v20
    assert grammar_slug(_classic()) == "T.Nt4u30v10Pc0u50v20"


def test_grammar_slug_no_display_chars():
    from mutate import diverse_population
    for g in diverse_population(24):
        slug = grammar_slug(g)
        for bad in ("+", "-", " "):
            assert bad not in slug, f"Bad char {bad!r} in slug {slug!r}"


def test_grammar_slug_subtract_shows_N():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "subtract", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert grammar_slug(g).split(".", 1)[1].startswith("Ns")


def test_grammar_slug_add_shows_P():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "add", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "Ps" in grammar_slug(g)


def test_grammar_slug_intersect_shows_X():
    g = {"seed": {"type": "cube"}, "iterations": [
        {"operation": "intersect", "primitive": "sphere",
         "fd_u": 0.3, "fd_v": 0.1, "smooth_radius": 0.0,
         "scale_factor": 0.30, "distance": 0.70}
    ]}
    assert "Xs" in grammar_slug(g)


def test_grammar_slug_scale_encoded_with_k():
    g = _classic()
    g["iterations"][0]["scale_factor"] = 0.45
    assert "k45" in grammar_slug(g)


def test_grammar_slug_distance_encoded_with_d():
    g = _classic()
    g["iterations"][0]["distance"] = 0.85
    assert "d85" in grammar_slug(g)


def test_grammar_slug_steps_no_spaces():
    assert " " not in grammar_slug(_classic())


def test_grammar_slug_no_iterations():
    g = _classic()
    g["iterations"] = []
    slug = grammar_slug(g)
    assert slug == "T."
    assert POSIX_SAFE.match(slug)


def test_grammar_slug_cube_seed():
    g = _classic()
    g["seed"]["type"] = "cube"
    assert grammar_slug(g).startswith("C.")


def test_grammar_slug_icosahedron_seed():
    g = _classic()
    g["seed"]["type"] = "icosahedron"
    assert grammar_slug(g).startswith("I.")
