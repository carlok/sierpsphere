"""
Grammar mutation and crossover operators for the G-invariant evolutionary loop.
All functions are pure: they return new grammar dicts, never modify in-place.

Grammar schema:
  seed:       {type: tetrahedron|cube|icosahedron, radius: float}
  iterations: [{operation, primitive, fd_u, fd_v, distance,
                scale_factor, smooth_radius}]
  symmetry_group is NOT stored — derived from seed.type via SEED_TO_GROUP.
"""
from __future__ import annotations
import copy
import random

# ── Constants ─────────────────────────────────────────────────────────────────

# Seeds: one per finite subgroup of O(3) — bijection with symmetry groups
PRIMITIVES = ["tetrahedron", "cube", "icosahedron"]

# Valid child primitives (sphere included as a "smooth" child option)
CHILD_PRIMITIVES = ["tetrahedron", "cube", "icosahedron", "sphere"]

OPERATIONS = ["subtract", "add", "intersect"]

SEED_TO_GROUP = {
    "tetrahedron": "tetrahedral",
    "cube":        "octahedral",
    "icosahedron": "icosahedral",
}


# ── Random grammar ─────────────────────────────────────────────────────────────

def random_grammar_pure(
    n_steps: int | None = None,
    seed_type: str | None = None,
) -> dict:
    """
    Fully random G-grammar — no seed files involved.
    `seed_type` pins the seed primitive (used by diverse_population).
    First step always carves (subtract/intersect) to avoid solid-blob failures.
    fd_u + fd_v ≤ 1 invariant enforced by _random_fd().
    """
    if n_steps is None:
        n_steps = random.randint(1, 4)
    seed_prim = seed_type or random.choice(PRIMITIVES)

    steps = []
    for i in range(n_steps):
        op = random.choice(["subtract", "intersect"]) if i == 0 else random.choice(OPERATIONS)
        u, v = _random_fd()
        steps.append({
            "operation":     op,
            "primitive":     random.choice(CHILD_PRIMITIVES),
            "fd_u":          round(u, 4),
            "fd_v":          round(v, 4),
            "distance":      round(random.uniform(0.5, 1.1), 3),
            "scale_factor":  round(random.uniform(0.2, 0.55), 3),
            "smooth_radius": round(random.uniform(0.0, 0.06), 4),
        })

    return {
        "seed":       {"type": seed_prim, "radius": 1.0},
        "iterations": steps,
    }


def diverse_population(pop_size: int) -> list[dict]:
    """
    Equal thirds across {tetrahedron, cube, icosahedron} seeds.
    Varied step counts (1–4). Never loaded from saved JSON.
    """
    population = []
    per_type = pop_size // len(PRIMITIVES)
    for prim in PRIMITIVES:
        for _ in range(per_type):
            population.append(random_grammar_pure(
                n_steps=random.randint(1, 4), seed_type=prim
            ))
    while len(population) < pop_size:
        population.append(random_grammar_pure())
    random.shuffle(population)
    return population


# ── Mutation ───────────────────────────────────────────────────────────────────

def mutate(grammar: dict, rate: float = 0.55) -> dict:
    """
    Return a mutated copy. Each gene mutates independently with probability
    proportional to `rate`.

    Seed type mutates at rate×0.15 — changing it changes G, so all fd_u/fd_v
    are resampled in the new fundamental domain (different spherical triangle).
    fd_u + fd_v ≤ 1 invariant always maintained.
    """
    g = copy.deepcopy(grammar)

    # Seed type — low probability, structural change
    if random.random() < rate * 0.15:
        new_seed = random.choice(PRIMITIVES)
        g["seed"]["type"] = new_seed
        # Resample all fd coordinates — FD(G) changes with G
        for it in g.get("iterations", []):
            u, v = _random_fd()
            it["fd_u"] = round(u, 4)
            it["fd_v"] = round(v, 4)

    for it in g.get("iterations", []):
        # fd_u / fd_v — perturb with Gaussian, maintain u+v≤1
        if random.random() < rate:
            u = it.get("fd_u", 0.3)
            v = it.get("fd_v", 0.1)
            u = float(max(0.0, min(1.0, u + random.gauss(0, 0.15))))
            v = float(max(0.0, min(1.0, v + random.gauss(0, 0.15))))
            if u + v > 1.0:
                total = u + v
                u, v = u / total, v / total
            it["fd_u"] = round(u, 4)
            it["fd_v"] = round(v, 4)

        if random.random() < rate:
            it["distance"] = _jitter(it.get("distance", 0.7), 0.15, 0.3, 1.4)
        if random.random() < rate:
            it["scale_factor"] = _jitter(it.get("scale_factor", 0.3), 0.12, 0.1, 0.65)
        if random.random() < rate:
            it["smooth_radius"] = _jitter(it.get("smooth_radius", 0.02), 0.30, 0.0, 0.15)
        if random.random() < rate * 0.5:
            it["operation"] = random.choice(OPERATIONS)
        if random.random() < rate * 0.4:
            it["primitive"] = random.choice(CHILD_PRIMITIVES)

    iters = g.get("iterations", [])

    # Add a step
    if random.random() < rate * 0.3 and len(iters) < 5:
        u, v = _random_fd()
        iters.append({
            "operation":     random.choice(OPERATIONS),
            "primitive":     random.choice(CHILD_PRIMITIVES),
            "fd_u":          round(u, 4),
            "fd_v":          round(v, 4),
            "distance":      round(random.uniform(0.5, 1.1), 3),
            "scale_factor":  round(random.uniform(0.2, 0.55), 3),
            "smooth_radius": round(random.uniform(0.0, 0.06), 4),
        })

    # Remove a step
    if random.random() < rate * 0.3 and len(iters) > 1:
        iters.pop(random.randrange(len(iters)))

    g["iterations"] = iters
    return g


# ── Crossover ──────────────────────────────────────────────────────────────────

def crossover(parent_a: dict, parent_b: dict) -> tuple[dict, dict]:
    """
    Relaxed group-coherent crossover (foundation.tex §4.2):
      - Each child inherits seed (→ group G) from one parent.
      - Operations borrowed freely from either parent's iteration list.
      - If the inherited G differs from the donor's G, fd_u/fd_v of
        borrowed steps are resampled uniformly in the new FD (FD topology
        changes between groups — old coordinates may not map coherently).
    """
    a = copy.deepcopy(parent_a)
    b = copy.deepcopy(parent_b)

    # Each child gets its seed from a designated parent
    # child_a inherits from parent_a's seed, child_b from parent_b's
    group_a = SEED_TO_GROUP.get(a["seed"]["type"], "octahedral")
    group_b = SEED_TO_GROUP.get(b["seed"]["type"], "octahedral")

    steps_a = parent_a.get("iterations", [])
    steps_b = parent_b.get("iterations", [])

    if not steps_a or not steps_b:
        return a, b

    # Single-point crossover on merged step pool
    cut_a = random.randint(1, max(1, len(steps_a)))
    cut_b = random.randint(0, max(0, len(steps_b) - 1))

    # child_a: steps from parent_a[:cut] + parent_b[cut:]
    raw_a = steps_a[:cut_a] + steps_b[cut_b:]
    # child_b: steps from parent_b[:cut] + parent_a[cut:]
    raw_b = steps_b[:cut_b] + steps_a[cut_a:]

    MAX = 5
    a["iterations"] = (_fix_fd(raw_a, group_a, donor_group=group_b, cut=cut_a) or steps_a)[:MAX]
    b["iterations"] = (_fix_fd(raw_b, group_b, donor_group=group_a, cut=cut_b) or steps_b)[:MAX]

    return a, b


def tournament_select(
    population: list[dict], fitnesses: list[float], k: int = 2
) -> dict:
    """Tournament selection. k=2 keeps selection pressure weak (preserves diversity)."""
    contestants = random.sample(list(zip(population, fitnesses)), min(k, len(population)))
    return max(contestants, key=lambda x: x[1])[0]


# ── Internals ──────────────────────────────────────────────────────────────────

def _random_fd() -> tuple[float, float]:
    """Sample (u, v) uniformly in the valid barycentric region u+v≤1."""
    u = random.random()
    v = random.uniform(0, 1 - u)
    return u, v


def _jitter(value: float, rel: float, lo: float, hi: float) -> float:
    """Gaussian multiplicative jitter, clamped to [lo, hi]."""
    delta = value * rel * random.gauss(0, 1)
    return round(float(max(lo, min(hi, value + delta))), 4)


def _fix_fd(
    steps: list[dict],
    child_group: str,
    donor_group: str,
    cut: int,
) -> list[dict]:
    """
    Resample fd_u/fd_v for steps borrowed from a different group's parent.
    Steps before `cut` are from child's own group — leave untouched.
    Steps from `cut` onward are from donor; resample if groups differ.
    """
    if child_group == donor_group:
        return copy.deepcopy(steps)
    result = []
    for i, it in enumerate(steps):
        s = copy.deepcopy(it)
        if i >= cut:
            u, v = _random_fd()
            s["fd_u"] = round(u, 4)
            s["fd_v"] = round(v, 4)
        result.append(s)
    return result
