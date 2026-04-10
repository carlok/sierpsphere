"""
Grammar mutation and crossover operators for the evolutionary loop.
All functions are pure: they return new grammar dicts, never modify in-place.
"""
from __future__ import annotations
import copy
import random
import math

OPERATIONS  = ["subtract", "add", "intersect"]
PRIMITIVES  = ["sphere", "cube", "octahedron"]
SYMMETRIES  = ["tetrahedral", "octahedral", "icosahedral"]
# Icosahedral is expensive — lower probability
SYM_WEIGHTS = [0.50, 0.35, 0.15]


def mutate(grammar: dict, rate: float = 0.25) -> dict:
    """Return a mutated copy. Each mutable field flips with probability `rate`."""
    g = copy.deepcopy(grammar)

    # Symmetry group (low probability — big structural change)
    if random.random() < rate * 0.3:
        g["symmetry_group"] = random.choices(SYMMETRIES, weights=SYM_WEIGHTS)[0]

    iters = g.get("iterations", [])

    # Per-step mutations
    for it in iters:
        if random.random() < rate:
            it["scale_factor"] = _jitter(it["scale_factor"], 0.12, 0.15, 0.65)
        if random.random() < rate:
            it["distance_factor"] = _jitter(it.get("distance_factor", 1.0), 0.10, 0.5, 1.5)
        if random.random() < rate:
            it["smooth_radius"] = _jitter(it.get("smooth_radius", 0.02), 0.30, 0.0, 0.15)
        if random.random() < rate * 0.5:
            it["operation"] = random.choice(OPERATIONS)
        if random.random() < rate * 0.4:
            it["primitive"] = random.choice(PRIMITIVES)

    # Add a step
    if random.random() < rate * 0.3 and len(iters) < 4:
        template = copy.deepcopy(random.choice(iters)) if iters else _default_step()
        template["operation"] = random.choice(OPERATIONS)
        template["scale_factor"] = random.uniform(0.3, 0.55)
        iters.append(template)

    # Remove a step
    if random.random() < rate * 0.3 and len(iters) > 1:
        iters.pop(random.randrange(len(iters)))

    g["iterations"] = iters
    return g


def crossover(parent_a: dict, parent_b: dict) -> tuple[dict, dict]:
    """Single-point crossover on the iteration list. Returns two children."""
    a = copy.deepcopy(parent_a)
    b = copy.deepcopy(parent_b)

    steps_a = a.get("iterations", [])
    steps_b = b.get("iterations", [])

    if not steps_a or not steps_b:
        return a, b

    cut_a = random.randint(1, max(1, len(steps_a) - 1))
    cut_b = random.randint(1, max(1, len(steps_b) - 1))

    child_a_steps = steps_a[:cut_a] + steps_b[cut_b:]
    child_b_steps = steps_b[:cut_b] + steps_a[cut_a:]

    a["iterations"] = child_a_steps or steps_a
    b["iterations"] = child_b_steps or steps_b

    # Children inherit symmetry randomly from either parent
    if random.random() < 0.5:
        a["symmetry_group"] = parent_b.get("symmetry_group", "tetrahedral")
    if random.random() < 0.5:
        b["symmetry_group"] = parent_a.get("symmetry_group", "tetrahedral")

    return a, b


def random_grammar(seed_grammars: list[dict]) -> dict:
    """Random grammar seeded from an existing one with heavy mutation."""
    base = copy.deepcopy(random.choice(seed_grammars))
    return mutate(base, rate=0.6)


def tournament_select(population: list[dict], fitnesses: list[float], k: int = 4) -> dict:
    """Tournament selection: pick k individuals, return the fittest."""
    contestants = random.sample(list(zip(population, fitnesses)), min(k, len(population)))
    return max(contestants, key=lambda x: x[1])[0]


# ── Internals ─────────────────────────────────────────────────────────────

def _jitter(value: float, rel: float, lo: float, hi: float) -> float:
    """Multiplicative jitter, clamped to [lo, hi]."""
    delta = value * rel * random.gauss(0, 1)
    return float(max(lo, min(hi, value + delta)))


def _default_step() -> dict:
    return {
        "operation": "subtract",
        "primitive": "sphere",
        "scale_factor": 0.5,
        "distance_factor": 1.0,
        "smooth_radius": 0.02,
        "apply_to": "new",
    }
