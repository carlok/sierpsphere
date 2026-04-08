import json
from pathlib import Path

from grammar_store import list_grammar_names, load_grammar


def test_list_grammar_names_excludes_schema(tmp_path: Path) -> None:
    grammar_dir = tmp_path / "grammar"
    grammar_dir.mkdir()
    (grammar_dir / "schema.json").write_text("{}")
    (grammar_dir / "sierpinski_classic.json").write_text("{}")
    (grammar_dir / "sierpinski_cube.json").write_text("{}")
    names = list_grammar_names(grammar_dir)
    assert "schema" not in names
    assert "sierpinski_classic" in names
    assert "sierpinski_cube" in names


def test_load_grammar_cube_seed_type(tmp_path: Path) -> None:
    grammar_dir = tmp_path / "grammar"
    grammar_dir.mkdir()
    payload = {"seed": {"type": "cube"}, "iterations": [{"primitive": "cube"}]}
    (grammar_dir / "sierpinski_cube.json").write_text(json.dumps(payload))
    grammar = load_grammar(grammar_dir, "sierpinski_cube")
    assert grammar["seed"]["type"] == "cube"
    assert grammar["iterations"][0]["primitive"] == "cube"

