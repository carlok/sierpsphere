# platosdf

![](aaa.jpg)

A genetic evolver that generates 3D shapes defined by **G-invariant Signed Distance Functions**, optimised for DMLS/SLM metal 3D printing.

**Repository:** [github.com/carlok/platosdf](https://github.com/carlok/platosdf)

Mathematical foundation: [`foundation.tex`](foundation.tex) · formal notes: [`tex/g_carving_grammars.tex`](tex/g_carving_grammars.tex)

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
platosdf/
├── evolver/
│   ├── sdf_metal.py        # Metal/MPS SDF evaluator (PyTorch, Apple Silicon)
│   ├── mutate.py           # Mutation, crossover, tournament selection
│   ├── fitness.py          # DMLS/SLM fitness metrics (15 sub-scores)
│   ├── grammar_name.py     # Human-readable names and POSIX-safe slugs
│   ├── evolver_native.py   # GA main loop (CLI)
│   ├── config.json         # Population size, eval resolution, weights
│   └── tests/              # pytest suite
│       ├── test_mutate.py
│       ├── test_grammar_name.py
│       └── test_fitness.py
├── engine/
│   └── sdf.py              # NumPy SDF evaluator (CPU, server-side mesh export)
├── glb-viewer/
│   ├── index.html          # Three.js GLB viewer with material/light panel
│   └── serve.py            # Local HTTP server
├── tex/
│   └── g_carving_grammars.tex  # Small theorems on G-carving grammars
├── foundation.tex          # Formal mathematical specification
├── PLAN.md                 # Step-by-step build plan
└── PROMPT.txt              # Bootstrap prompt for new sessions
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

Output is written to `gallery/` (relative to `evolver/`):

```
gallery/
  epoch_0001/
    rank_01_<slug>.glb          # top-k 3D meshes (binary glTF)
    rank_01_<slug>_grammar.json
    overview.glb                # all top-k side by side
    fitness_log.json
  manifest.json                 # cross-epoch summary
  population.json               # last population (used by --resume)
```

### GLB viewer

```bash
python glb-viewer/serve.py   # → http://localhost:5000
```

Drag-and-drop any `.glb` from the gallery. Panel controls: material presets, metalness/roughness sliders, IBL environment, light intensities, turntable.

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

---

## Implementation notes

**Carving-only grammar** — `OPERATIONS = ["subtract", "intersect"]`. The `add` (union) operation was removed because orbit copies placed near the seed surface protrude as peninsulas. Carving-only is also physically correct for metal printing: you begin with a solid and remove material.

**Mesh cleaning** — `extract_mesh_metal` always returns the single largest connected component, at both eval and save resolution. Fitness gating and GLB export therefore always see the same topology. Only viable individuals (fitness > 0) get a `.glb` and `_grammar.json` saved.

**Marching cubes level=0.01** — slight erosion (~0.8mm at 80mm print scale) removes necks thinner than ~1.6mm before they can appear as peninsulas in the GLB.

**Distance capped at 1.0** — orbit copies placed at `distance > seed_radius` graze the surface from outside, creating thin fingers via subtract/intersect. Hard cap at 1.0 everywhere (generation, mutation, jitter).

**Crossover step cap** — crossover is capped at 5 iterations per child. Without the cap, repeated crossover produces grammars with 10–15+ steps and degenerate geometry.

**Tetrahedral group generators** — Td requires three generators: C3([1,1,1]), C2([1,0,0]), σ_d([1,-1,0]). Using only C3+σ_d yields S3 (order 6) instead of Td (order 24).

**Diversity** — pop=36, mutation_rate=0.65, fd Gaussian σ=0.22, tournament_k=3, ~12% fresh random individuals injected each epoch.
