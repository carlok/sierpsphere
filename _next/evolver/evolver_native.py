"""
SierpSphere Grammar Evolver — native macOS Metal version.
No Podman. Runs directly on host Python with PyTorch MPS.

Setup (once):
  pip install -r requirements_native.txt

Usage:
  python evolver_native.py                 # fresh run
  python evolver_native.py --epochs 5      # run N epochs
  python evolver_native.py --resume        # continue from last saved population
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

# ── Path setup ───────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "engine"))   # sdf.py, grammar_store.py
sys.path.insert(0, str(Path(__file__).parent))  # fitness.py, mutate.py, grammar_name.py

from sdf import SierpSphereEvaluator
from grammar_store import list_grammar_names, load_grammar  # kept for --resume path
from fitness import compute_fitness
from mutate import crossover, mutate, diverse_population, tournament_select
from grammar_name import grammar_name, grammar_slug
from sdf_metal import extract_mesh_metal, device_info


# ── Config ────────────────────────────────────────────────────────────────────

CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Remap Podman /app/ paths to repo root
    def remap(p: str) -> str:
        if p.startswith("/app/"):
            return str(ROOT / p[len("/app/"):])
        if not Path(p).is_absolute():
            return str(ROOT / p)
        return p
    cfg["grammar_dir"] = remap(cfg["grammar_dir"])
    cfg["gallery_dir"] = remap(cfg["gallery_dir"])
    return cfg


# ── Evaluation (single, uses Metal) ──────────────────────────────────────────

def evaluate_individual(grammar: dict, cfg: dict) -> dict:
    try:
        mesh = extract_mesh_metal(grammar,
                                  resolution=cfg["eval_resolution"],
                                  bounds=cfg["bounds"])
        if mesh is None or len(mesh.faces) == 0:
            return {"fitness": 0.0, "hard_gate_failed": "empty_mesh",
                    "scores": {}, "manufacturing_note": "Empty mesh."}
        return compute_fitness(mesh, grammar, target_mm=cfg["target_mm"])
    except Exception as exc:
        return {"fitness": 0.0, "hard_gate_failed": "exception",
                "scores": {}, "manufacturing_note": str(exc)[:120]}


def _worker_init():
    """Per-worker initialisation — each process gets its own MPS context."""
    import torch
    if torch.backends.mps.is_available():
        # warm up MPS in this process
        _ = torch.zeros(1, device="mps")


def _worker_eval(args):
    """Top-level function (picklable) for multiprocessing."""
    grammar, cfg = args
    return evaluate_individual(grammar, cfg)


def evaluate_population(population: list[dict], cfg: dict, max_workers: int = 0) -> list[dict]:
    """Evaluate population in parallel — one MPS context per worker process."""
    import multiprocessing as mp
    cap = max_workers if max_workers > 0 else mp.cpu_count()
    n_workers = min(len(population), cap)

    # 'spawn' is required on macOS (fork + MPS = crash)
    ctx = mp.get_context("spawn")
    args = [(g, cfg) for g in population]

    with ctx.Pool(processes=n_workers, initializer=_worker_init) as pool:
        results = pool.map(_worker_eval, args)

    # Print summary after all results arrive
    for i, (g, r) in enumerate(zip(population, results)):
        print(f"  [{i+1:02d}/{len(population)}] "
              f"f={r['fitness']:.4f}  "
              f"{grammar_name(g)}"
              + (f"  ✗ {r['hard_gate_failed']}" if r.get("hard_gate_failed") else ""),
              flush=True)
    return results


# ── Gallery output ────────────────────────────────────────────────────────────

def save_epoch(epoch, population, results, cfg, elapsed):
    gallery = Path(cfg["gallery_dir"])
    epoch_dir = gallery / f"epoch_{epoch:04d}"
    epoch_dir.mkdir(parents=True, exist_ok=True)

    fitnesses = [r["fitness"] for r in results]
    ranked = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i], reverse=True)
    top_k = ranked[:cfg["save_top_k"]]

    saved = []
    merged_meshes = []
    offset_x = 0.0

    for rank, idx in enumerate(top_k):
        grammar = population[idx]
        result = results[idx]
        slug = grammar_slug(grammar)
        viable = result["fitness"] > 0.0

        # Grammar JSON: viable only
        if not viable:
            saved.append({
                "rank": rank + 1,
                "name": grammar_name(grammar),
                "slug": slug,
                "fitness": 0.0,
                "hard_gate_failed": result.get("hard_gate_failed"),
                "scores": {},
                "manufacturing_note": result.get("manufacturing_note", ""),
                "grammar_file": None,
            })
            continue

        grammar_path = epoch_dir / f"rank_{rank+1:02d}_{slug}_grammar.json"
        grammar_path.write_text(json.dumps(grammar, indent=2))

        res = cfg["save_resolution"] if rank == 0 else cfg["eval_resolution"]
        try:
            mesh = extract_mesh_metal(grammar, resolution=res, bounds=cfg["bounds"])
            if mesh and len(mesh.faces) > 0:
                # At save_res the mesh may split vs eval_res — keep largest component only
                parts = mesh.split(only_watertight=False)
                if len(parts) > 1:
                    mesh = max(parts, key=lambda p: len(p.faces))
                    mesh = trimesh.Trimesh(
                        vertices=mesh.vertices.copy(),
                        faces=mesh.faces.copy(),
                        process=False,
                    )
                glb_path = epoch_dir / f"rank_{rank+1:02d}_{slug}.glb"
                mesh.export(str(glb_path))
                m = mesh.copy()
                m.apply_translation([offset_x, 0, 0])
                offset_x += mesh.bounding_box.extents[0] * 1.3
                merged_meshes.append(m)
        except Exception:
            pass

        saved.append({
            "rank": rank + 1,
            "name": grammar_name(grammar),
            "slug": slug,
            "fitness": result["fitness"],
            "hard_gate_failed": None,
            "scores": result.get("scores", {}),
            "manufacturing_note": result.get("manufacturing_note", ""),
            "grammar_file": grammar_path.name,
        })

    if merged_meshes:
        trimesh.util.concatenate(merged_meshes).export(str(epoch_dir / "overview.glb"))

    viable = [f for f in fitnesses if f > 0]
    log = {
        "epoch": epoch,
        "elapsed_s": round(elapsed, 1),
        "best_fitness": fitnesses[ranked[0]],
        "mean_fitness": round(float(np.mean(viable)), 4) if viable else 0.0,
        "viable_count": len(viable),
        "top_k": saved,
    }
    (epoch_dir / "fitness_log.json").write_text(json.dumps(log, indent=2))

    manifest_path = gallery / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    manifest.append({
        "epoch": epoch, "best_fitness": log["best_fitness"],
        "mean_fitness": log["mean_fitness"], "viable_count": log["viable_count"],
        "elapsed_s": log["elapsed_s"],
    })
    manifest_path.write_text(json.dumps(manifest, indent=2))


# ── Printing ──────────────────────────────────────────────────────────────────

def print_epoch(epoch, population, results, elapsed):
    fitnesses = [r["fitness"] for r in results]
    viable = [f for f in fitnesses if f > 0]
    best = max(fitnesses)
    mean = float(np.mean(viable)) if viable else 0.0
    best_idx = fitnesses.index(best)
    ts = time.strftime("%H:%M:%S")
    print(f"\n[{ts}] Epoch {epoch:04d} | "
          f"best={best:.4f}  mean={mean:.4f}  "
          f"viable={len(viable)}/{len(fitnesses)}  t={elapsed:.1f}s")
    print(f"  Best: {grammar_name(population[best_idx])}")
    scores = results[best_idx].get("scores", {})
    if scores:
        top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:5]
        print("  Scores: " + "  ".join(f"{k}={v:.3f}" for k, v in top))
    sys.stdout.flush()


# ── Seed population ───────────────────────────────────────────────────────────

def build_seed_population(cfg):
    """Diverse random population — equal thirds of each seed type."""
    return diverse_population(cfg["pop_size"])


# ── GA ────────────────────────────────────────────────────────────────────────

def next_generation(population, results, cfg):
    fitnesses = [r["fitness"] for r in results]
    ranked = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i], reverse=True)
    next_pop = [copy.deepcopy(population[i]) for i in ranked[:cfg["elitism_k"]]]

    # Type elitism: keep best viable of each seed type
    for prim in ["tetrahedron", "cube", "icosahedron"]:
        best_idx = next(
            (i for i in ranked
             if population[i].get("seed", {}).get("type") == prim
             and fitnesses[i] > 0
             and population[i] not in next_pop),
            None
        )
        if best_idx is not None:
            next_pop.append(copy.deepcopy(population[best_idx]))
    while len(next_pop) < cfg["pop_size"]:
        if np.random.random() < cfg["crossover_rate"] and len(population) >= 2:
            pa = tournament_select(population, fitnesses, cfg["tournament_k"])
            pb = tournament_select(population, fitnesses, cfg["tournament_k"])
            ca, cb = crossover(pa, pb)
            next_pop.append(mutate(ca, cfg["mutation_rate"]))
            if len(next_pop) < cfg["pop_size"]:
                next_pop.append(mutate(cb, cfg["mutation_rate"]))
        else:
            next_pop.append(mutate(
                tournament_select(population, fitnesses, cfg["tournament_k"]),
                cfg["mutation_rate"]))
    return next_pop[:cfg["pop_size"]]


# ── Main ──────────────────────────────────────────────────────────────────────

def run(args):
    cfg = load_config()
    n_epochs = args.epochs or cfg["n_epochs"]
    gallery = Path(cfg["gallery_dir"])
    gallery.mkdir(parents=True, exist_ok=True)

    import multiprocessing as mp
    workers = args.workers if args.workers > 0 else mp.cpu_count()
    print(f"Device: {device_info()}")
    print(f"eval_res={cfg['eval_resolution']}  save_res={cfg['save_resolution']}  "
          f"pop={cfg['pop_size']}  epochs={n_epochs}  workers={workers}")

    pop_file = gallery / "population.json"
    if args.resume and pop_file.exists():
        population = json.loads(pop_file.read_text())
        start_epoch = len(json.loads((gallery / "manifest.json").read_text())) + 1
        print(f"Resuming from epoch {start_epoch} ({len(population)} individuals)")
    else:
        population = build_seed_population(cfg)
        start_epoch = 1
        print(f"Starting fresh: {len(population)} individuals")
    print("-" * 70)

    for epoch in range(start_epoch, start_epoch + n_epochs):
        ts = time.strftime("%H:%M:%S")
        print(f"\n[{ts}] Epoch {epoch:04d} — evaluating {len(population)} individuals…")
        t0 = time.time()
        results = evaluate_population(population, cfg, args.workers)
        elapsed = time.time() - t0

        print_epoch(epoch, population, results, elapsed)
        save_epoch(epoch, population, results, cfg, elapsed)
        pop_file.write_text(json.dumps(population, indent=2))
        population = next_generation(population, results, cfg)

    print("=" * 70)
    print("Evolution complete.")


if __name__ == "__main__":
    # Required for 'spawn' multiprocessing on macOS
    import multiprocessing
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=0,
                        help="Max parallel workers (0 = all cores)")
    run(parser.parse_args())
