"""Grammar storage utilities for preset discovery and loading."""

from __future__ import annotations

import json
from pathlib import Path


def list_grammar_names(grammar_dir: Path) -> list[str]:
    """Return sorted preset names from the grammar directory."""
    return sorted(p.stem for p in grammar_dir.glob("*.json") if p.stem != "schema")


def load_grammar(grammar_dir: Path, name: str) -> dict:
    """Load a grammar by name from `<grammar_dir>/<name>.json`."""
    path = grammar_dir / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Grammar '{name}' not found")
    return json.loads(path.read_text())
