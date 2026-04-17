"""
Tests for mutate.py: random_grammar_pure, diverse_population,
mutate, crossover, tournament_select.
New grammar schema: fd_u/fd_v instead of distance_factor, no symmetry_group field.
"""
from mutate import (
    OPERATIONS, PRIMITIVES, CHILD_PRIMITIVES, SEED_TO_GROUP,
    crossover, diverse_population, mutate,
    random_grammar_pure, tournament_select,
)


# ── random_grammar_pure ───────────────────────────────────────────────────────

def test_random_grammar_pure_structure():
    g = random_grammar_pure()
    assert "seed" in g
    assert "symmetry_group" not in g  # derived from seed, never stored
    assert "iterations" in g
    assert g["seed"]["type"] in PRIMITIVES
    assert 1 <= len(g["iterations"]) <= 4


def test_random_grammar_pure_first_step_carves():
    for _ in range(50):
        g = random_grammar_pure()
        assert g["iterations"][0]["operation"] in ("subtract", "intersect"), \
            "First step must carve (subtract or intersect)"


def test_random_grammar_pure_seed_pin():
    for prim in PRIMITIVES:
        g = random_grammar_pure(seed_type=prim)
        assert g["seed"]["type"] == prim


def test_random_grammar_pure_n_steps():
    for n in range(1, 5):
        g = random_grammar_pure(n_steps=n)
        assert len(g["iterations"]) == n


def test_random_grammar_pure_scale_in_range():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert 0.0 < it["scale_factor"] < 1.0


def test_random_grammar_pure_fd_invariant():
    """fd_u + fd_v <= 1.0 must hold for all generated steps."""
    for _ in range(50):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["fd_u"] + it["fd_v"] <= 1.0 + 1e-9, \
                f"fd invariant violated: fd_u={it['fd_u']} fd_v={it['fd_v']}"


def test_random_grammar_pure_fd_non_negative():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["fd_u"] >= 0.0
            assert it["fd_v"] >= 0.0


def test_random_grammar_pure_has_distance():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert "distance" in it
            assert it["distance"] > 0.0


def test_random_grammar_pure_no_distance_factor():
    for _ in range(10):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert "distance_factor" not in it


def test_random_grammar_pure_primitives_valid():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["primitive"] in CHILD_PRIMITIVES


def test_random_grammar_pure_smooth_radius_non_negative():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["smooth_radius"] >= 0.0


def test_random_grammar_pure_operations_valid():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["operation"] in OPERATIONS


# ── diverse_population ────────────────────────────────────────────────────────

def test_diverse_population_size():
    pop = diverse_population(24)
    assert len(pop) == 24


def test_diverse_population_contains_all_seed_types():
    pop = diverse_population(24)
    types = {g["seed"]["type"] for g in pop}
    assert types == set(PRIMITIVES), "All three seed types must be present"


def test_diverse_population_roughly_equal_thirds():
    pop = diverse_population(24)
    from collections import Counter
    counts = Counter(g["seed"]["type"] for g in pop)
    for prim in PRIMITIVES:
        assert counts[prim] >= 7, f"Expected ≥7 of {prim}, got {counts[prim]}"


def test_diverse_population_all_valid_structure():
    pop = diverse_population(24)
    for g in pop:
        assert "seed" in g
        assert "symmetry_group" not in g
        assert "iterations" in g
        assert len(g["iterations"]) >= 1
        assert g["seed"]["type"] in PRIMITIVES


def test_diverse_population_fd_invariant():
    pop = diverse_population(24)
    for g in pop:
        for it in g["iterations"]:
            assert it["fd_u"] + it["fd_v"] <= 1.0 + 1e-9


def test_diverse_population_no_empty_iterations():
    pop = diverse_population(24)
    for g in pop:
        assert len(g["iterations"]) >= 1


# ── mutate ────────────────────────────────────────────────────────────────────

def _base_grammar():
    return {
        "seed": {"type": "cube", "radius": 1.0},
        "iterations": [
            {"operation": "subtract", "primitive": "sphere",
             "fd_u": 0.3, "fd_v": 0.1,
             "distance": 0.7, "scale_factor": 0.3, "smooth_radius": 0.02},
        ],
    }


def test_mutate_returns_new_object():
    g = _base_grammar()
    g2 = mutate(g, rate=1.0)
    assert g2 is not g
    assert g2["iterations"] is not g["iterations"]


def test_mutate_preserves_structure():
    g = _base_grammar()
    g2 = mutate(g, rate=0.5)
    assert "seed" in g2
    assert "symmetry_group" not in g2
    assert len(g2["iterations"]) >= 1
    for it in g2["iterations"]:
        assert it["operation"] in OPERATIONS
        assert it["primitive"] in CHILD_PRIMITIVES
        assert 0.0 < it["scale_factor"] < 1.0


def test_mutate_zero_rate_unchanged():
    g = _base_grammar()
    g2 = mutate(g, rate=0.0)
    assert g2["seed"]["type"] == g["seed"]["type"]
    assert len(g2["iterations"]) == len(g["iterations"])


def test_mutate_fd_invariant_maintained():
    for _ in range(50):
        g = _base_grammar()
        g2 = mutate(g, rate=1.0)
        for it in g2["iterations"]:
            assert it["fd_u"] + it["fd_v"] <= 1.0 + 1e-9, \
                f"fd invariant violated after mutate: u={it['fd_u']} v={it['fd_v']}"


def test_mutate_fd_non_negative():
    for _ in range(30):
        g = _base_grammar()
        g2 = mutate(g, rate=1.0)
        for it in g2["iterations"]:
            assert it["fd_u"] >= 0.0
            assert it["fd_v"] >= 0.0


def test_mutate_high_rate_changes_something():
    import random as _random
    _random.seed(42)
    g = _base_grammar()
    changed = False
    for _ in range(20):
        g2 = mutate(g, rate=1.0)
        if (g2["seed"]["type"] != g["seed"]["type"] or
                g2["iterations"][0]["operation"] != g["iterations"][0]["operation"] or
                abs(g2["iterations"][0]["fd_u"] - g["iterations"][0]["fd_u"]) > 1e-6):
            changed = True
            break
    assert changed, "rate=1.0 should change at least one field across 20 tries"


def test_mutate_first_step_stays_valid():
    for _ in range(30):
        g = _base_grammar()
        g2 = mutate(g, rate=1.0)
        assert g2["iterations"][0]["operation"] in OPERATIONS


def test_mutate_seed_change_resamples_fd():
    """When seed type changes, fd invariant must still hold."""
    import random as _r
    _r.seed(7)
    for _ in range(30):
        g = _base_grammar()
        g["seed"]["type"] = "tetrahedron"
        g2 = mutate(g, rate=1.0)
        for it in g2["iterations"]:
            assert it["fd_u"] + it["fd_v"] <= 1.0 + 1e-9


# ── crossover ─────────────────────────────────────────────────────────────────

def _grammar_b():
    return {
        "seed": {"type": "icosahedron", "radius": 1.0},
        "iterations": [
            {"operation": "subtract", "primitive": "cube",
             "fd_u": 0.2, "fd_v": 0.3,
             "distance": 0.8, "scale_factor": 0.4, "smooth_radius": 0.01},
            {"operation": "intersect", "primitive": "tetrahedron",
             "fd_u": 0.1, "fd_v": 0.05,
             "distance": 0.6, "scale_factor": 0.25, "smooth_radius": 0.0},
        ],
    }


def test_crossover_returns_two_children():
    ca, cb = crossover(_base_grammar(), _grammar_b())
    assert len(ca["iterations"]) >= 1
    assert len(cb["iterations"]) >= 1


def test_crossover_children_inherit_seed_from_parents():
    """child_a inherits seed from parent_a; child_b from parent_b."""
    a = _base_grammar()      # cube
    b = _grammar_b()         # icosahedron
    ca, cb = crossover(a, b)
    assert ca["seed"]["type"] == a["seed"]["type"], \
        "child_a should inherit seed from parent_a"
    assert cb["seed"]["type"] == b["seed"]["type"], \
        "child_b should inherit seed from parent_b"


def test_crossover_no_symmetry_group_in_children():
    ca, cb = crossover(_base_grammar(), _grammar_b())
    assert "symmetry_group" not in ca
    assert "symmetry_group" not in cb


def test_crossover_fd_invariant_in_children():
    for _ in range(20):
        ca, cb = crossover(_base_grammar(), _grammar_b())
        for it in ca["iterations"] + cb["iterations"]:
            assert it["fd_u"] + it["fd_v"] <= 1.0 + 1e-9, \
                f"fd invariant violated in crossover child: u={it['fd_u']} v={it['fd_v']}"


def test_crossover_children_valid_operations():
    for _ in range(10):
        ca, cb = crossover(_base_grammar(), _grammar_b())
        for it in ca["iterations"] + cb["iterations"]:
            assert it["operation"] in OPERATIONS


def test_crossover_children_valid_primitives():
    for _ in range(10):
        ca, cb = crossover(_base_grammar(), _grammar_b())
        for it in ca["iterations"] + cb["iterations"]:
            assert it["primitive"] in CHILD_PRIMITIVES


# ── tournament_select ─────────────────────────────────────────────────────────

def test_tournament_select_returns_fittest():
    pop = [{"id": i} for i in range(10)]
    fits = list(range(10))
    winner = tournament_select(pop, fits, k=10)
    assert winner["id"] == 9


def test_tournament_select_k1_random():
    pop = [{"id": i} for i in range(5)]
    fits = [1.0] * 5
    winners = {tournament_select(pop, fits, k=1)["id"] for _ in range(30)}
    assert len(winners) > 1, "k=1 should pick randomly"


def test_tournament_select_result_in_population():
    pop = [{"id": i} for i in range(10)]
    fits = list(range(10))
    for _ in range(20):
        winner = tournament_select(pop, fits, k=3)
        assert winner in pop
