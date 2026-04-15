"""Tests for STL / GLB export in save_epoch."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Make sure evolver/ is importable when run from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))


def _minimal_cfg(gallery_dir: str) -> dict:
    return {
        "gallery_dir": gallery_dir,
        "save_top_k": 1,
        "save_resolution": 20,
        "eval_resolution": 20,
        "bounds": 1.8,
        "target_mm": 80.0,
    }


def _minimal_grammar() -> dict:
    return {
        "seed": {"type": "cube", "radius": 1.0},
        "iterations": [],
    }


def _viable_result() -> dict:
    return {
        "fitness": 0.42,
        "hard_gate_failed": None,
        "scores": {"fractal_dimension": 0.5},
        "manufacturing_note": "",
    }


# ── GLB always written ────────────────────────────────────────────────────────

def test_glb_written_by_default():
    from evolver_native import save_epoch
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _minimal_cfg(tmp)
        pop = [_minimal_grammar()]
        res = [_viable_result()]
        save_epoch(1, pop, res, cfg, elapsed=0.1, export_stl=False)
        glbs = list(Path(tmp).rglob("*.glb"))
        # overview.glb + rank_01*.glb
        assert any("rank_01" in g.name for g in glbs), "rank_01 GLB not written"


# ── STL written only with export_stl=True ────────────────────────────────────

def test_stl_not_written_by_default():
    from evolver_native import save_epoch
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _minimal_cfg(tmp)
        pop = [_minimal_grammar()]
        res = [_viable_result()]
        save_epoch(1, pop, res, cfg, elapsed=0.1, export_stl=False)
        assert list(Path(tmp).rglob("*.stl")) == [], "STL should not be written without --export-stl"


def test_stl_written_when_flag_set():
    from evolver_native import save_epoch
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _minimal_cfg(tmp)
        pop = [_minimal_grammar()]
        res = [_viable_result()]
        save_epoch(1, pop, res, cfg, elapsed=0.1, export_stl=True)
        stls = list(Path(tmp).rglob("*.stl"))
        assert any("rank_01" in s.name for s in stls), "rank_01 STL not written"


def test_stl_and_glb_share_same_slug():
    """GLB and STL for the same rank must have identical slugs."""
    from evolver_native import save_epoch
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _minimal_cfg(tmp)
        pop = [_minimal_grammar()]
        res = [_viable_result()]
        save_epoch(1, pop, res, cfg, elapsed=0.1, export_stl=True)
        epoch_dir = Path(tmp) / "epoch_0001"
        glb_stems = {p.stem for p in epoch_dir.glob("rank_01*.glb")}
        stl_stems = {p.stem for p in epoch_dir.glob("rank_01*.stl")}
        assert glb_stems == stl_stems, f"Slug mismatch: GLB={glb_stems} STL={stl_stems}"


def test_stl_is_valid_binary():
    """Exported STL must start with the 80-byte binary STL header."""
    from evolver_native import save_epoch
    with tempfile.TemporaryDirectory() as tmp:
        cfg = _minimal_cfg(tmp)
        pop = [_minimal_grammar()]
        res = [_viable_result()]
        save_epoch(1, pop, res, cfg, elapsed=0.1, export_stl=True)
        stl_files = list(Path(tmp).rglob("rank_01*.stl"))
        assert stl_files, "No STL produced"
        data = stl_files[0].read_bytes()
        # Binary STL: 80-byte header + 4-byte triangle count
        assert len(data) >= 84, "STL file too short to be valid binary STL"
