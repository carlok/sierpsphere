"""
Tests for mutate.py: random_grammar_pure, diverse_population,
mutate, crossover, tournament_select.
"""
import pytest
from mutate import (
    OPERATIONS, PRIMITIVES, SYMMETRIES,
    crossover, diverse_population, mutate,
    random_grammar_pure, tournament_select,
)


# ── random_grammar_pure ───────────────────────────────────────────────────────

def test_random_grammar_pure_structure():
    g = random_grammar_pure()
    assert "seed" in g
    assert "symmetry_group" in g
    assert "iterations" in g
    assert g["seed"]["type"] in PRIMITIVES
    assert g["symmetry_group"] in SYMMETRIES
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


# ── mutate ────────────────────────────────────────────────────────────────────

def _base_grammar():
    return {
        "seed": {"type": "sphere", "radius": 1.0, "center": [0, 0, 0]},
        "symmetry_group": "tetrahedral",
        "iterations": [
            {"operation": "subtract", "primitive": "sphere",
             "scale_factor": 0.5, "distance_factor": 1.0,
             "smooth_radius": 0.02, "apply_to": "new"},
        ],
        "render": {"resolution": 128, "bounds": 1.8},
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
    assert "symmetry_group" in g2
    assert len(g2["iterations"]) >= 1
    for it in g2["iterations"]:
        assert it["operation"] in OPERATIONS
        assert it["primitive"] in PRIMITIVES
        assert 0.0 < it["scale_factor"] < 1.0


def test_mutate_zero_rate_unchanged():
    g = _base_grammar()
    g2 = mutate(g, rate=0.0)
    assert g2["symmetry_group"] == g["symmetry_group"]
    assert g2["seed"]["type"] == g["seed"]["type"]
    assert len(g2["iterations"]) == len(g["iterations"])


# ── crossover ─────────────────────────────────────────────────────────────────

def test_crossover_returns_two_children():
    a = _base_grammar()
    b = {**_base_grammar(), "symmetry_group": "octahedral"}
    b["iterations"].append({"operation": "add", "primitive": "cube",
                             "scale_factor": 0.4, "distance_factor": 1.0,
                             "smooth_radius": 0.01, "apply_to": "new"})
    ca, cb = crossover(a, b)
    assert ca is not a
    assert cb is not b
    assert len(ca["iterations"]) >= 1
    assert len(cb["iterations"]) >= 1


def test_crossover_steps_come_from_parents():
    a = _base_grammar()
    b = {**_base_grammar()}
    b["iterations"] = [{"operation": "intersect", "primitive": "octahedron",
                         "scale_factor": 0.3, "distance_factor": 0.9,
                         "smooth_radius": 0.0, "apply_to": "new"}]
    ca, cb = crossover(a, b)
    all_prims = {"sphere", "octahedron"}
    for it in ca["iterations"] + cb["iterations"]:
        assert it["primitive"] in all_prims


# ── tournament_select ─────────────────────────────────────────────────────────

def test_tournament_select_returns_fittest():
    pop = [{"id": i} for i in range(10)]
    fits = list(range(10))
    # With k = len(pop), always returns the fittest
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


# ── additional random_grammar_pure ───────────────────────────────────────────

def test_random_grammar_pure_operations_valid():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["operation"] in OPERATIONS


def test_random_grammar_pure_primitives_valid():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["primitive"] in PRIMITIVES


def test_random_grammar_pure_smooth_radius_non_negative():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["smooth_radius"] >= 0.0


def test_random_grammar_pure_distance_factor_positive():
    for _ in range(30):
        g = random_grammar_pure()
        for it in g["iterations"]:
            assert it["distance_factor"] > 0.0


# ── additional mutate ─────────────────────────────────────────────────────────

def test_mutate_high_rate_changes_something():
    import random as _random
    _random.seed(42)
    g = _base_grammar()
    changed = False
    for _ in range(20):
        g2 = mutate(g, rate=1.0)
        if (g2["symmetry_group"] != g["symmetry_group"] or
                g2["seed"]["type"] != g["seed"]["type"] or
                g2["iterations"][0]["operation"] != g["iterations"][0]["operation"]):
            changed = True
            break
    assert changed, "rate=1.0 should change at least one field across 20 tries"


def test_mutate_first_step_stays_valid():
    for _ in range(30):
        g = _base_grammar()
        g2 = mutate(g, rate=1.0)
        assert g2["iterations"][0]["operation"] in OPERATIONS


# ── additional crossover ──────────────────────────────────────────────────────

def test_crossover_symmetry_from_parents():
    a = _base_grammar()
    b = {**_base_grammar(), "symmetry_group": "octahedral"}
    b["iterations"].append({"operation": "add", "primitive": "cube",
                             "scale_factor": 0.4, "distance_factor": 1.0,
                             "smooth_radius": 0.01, "apply_to": "new"})
    parent_syms = {a["symmetry_group"], b["symmetry_group"]}
    for _ in range(10):
        ca, cb = crossover(a, b)
        assert ca["symmetry_group"] in parent_syms
        assert cb["symmetry_group"] in parent_syms


def test_crossover_children_valid_operations():
    a = _base_grammar()
    b = {**_base_grammar()}
    b["iterations"] = [{"operation": "intersect", "primitive": "octahedron",
                         "scale_factor": 0.3, "distance_factor": 0.9,
                         "smooth_radius": 0.0, "apply_to": "new"}]
    for _ in range(10):
        ca, cb = crossover(a, b)
        for it in ca["iterations"] + cb["iterations"]:
            assert it["operation"] in OPERATIONS


# ── additional diverse_population ─────────────────────────────────────────────

def test_diverse_population_all_valid_structure():
    pop = diverse_population(24)
    for g in pop:
        assert "seed" in g
        assert "symmetry_group" in g
        assert "iterations" in g
        assert len(g["iterations"]) >= 1
        assert g["seed"]["type"] in PRIMITIVES
        assert g["symmetry_group"] in SYMMETRIES


def test_diverse_population_no_empty_iterations():
    pop = diverse_population(24)
    for g in pop:
        assert len(g["iterations"]) >= 1
