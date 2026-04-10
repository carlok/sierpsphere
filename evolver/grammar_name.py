"""
Compact name/slug encoding for SierpSphere grammars.

Display name:   Td.S.-s4 +s2 -s1          (human-readable)
Filename slug:  Td.S.Ns4Ps2Ns1             (POSIX safe: [A-Za-z0-9._-])

Encoding conventions:
  Group:    tetrahedral → Td   octahedral → Oh   icosahedral → Ih
  Seed:     sphere → S   cube → C   octahedron → O
  Op (display):  subtract → -   add → +   intersect → x
  Op (slug):     subtract → N   add → P   intersect → X
  Primitive:     sphere → s   cube → c   octahedron → o
  smooth_radius: integer units of 0.005  (0.02→4, 0.01→2, 0.005→1, 0→0)
  scale_factor:  omit when 0.50; else two-digit integer ×100
                 display `:47`   slug `k47`
  distance_factor: omit when 1.00; else three-digit integer ×100
                 display `@1.1`  slug `d110`
"""
from __future__ import annotations

_GROUPS = {"tetrahedral": "Td", "octahedral": "Oh", "icosahedral": "Ih"}
_SEEDS  = {"sphere": "S", "cube": "C", "octahedron": "O"}
_OPS_D  = {"subtract": "-", "add": "+", "intersect": "x"}   # display
_OPS_S  = {"subtract": "N", "add": "P", "intersect": "X"}   # slug
_PRIMS  = {"sphere": "s", "cube": "c", "octahedron": "o"}


def _encode_step_display(it: dict) -> str:
    op    = _OPS_D.get(it.get("operation", "subtract"), "-")
    prim  = _PRIMS.get(it.get("primitive", "sphere"), "s")
    rho   = int(round(it.get("smooth_radius", 0.0) / 0.005))
    sigma = int(round(it.get("scale_factor", 0.5) * 100))
    delta = it.get("distance_factor", 1.0)

    token = f"{op}{prim}{rho}"
    if sigma != 50:
        token += f":{sigma}"
    if abs(delta - 1.0) > 0.005:
        token += f"@{delta:.2g}"
    return token


def _encode_step_slug(it: dict) -> str:
    op    = _OPS_S.get(it.get("operation", "subtract"), "N")
    prim  = _PRIMS.get(it.get("primitive", "sphere"), "s")
    rho   = int(round(it.get("smooth_radius", 0.0) / 0.005))
    sigma = int(round(it.get("scale_factor", 0.5) * 100))
    delta = it.get("distance_factor", 1.0)

    token = f"{op}{prim}{rho}"
    if sigma != 50:
        token += f"k{sigma}"
    if abs(delta - 1.0) > 0.005:
        token += f"d{int(round(delta * 100))}"
    return token


def grammar_name(grammar: dict) -> str:
    """Human-readable one-line name, e.g. `Td.S.-s4 +s2 -s1`."""
    group = _GROUPS.get(grammar.get("symmetry_group", "tetrahedral"), "Td")
    seed  = _SEEDS.get(grammar.get("seed", {}).get("type", "sphere"), "S")
    steps = " ".join(_encode_step_display(it) for it in grammar.get("iterations", []))
    return f"{group}.{seed}.{steps}"


def grammar_slug(grammar: dict) -> str:
    """POSIX-safe filename slug, e.g. `Td.S.Ns4Ps2Ns1`."""
    group = _GROUPS.get(grammar.get("symmetry_group", "tetrahedral"), "Td")
    seed  = _SEEDS.get(grammar.get("seed", {}).get("type", "sphere"), "S")
    steps = "".join(_encode_step_slug(it) for it in grammar.get("iterations", []))
    return f"{group}.{seed}.{steps}"
