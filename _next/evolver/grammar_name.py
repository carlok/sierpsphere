"""
Compact name/slug encoding for G-grammar grammars.

The symmetry group is implied by the seed type (bijection) so it is NOT
encoded separately. fd_u/fd_v replace distance_factor.

Display name:  T.-t4u30v10 +c0u50v20    (human-readable)
Filename slug:  T.Nt4u30v10Pc0u50v20    (POSIX-safe: [A-Za-z0-9._-])

Encoding conventions:
  Seed (= group):  tetrahedron→T  cube→C  icosahedron→I
  Op (display):    subtract→-    add→+   intersect→x
  Op (slug):       subtract→N    add→P   intersect→X
  Primitive:       tetrahedron→t  cube→c  icosahedron→i  sphere→s
  smooth_radius:   integer units of 0.005  (0.02→4, 0.01→2, 0.0→0)
  fd_u, fd_v:      two-digit integer ×100  (0.30→u30, 0.10→v10)
  scale_factor:    omit when 0.30 (default); else k+two-digit int×100  (0.45→k45)
  distance:        omit when 0.70 (default); else d+two-digit int×100  (0.85→d85)
"""
from __future__ import annotations

_SEEDS = {"tetrahedron": "T", "cube": "C", "icosahedron": "I"}
_OPS_D = {"subtract": "-", "add": "+", "intersect": "x"}
_OPS_S = {"subtract": "N", "add": "P",  "intersect": "X"}
_PRIMS = {"tetrahedron": "t", "cube": "c", "icosahedron": "i", "sphere": "s"}

_DEFAULT_SCALE    = 0.30
_DEFAULT_DISTANCE = 0.70


def _encode_step_display(it: dict) -> str:
    op    = _OPS_D.get(it.get("operation", "subtract"), "-")
    prim  = _PRIMS.get(it.get("primitive", "sphere"), "s")
    rho   = int(round(it.get("smooth_radius", 0.0) / 0.005))
    u     = int(round(it.get("fd_u", 0.3) * 100))
    v     = int(round(it.get("fd_v", 0.1) * 100))
    scale = it.get("scale_factor", _DEFAULT_SCALE)
    dist  = it.get("distance", _DEFAULT_DISTANCE)

    token = f"{op}{prim}{rho}u{u:02d}v{v:02d}"
    if abs(scale - _DEFAULT_SCALE) > 0.005:
        token += f"k{int(round(scale * 100)):02d}"
    if abs(dist - _DEFAULT_DISTANCE) > 0.005:
        token += f"d{int(round(dist * 100)):02d}"
    return token


def _encode_step_slug(it: dict) -> str:
    op    = _OPS_S.get(it.get("operation", "subtract"), "N")
    prim  = _PRIMS.get(it.get("primitive", "sphere"), "s")
    rho   = int(round(it.get("smooth_radius", 0.0) / 0.005))
    u     = int(round(it.get("fd_u", 0.3) * 100))
    v     = int(round(it.get("fd_v", 0.1) * 100))
    scale = it.get("scale_factor", _DEFAULT_SCALE)
    dist  = it.get("distance", _DEFAULT_DISTANCE)

    token = f"{op}{prim}{rho}u{u:02d}v{v:02d}"
    if abs(scale - _DEFAULT_SCALE) > 0.005:
        token += f"k{int(round(scale * 100)):02d}"
    if abs(dist - _DEFAULT_DISTANCE) > 0.005:
        token += f"d{int(round(dist * 100)):02d}"
    return token


def grammar_name(grammar: dict) -> str:
    """Human-readable one-line name, e.g. `T.-t4u30v10 +c0u50v20`."""
    seed  = _SEEDS.get(grammar.get("seed", {}).get("type", "cube"), "C")
    steps = " ".join(_encode_step_display(it) for it in grammar.get("iterations", []))
    return f"{seed}.{steps}"


def grammar_slug(grammar: dict) -> str:
    """POSIX-safe filename slug, e.g. `T.Nt4u30v10Pc0u50v20`."""
    seed  = _SEEDS.get(grammar.get("seed", {}).get("type", "cube"), "C")
    steps = "".join(_encode_step_slug(it) for it in grammar.get("iterations", []))
    return f"{seed}.{steps}"
