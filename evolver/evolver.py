"""
SierpSphere Grammar Evolver
Genetic algorithm targeting DMLS/SLM metal 3D printing fitness.

Usage (inside Podman):
  python evolver.py                    # run all epochs
  python evolver.py --epochs 5         # run 5 epochs only
  python evolver.py --resume           # continue from last saved population
"""
from __future__ import annotations

import argparse
import copy
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

import numpy as np
import trimesh

# Shared engine code (volume-mounted from ../engine)
sys.path.insert(0, "/app")
from sdf import SierpSphereEvaluator, extract_mesh
from grammar_store import list_grammar_names, load_grammar
from fitness import compute_fitness
from mutate import crossover, mutate, random_grammar, tournament_select
from grammar_name import grammar_name, grammar_slug


# ── Config ────────────────────────────────────────────────────────────────

def load_config() -> dict:
    with open("/app/config.json") as f:
        return json.load(f)


# ── Evaluation (runs in worker process) ──────────────────────────────────

def evaluate_individual(args: tuple) -> dict:
    """Worker: build SDF → extract mesh → compute fitness. Returns result dict."""
    grammar, cfg = args
    try:
        ev = SierpSphereEvaluator(grammar)
        mesh = extract_mesh(ev, resolution=cfg["eval_resolution"], bounds=cfg["bounds"])
        if mesh is None or len(mesh.faces) == 0:
            return {"fitness": 0.0, "hard_gate_failed": "empty_mesh",
                    "scores": {}, "manufacturing_note": "Mesh extraction produced no geometry."}
        result = compute_fitness(mesh, grammar, target_mm=cfg["target_mm"])
        return result
    except Exception as exc:
        return {"fitness": 0.0, "hard_gate_failed": "exception",
                "scores": {}, "manufacturing_note": str(exc)[:120]}


def evaluate_population(population: list[dict], cfg: dict) -> list[dict]:
    """Evaluate all individuals in parallel using all CPU cores."""
    args = [(g, cfg) for g in population]
    n_workers = min(cfg["pop_size"], mp.cpu_count())
    with mp.Pool(processes=n_workers) as pool:
        results = pool.map(evaluate_individual, args)
    return results


# ── Gallery output ────────────────────────────────────────────────────────

def save_epoch(
    epoch: int,
    population: list[dict],
    results: list[dict],
    cfg: dict,
    elapsed: float,
) -> None:
    gallery = Path(cfg["gallery_dir"])
    epoch_dir = gallery / f"epoch_{epoch:04d}"
    epoch_dir.mkdir(parents=True, exist_ok=True)

    fitnesses = [r["fitness"] for r in results]
    ranked = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i], reverse=True)
    top_k = ranked[: cfg["save_top_k"]]

    saved = []
    merged_meshes = []
    offset_x = 0.0

    for rank, idx in enumerate(top_k):
        grammar = population[idx]
        result = results[idx]
        slug = grammar_slug(grammar)

        # Save grammar JSON — filename encodes the grammar
        grammar_path = epoch_dir / f"rank_{rank+1:02d}_{slug}_grammar.json"
        grammar_path.write_text(json.dumps(grammar, indent=2))

        # High-res mesh for the winner only (rank 1), eval-res for the rest
        res = cfg["save_resolution"] if rank == 0 else cfg["eval_resolution"]
        try:
            ev = SierpSphereEvaluator(grammar)
            mesh = extract_mesh(ev, resolution=res, bounds=cfg["bounds"])
            if mesh and len(mesh.faces) > 0:
                glb_path = epoch_dir / f"rank_{rank+1:02d}_{slug}.glb"
                mesh.export(str(glb_path))

                # Accumulate for merged overview GLB
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
            "hard_gate_failed": result.get("hard_gate_failed"),
            "scores": result.get("scores", {}),
            "manufacturing_note": result.get("manufacturing_note", ""),
            "grammar_file": grammar_path.name,
        })

    # Merged overview GLB (all top-k side by side)
    if merged_meshes:
        merged = trimesh.util.concatenate(merged_meshes)
        merged.export(str(epoch_dir / "overview.glb"))

    # Per-epoch log
    log = {
        "epoch": epoch,
        "elapsed_s": round(elapsed, 1),
        "best_fitness": fitnesses[ranked[0]],
        "mean_fitness": round(float(np.mean([f for f in fitnesses if f > 0])), 4) if any(f > 0 for f in fitnesses) else 0.0,
        "viable_count": sum(1 for f in fitnesses if f > 0),
        "top_k": saved,
    }
    (epoch_dir / "fitness_log.json").write_text(json.dumps(log, indent=2))

    # Update global manifest
    manifest_path = gallery / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    manifest.append({
        "epoch": epoch,
        "best_fitness": log["best_fitness"],
        "mean_fitness": log["mean_fitness"],
        "viable_count": log["viable_count"],
        "elapsed_s": log["elapsed_s"],
    })
    manifest_path.write_text(json.dumps(manifest, indent=2))


# ── Printing ──────────────────────────────────────────────────────────────

def print_epoch(epoch: int, population: list[dict], results: list[dict], elapsed: float) -> None:
    fitnesses = [r["fitness"] for r in results]
    viable = [f for f in fitnesses if f > 0]
    best = max(fitnesses)
    mean = float(np.mean(viable)) if viable else 0.0
    best_idx = fitnesses.index(best)
    best_r = results[best_idx]
    best_grammar = population[best_idx]
    ts = time.strftime("%H:%M:%S")
    print(
        f"[{ts}] Epoch {epoch:04d} | "
        f"best={best:.4f}  mean={mean:.4f}  "
        f"viable={len(viable)}/{len(fitnesses)}  "
        f"t={elapsed:.1f}s"
    )
    print(f"  Best: {grammar_name(best_grammar)}")
    if best_r.get("scores"):
        top_scores = sorted(best_r["scores"].items(), key=lambda x: x[1], reverse=True)[:5]
        print("  Scores: " + "  ".join(f"{k}={v:.3f}" for k, v in top_scores))
    sys.stdout.flush()


# ── Seed population ───────────────────────────────────────────────────────

def build_seed_population(cfg: dict) -> list[dict]:
    grammar_dir = Path(cfg["grammar_dir"])
    names = list_grammar_names(grammar_dir)
    seeds = [load_grammar(grammar_dir, n) for n in names]
    if not seeds:
        raise RuntimeError(f"No grammars found in {grammar_dir}")

    population = list(seeds)  # include originals
    while len(population) < cfg["pop_size"]:
        population.append(random_grammar(seeds))
    return population[: cfg["pop_size"]]


# ── Main GA loop ──────────────────────────────────────────────────────────

def next_generation(
    population: list[dict],
    results: list[dict],
    cfg: dict,
) -> list[dict]:
    fitnesses = [r["fitness"] for r in results]
    ranked = sorted(range(len(fitnesses)), key=lambda i: fitnesses[i], reverse=True)

    next_pop: list[dict] = []

    # Elitism: carry top-k unchanged
    for i in ranked[: cfg["elitism_k"]]:
        next_pop.append(copy.deepcopy(population[i]))

    # Fill rest via crossover + mutation
    while len(next_pop) < cfg["pop_size"]:
        if np.random.random() < cfg["crossover_rate"] and len(population) >= 2:
            pa = tournament_select(population, fitnesses, cfg["tournament_k"])
            pb = tournament_select(population, fitnesses, cfg["tournament_k"])
            child_a, child_b = crossover(pa, pb)
            next_pop.append(mutate(child_a, cfg["mutation_rate"]))
            if len(next_pop) < cfg["pop_size"]:
                next_pop.append(mutate(child_b, cfg["mutation_rate"]))
        else:
            parent = tournament_select(population, fitnesses, cfg["tournament_k"])
            next_pop.append(mutate(parent, cfg["mutation_rate"]))

    return next_pop[: cfg["pop_size"]]


def run(args: argparse.Namespace) -> None:
    cfg = load_config()
    n_epochs = args.epochs or cfg["n_epochs"]
    gallery = Path(cfg["gallery_dir"])
    gallery.mkdir(parents=True, exist_ok=True)

    # Resume or start fresh
    pop_file = gallery / "population.json"
    if args.resume and pop_file.exists():
        population = json.loads(pop_file.read_text())
        start_epoch = len(json.loads((gallery / "manifest.json").read_text())) + 1
        print(f"Resuming from epoch {start_epoch} with {len(population)} individuals.")
    else:
        population = build_seed_population(cfg)
        start_epoch = 1
        print(f"Starting fresh: {len(population)} individuals, {n_epochs} epochs.")

    print(f"CPU workers: {mp.cpu_count()}  eval_res: {cfg['eval_resolution']}  save_res: {cfg['save_resolution']}")
    print("-" * 70)

    for epoch in range(start_epoch, start_epoch + n_epochs):
        t0 = time.time()
        results = evaluate_population(population, cfg)
        elapsed = time.time() - t0

        print_epoch(epoch, population, results, elapsed)
        save_epoch(epoch, population, results, cfg, elapsed)

        # Persist current population for resume
        pop_file.write_text(json.dumps(population, indent=2))

        population = next_generation(population, results, cfg)

    print("=" * 70)
    print("Evolution complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SierpSphere Grammar Evolver")
    parser.add_argument("--epochs", type=int, default=0, help="Override n_epochs from config")
    parser.add_argument("--resume", action="store_true", help="Resume from last saved population")
    run(parser.parse_args())
