# g-sdf-evolver

A genetic evolver that generates 3D shapes defined by **G-invariant Signed Distance Functions**, optimised for DMLS/SLM metal 3D printing.

Mathematical foundation: [`foundation.tex`](foundation.tex)

---

## Core idea

Every shape in the population is a **G-invariant SDF** — satisfying f(g·x) = f(x) for all g ∈ G. This is enforced structurally by the grammar, not measured post-hoc.

The three symmetry groups correspond to the Platonic solids (finite irreducible subgroups of O(3)):

| Seed | Group | Order |
|------|-------|-------|
| tetrahedron | Td | 24 |
| cube | Oh | 48 |
| icosahedron | Ih | 120 |

Each shape is a **G-grammar**: a seed primitive (the initial G-invariant SDF) followed by a sequence of Boolean operations, each carving or adding a G-orbit of child primitives placed inside the fundamental domain FD(G).

---

## Structure

```
_next/
├── evolver/
│   ├── sdf_metal.py        # Metal/MPS SDF evaluator (PyTorch, Apple Silicon)
│   ├── mutate.py           # Mutation, crossover, tournament selection
│   ├── fitness.py          # DMLS/SLM fitness metrics (15 sub-scores)
│   ├── grammar_name.py     # Human-readable names and POSIX-safe slugs
│   ├── evolver_native.py   # GA main loop (CLI)
│   ├── config.json         # Population size, eval resolution, weights
│   └── tests/              # 105 pytest tests
│       ├── test_mutate.py
│       ├── test_grammar_name.py
│       └── test_fitness.py
├── engine/
│   └── sdf.py              # NumPy SDF evaluator (CPU, server-side mesh export)
├── foundation.tex          # Formal mathematical specification
├── PLAN.md                 # Step-by-step build plan
├── PROMPT.txt              # Bootstrap prompt for new sessions
├── SALVAGE.txt             # What was kept/discarded from the predecessor repo
└── NAMES.txt               # Project name candidates
```

---

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install torch trimesh scipy scikit-image numpy pytest
```

## Run

```bash
cd evolver
python evolver_native.py --epochs 10 --workers 8
python evolver_native.py --resume --epochs 10
```

## Test

```bash
cd evolver
python -m pytest tests/ -q
```

---

## Grammar encoding

A grammar is a JSON dict:

```json
{
  "seed": {"type": "cube", "radius": 1.0},
  "iterations": [
    {"operation": "subtract", "primitive": "sphere",
     "fd_u": 0.3, "fd_v": 0.1,
     "distance": 0.7, "scale_factor": 0.3, "smooth_radius": 0.02}
  ]
}
```

`fd_u`, `fd_v` are barycentric coordinates in FD(G) — the irreducible spherical triangle for the group derived from the seed. `symmetry_group` is never stored; it is always derived from `seed.type`.

**Name format:** `C.-s9u63v35k24d97 +i2u74v20` — seed char, op, primitive, smooth×0.005, u×100, v×100, optional scale (k) and distance (d) when non-default.

---

## Fitness

15 weighted sub-scores, all in [0, 1]. Hard gates (non-watertight, islands, thin walls) return fitness 0.

Key weights: `min_wall_thickness` 0.15 · `fractal_dimension` 0.16 · `curvature_variance` 0.12 · `normalised_S_V` 0.08.

G-invariance is **structural** (enforced by grammar construction), not a fitness metric.
