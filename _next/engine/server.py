"""
Flask API serving:
  GET  /api/grammar                        → list available grammars
  POST /api/evaluate                       → accept grammar JSON, return raymarcher params
  POST /api/mesh                           → accept grammar JSON, return GLB binary
  GET  /api/mesh/<name>                    → export a named grammar as GLB
  GET  /api/gallery                        → list evolution epochs (manifest.json)
  GET  /api/gallery/<epoch>/<filename>     → serve a file from gallery/epoch_NNNN/
"""

import io
import os
import json
from pathlib import Path

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from werkzeug.exceptions import BadRequest

from grammar_store import list_grammar_names, load_grammar
from sdf import SierpSphereEvaluator, extract_mesh

app = Flask(__name__)
CORS(app)

GRAMMAR_DIR = Path(os.environ.get("GRAMMAR_DIR", "/app/grammar"))
GALLERY_DIR = Path(os.environ.get("GALLERY_DIR", "/app/gallery"))

@app.route("/api/grammar", methods=["GET"])
def list_grammars():
    return jsonify(list_grammar_names(GRAMMAR_DIR))


@app.route("/api/grammar/<name>", methods=["GET"])
def get_grammar(name: str):
    """Return the raw grammar JSON for a named preset."""
    try:
        grammar = load_grammar(GRAMMAR_DIR, name)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404
    return jsonify(grammar)


@app.route("/api/evaluate", methods=["POST"])
def evaluate_grammar():
    """Accept grammar JSON, return the flat SDF description for the raymarcher."""
    try:
        grammar = request.get_json(force=True)
        ev = SierpSphereEvaluator(grammar)
        return jsonify(ev.to_raymarcher_json())
    except (BadRequest, KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid grammar payload: {exc}"}), 400


@app.route("/api/mesh", methods=["POST"])
def mesh_from_grammar():
    """Accept grammar JSON, return a GLB mesh."""
    try:
        grammar = request.get_json(force=True)
        ev = SierpSphereEvaluator(grammar)
        res = grammar.get("render", {}).get("resolution", 128)
        bnd = grammar.get("render", {}).get("bounds", 1.8)
        mesh = extract_mesh(ev, resolution=res, bounds=bnd)
    except (BadRequest, KeyError, TypeError, ValueError) as exc:
        return jsonify({"error": f"Invalid grammar payload: {exc}"}), 400

    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    buf.seek(0)
    return send_file(buf, mimetype="model/gltf-binary", download_name="sierpsphere.glb")


@app.route("/api/mesh/<name>", methods=["GET"])
def mesh_named(name: str):
    """Export a named grammar file as GLB."""
    try:
        grammar = load_grammar(GRAMMAR_DIR, name)
        ev = SierpSphereEvaluator(grammar)
        res = grammar.get("render", {}).get("resolution", 128)
        bnd = grammar.get("render", {}).get("bounds", 1.8)
        mesh = extract_mesh(ev, resolution=res, bounds=bnd)
    except FileNotFoundError as exc:
        return jsonify({"error": str(exc)}), 404

    buf = io.BytesIO()
    mesh.export(buf, file_type="glb")
    buf.seek(0)
    return send_file(buf, mimetype="model/gltf-binary", download_name=f"{name}.glb")


@app.route("/api/gallery", methods=["GET"])
def gallery_manifest():
    """Return the evolution manifest (list of epochs with fitness summaries)."""
    manifest_path = GALLERY_DIR / "manifest.json"
    if not manifest_path.exists():
        return jsonify([])
    return jsonify(json.loads(manifest_path.read_text()))


@app.route("/api/gallery/<int:epoch>/<filename>", methods=["GET"])
def gallery_file(epoch: int, filename: str):
    """Serve a file from gallery/epoch_NNNN/ (GLB, JSON, etc.)."""
    # Sanitise filename — no path traversal
    if "/" in filename or "\\" in filename or filename.startswith("."):
        return jsonify({"error": "Invalid filename"}), 400
    epoch_dir = GALLERY_DIR / f"epoch_{epoch:04d}"
    file_path = epoch_dir / filename
    if not file_path.exists():
        return jsonify({"error": "Not found"}), 404
    if filename.endswith(".glb"):
        return send_file(str(file_path), mimetype="model/gltf-binary", download_name=filename)
    if filename.endswith(".json"):
        return jsonify(json.loads(file_path.read_text()))
    return send_file(str(file_path), download_name=filename)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
