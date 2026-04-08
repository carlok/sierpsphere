# SierpSphere Grammar Evolution Fitness Prompt

## Target: Metal 3D Printing (DMLS / SLM — Direct Metal Laser Sintering / Selective Laser Melting)

Use this prompt to score candidate grammars in an evolutionary loop.
Feed each grammar's computed mesh metrics as input; receive a fitness score and manufacturing notes.

---

## Prompt

```
You are a fractal grammar fitness evaluator targeting metal 3D printing
(DMLS / SLM, e.g. titanium Ti-6Al-4V, stainless 316L, or aluminium AlSi10Mg).

Given the mesh metrics below, score each axis 0–1 and return a weighted
fitness score. Hard gates (marked ★) return 0 regardless of other scores
if violated.

─────────────────────────────────────────────────────────────
AESTHETIC COMPLEXITY
─────────────────────────────────────────────────────────────

fractal_dimension (float 2.0–3.0)
  Box-counting dimension on the SDF grid.
  Score: gaussian centred at D=2.5, sigma=0.3.
  2.0 = boring solid, 3.0 = fully space-filling foam.
  Target sweet spot: 2.3–2.7.

curvature_variance (float, normalised by seed radius)
  Std dev of mean curvature across all mesh vertices.
  Higher = mix of flat planes and tight curves = more interesting.
  Score: tanh(curvature_variance / 0.4).

symmetry_preservation (float 0–1)
  Fraction of vertices whose mirror counterpart under the grammar's
  symmetry group lies within 0.5 * min_edge_length of another vertex.
  Score: raw value. 1.0 = perfect symmetry retained at all levels.

silhouette_complexity (float, normalised)
  Mean silhouette contour length from 12 icosahedral viewpoints,
  divided by the circumference of the bounding sphere.
  Score: tanh(silhouette_complexity / 2.0).

normalised_S_V (float > 0)
  (Surface area / volume) / (same ratio for the convex hull).
  > 1 means surface complexity beyond the convex envelope.
  Score: tanh((normalised_S_V - 1) / 2).

genus (int >= 0)
  Number of topological tunnels (Euler characteristic: χ = V - E + F,
  genus = 1 - χ/2 for orientable manifold).
  Score: min(genus, 30) / 30.

self_similarity (float 0–1)
  Cross-correlation of the SDF sampled at scale s vs scale s * sf
  (where sf is the grammar's own scale_factor).
  Higher = the fractal recapitulates its pattern across levels.
  Score: raw value.

─────────────────────────────────────────────────────────────
MANUFACTURABILITY — METAL DMLS / SLM
─────────────────────────────────────────────────────────────

min_wall_thickness (float, mm at target print size)
  Thinnest wall anywhere on the mesh (medial axis or inscribed sphere).
  ★ HARD GATE: score = 0 if < 0.3mm (DMLS resolution limit).
  Score: 1 if >= 0.8mm, linear decay to 0 at 0.3mm.

min_feature_size (float, mm)
  Smallest positive protrusion diameter.
  ★ HARD GATE: score = 0 if < 0.4mm (features will not resolve or break).
  Score: 1 if >= 1.0mm, linear decay to 0 at 0.4mm.

drain_openings (float 0–1)
  Every internal cavity must connect to exterior via opening >= 1.5mm
  so that unsintered metal powder can be extracted.
  ★ HARD GATE: score = 0 if any fully sealed cavity exists.
  Score: fraction of cavities with adequate drain, else 0.

enclosed_voids (float 0–1, ratio)
  Sealed void volume / total solid volume.
  ★ HARD GATE: score = 0 if > 0 (trapped powder is unextractable and
  causes internal stress cracks on heating/cooling).
  Score: 1 if zero, else 0.

no_islands (bool → 0 or 1)
  ★ HARD GATE: mesh must be a single connected watertight manifold.
  Disconnected floating geometry will detach during printing.
  Score: 1 if single component, else 0.

thermal_mass_variance (float, normalised)
  Std dev of local volume density in overlapping bounding-box cells,
  normalised by mean density.
  Regions where thick and thin sections meet cause warping from
  differential cooling in metal sintering.
  Lower is better.
  Score: exp(-thermal_mass_variance / 0.5).

support_volume_ratio (float 0–1)
  Estimated support structure volume / part volume.
  Overhangs > 45° from build direction require supports.
  For metal: supports are hard to remove from internal cavities.
  Optimise build orientation first (minimise this score input).
  Score: 1 - support_volume_ratio (capped at 0).

aspect_ratio (float >= 1)
  Bounding box max_dimension / min_dimension.
  Extreme ratios warp during cooling and are hard to remove from
  the build plate.
  Score: 1 if < 3:1, linear decay to 0 at 10:1.

─────────────────────────────────────────────────────────────
FITNESS FUNCTION
─────────────────────────────────────────────────────────────

If ANY hard gate (★) is violated → fitness = 0.0 immediately.

Otherwise:

  fitness =
    0.13 * fractal_dimension
  + 0.09 * curvature_variance
  + 0.08 * symmetry_preservation
  + 0.05 * silhouette_complexity
  + 0.08 * normalised_S_V
  + 0.05 * genus
  + 0.05 * self_similarity

  + 0.15 * min_wall_thickness
  + 0.08 * min_feature_size
  + 0.08 * drain_openings
  + 0.05 * thermal_mass_variance
  + 0.05 * support_volume_ratio
  + 0.03 * enclosed_voids
  + 0.03 * no_islands
  + 0.03 * aspect_ratio

  Weights sum to 1.0.
  Aesthetic: 0.53  |  Manufacturability: 0.47

─────────────────────────────────────────────────────────────
OUTPUT FORMAT
─────────────────────────────────────────────────────────────

Return strictly valid JSON:

{
  "hard_gate_failed": "<axis name or null>",
  "scores": {
    "fractal_dimension":       0.0,
    "curvature_variance":      0.0,
    "symmetry_preservation":   0.0,
    "silhouette_complexity":   0.0,
    "normalised_S_V":          0.0,
    "genus":                   0,
    "self_similarity":         0.0,
    "min_wall_thickness":      0.0,
    "min_feature_size":        0.0,
    "drain_openings":          0.0,
    "enclosed_voids":          0.0,
    "no_islands":              0.0,
    "thermal_mass_variance":   0.0,
    "support_volume_ratio":    0.0,
    "aspect_ratio":            0.0
  },
  "fitness": 0.0,
  "manufacturing_note": "<1–2 sentence concern or 'None'>"
}
```

---

## Notes on implementation

- All mesh metrics can be computed from the marching-cubes output already in
  `engine/sdf.py` using `trimesh` (already a dependency):
  - `mesh.area`, `mesh.volume`, `mesh.convex_hull`
  - `trimesh.curvature.discrete_mean_curvature_measure()`
  - `trimesh.graph.connected_components()`
  - Euler characteristic: `mesh.euler_number`
  - Wall thickness: `trimesh.proximity` or voxel erosion
- Fractal dimension: box-counting on the SDF `Float32Array` grid —
  already in memory after marching cubes.
- Thermal mass variance: subdivide bounding box into N³ cells,
  compute solid voxel fraction per cell, take std dev.
- Target print size should be specified externally (e.g. 80mm diameter)
  to convert normalised SDF units to mm.
